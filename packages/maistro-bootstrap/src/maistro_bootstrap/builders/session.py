"""Hybrid opencode/Claude Code/Builders session engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maistro_bootstrap.builders.actions import ActionRequest, ActionResult
from maistro_bootstrap.builders.dagflow import DagFlow
from maistro_bootstrap.builders.message_board import MessageBoard
from maistro_bootstrap.builders.quality import QualityGateReport
from maistro_bootstrap.builders.sandbox import BuilderSandbox, SandboxCommandResult
from maistro_bootstrap.builders.spec_session import SpecSession

MAX_ACTION_OUTPUT_CHARS = 20_000


@dataclass
class BuilderSession:
    """Small validated action loop for interactive builder sessions."""

    sandbox: BuilderSandbox
    approved_to_apply: bool = False
    message_board: MessageBoard = field(default_factory=MessageBoard)
    spec_session: SpecSession = field(init=False)
    dagflow: DagFlow = field(default_factory=DagFlow)
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.spec_session = SpecSession(board=self.message_board)

    def apply_action(self, request: ActionRequest) -> ActionResult:
        """Execute one validated model action and append a compact transcript event."""
        try:
            result = self._apply_action(request)
        except Exception as exc:
            result = ActionResult(status="error", output=str(exc))
        self.transcript.append(
            {
                "action": request.action,
                "args": request.args,
                "status": result.status,
                "output": _compact(result.output),
            }
        )
        return result

    def apply_slash_command(self, command: str) -> ActionResult:
        """Execute one Codex/opencode-style slash command through structured actions."""
        normalized = command.strip()
        if normalized == "/diff":
            return self.apply_action(ActionRequest(action="show_diff"))
        if normalized == "/test":
            return self.apply_action(
                ActionRequest(
                    action="run_command",
                    args={"argv": ["uv", "run", "pytest", "-q"], "timeout": 300.0},
                )
            )
        if normalized == "/status":
            return ActionResult(status="ok", output=self.summary())
        if normalized == "/board":
            columns = self.message_board.columns()
            return ActionResult(
                status="ok",
                output=(
                    f"todo={len(columns['todo'])} "
                    f"wip={len(columns['wip'])} "
                    f"done={len(columns['done'])} "
                    f"questions={len(self.message_board.open_cards())}"
                ),
            )
        if normalized == "/quality":
            if self.dagflow.quality is None:
                return ActionResult(status="ok", output="No quality report recorded.")
            failures = self.dagflow.quality.failures()
            if failures:
                return ActionResult(status="error", output="\n".join(failures))
            return ActionResult(status="ok", output="Quality gates passed.")
        if normalized == "/apply":
            return self.apply_action(ActionRequest(action="apply_diff"))
        if normalized == "/reject":
            self.approved_to_apply = False
            return ActionResult(status="ok", output="pending diff rejected for this session")
        raise ValueError(f"unsupported slash command: {command}")

    def _apply_action(self, request: ActionRequest) -> ActionResult:
        handlers: dict[str, Callable[[ActionRequest], ActionResult]] = {
            "read_file": self._handle_read_file,
            "search": self._handle_search,
            "propose_patch": self._handle_propose_patch,
            "run_command": self._handle_run_command,
            "show_diff": self._handle_show_diff,
            "apply_diff": self._handle_apply_diff,
            "summarize": self._handle_summarize,
            "define_spec": self._handle_define_spec,
            "accept_spec": self._handle_accept_spec,
            "comment_card": self._handle_comment_card,
            "post_question": self._handle_post_question,
            "record_quality": self._handle_record_quality,
        }
        return handlers[request.action](request)

    def _handle_read_file(self, request: ActionRequest) -> ActionResult:
        path = _required_str(request.args, "path")
        return ActionResult(status="ok", output=self.sandbox.read_file(path))

    def _handle_search(self, request: ActionRequest) -> ActionResult:
        query = _required_str(request.args, "query")
        return ActionResult(status="ok", output="\n".join(self.sandbox.search(query)))

    def _handle_propose_patch(self, request: ActionRequest) -> ActionResult:
        path = _required_str(request.args, "path")
        content = _required_str(request.args, "content")
        self.sandbox.write_file(path, content)
        return ActionResult(status="ok", output=f"updated {path} in sandbox")

    def _handle_run_command(self, request: ActionRequest) -> ActionResult:
        argv = request.args.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            raise ValueError("run_command.args.argv must be a list[str]")
        timeout = float(request.args.get("timeout", 30.0))
        command = self.sandbox.run_command(argv, timeout=timeout)
        output = command.stdout if command.stdout else command.stderr
        return ActionResult(
            status="ok" if command.returncode == 0 else "error",
            output=_compact(output),
            metadata={
                "returncode": command.returncode,
                "elapsed_seconds": command.elapsed_seconds,
            },
        )

    def _handle_show_diff(self, _: ActionRequest) -> ActionResult:
        return ActionResult(status="ok", output=_compact(self.sandbox.diff()))

    def _handle_apply_diff(self, _: ActionRequest) -> ActionResult:
        if not self.approved_to_apply:
            return ActionResult(
                status="needs_approval",
                output="diff application requires explicit human approval",
            )
        return ActionResult(status="ok", output="approved diff ready for application")

    def _handle_summarize(self, _: ActionRequest) -> ActionResult:
        return ActionResult(status="ok", output=self.summary())

    def _handle_define_spec(self, request: ActionRequest) -> ActionResult:
        title = _required_str(request.args, "title")
        summary = _required_str(request.args, "summary")
        raw_criteria = request.args.get("acceptance_criteria")
        if not isinstance(raw_criteria, list) or not all(
            isinstance(item, str) for item in raw_criteria
        ):
            raise ValueError("define_spec.args.acceptance_criteria must be a list[str]")
        draft = self.spec_session.define_spec(
            title=title,
            summary=summary,
            acceptance_criteria=raw_criteria,
        )
        return ActionResult(
            status="ok",
            output=self.spec_session.render_review(),
            metadata={"status": draft.status, "criteria": len(draft.acceptance_criteria)},
        )

    def _handle_accept_spec(self, request: ActionRequest) -> ActionResult:
        draft = self.spec_session.accept()
        todos = self.spec_session.to_todos(owner=str(request.args.get("owner", "frank")))
        return ActionResult(
            status="ok",
            output=f"accepted spec '{draft.title}' and created {len(todos)} todo(s)",
            metadata={"todos": len(todos)},
        )

    def _handle_comment_card(self, request: ActionRequest) -> ActionResult:
        card_id = _required_str(request.args, "card_id")
        body = _required_str(request.args, "body")
        updated = self.message_board.add_human_comment(card_id, body)
        return ActionResult(
            status="ok",
            output=f"commented on {updated.card_id}",
            metadata={"comments": len(updated.comments)},
        )

    def _handle_post_question(self, request: ActionRequest) -> ActionResult:
        agent = _required_str(request.args, "agent")
        question = _required_str(request.args, "question")
        card = self.message_board.post_question(agent=agent, question=question)
        return ActionResult(
            status="ok",
            output=f"posted question {card.card_id}",
            metadata={"card_id": card.card_id},
        )

    def _handle_record_quality(self, request: ActionRequest) -> ActionResult:
        report = QualityGateReport(
            tests_passed=_required_bool(request.args, "tests_passed"),
            coverage_pct=_required_float(request.args, "coverage_pct"),
            mutation_score_pct=_required_float(request.args, "mutation_score_pct"),
            complexity_grade=_required_str(request.args, "complexity_grade"),
            dry_ok=_required_bool(request.args, "dry_ok"),
            code_smells_ok=_required_bool(request.args, "code_smells_ok"),
            bandit_ok=_required_bool(request.args, "bandit_ok"),
            ruff_ok=_required_bool(request.args, "ruff_ok"),
            mypy_ok=_required_bool(request.args, "mypy_ok"),
        )
        self.dagflow.record_quality(report)
        failures = report.failures()
        return ActionResult(
            status="ok" if report.passed else "error",
            output="Quality gates passed." if report.passed else "\n".join(failures),
            metadata={"passed": report.passed, "failures": failures},
        )

    def summary(self) -> str:
        actions = len(self.transcript)
        last_status = self.transcript[-1]["status"] if self.transcript else "none"
        return f"Builder session: {actions} action(s), last_status={last_status}"

    def snapshot(self) -> dict[str, object]:
        """Renderer-friendly state for a future full-screen TUI side panel."""
        last_status = self.transcript[-1]["status"] if self.transcript else "none"
        diff = self.sandbox.diff()
        return {
            "actions": len(self.transcript),
            "last_status": last_status,
            "approved_to_apply": self.approved_to_apply,
            "pending_diff": bool(diff.strip()),
            "open_questions": len(self.message_board.open_cards()),
            "board_columns": {
                name: len(cards) for name, cards in self.message_board.columns().items()
            },
            "spec_status": (
                self.spec_session.draft.status if self.spec_session.draft is not None else "none"
            ),
            "dag": self.dagflow.snapshot(),
            "transcript_tail": self.transcript[-5:],
        }


def _required_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value


def _required_bool(args: dict[str, Any], key: str) -> bool:
    value = args.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be bool")
    return value


def _required_float(args: dict[str, Any], key: str) -> float:
    value = args.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"{key} must be number")
    return float(value)


def _compact(value: str) -> str:
    if len(value) <= MAX_ACTION_OUTPUT_CHARS:
        return value
    keep = MAX_ACTION_OUTPUT_CHARS // 2
    return value[:keep] + "\n[...output truncated...]\n" + value[-keep:]


__all__ = ["BuilderSession", "SandboxCommandResult"]
