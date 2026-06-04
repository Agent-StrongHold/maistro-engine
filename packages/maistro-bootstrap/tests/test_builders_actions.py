"""Structured action protocol for builder sessions."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from maistro_bootstrap.builders.actions import ActionRequest
from maistro_bootstrap.builders.session import (
    MAX_ACTION_OUTPUT_CHARS,
    BuilderSession,
    SandboxCommandResult,
    _compact,
    _required_bool,
    _required_float,
    _required_str,
)


@dataclass
class FakeSandbox:
    files: dict[str, str] = field(default_factory=lambda: {"README.md": "hello"})
    commands: list[list[str]] = field(default_factory=list)

    def read_file(self, path: str) -> str:
        return self.files[path]

    def write_file(self, path: str, content: str) -> None:
        self.files[path] = content

    def search(self, query: str) -> list[str]:
        return [path for path, content in self.files.items() if query in content]

    def run_command(self, argv: list[str], *, timeout: float) -> SandboxCommandResult:
        self.commands.append(argv)
        return SandboxCommandResult(returncode=0, stdout="ok", stderr="", elapsed_seconds=0.01)

    def diff(self) -> str:
        return "diff --git a/README.md b/README.md\n"


def test_action_request_rejects_unknown_action() -> None:
    with pytest.raises(ValueError, match="unsupported builder action"):
        ActionRequest.from_json('{"action":"delete_everything","args":{}}')


def test_session_reads_files_and_runs_commands() -> None:
    sandbox = FakeSandbox()
    session = BuilderSession(sandbox=sandbox)

    read = session.apply_action(ActionRequest.from_json('{"action":"read_file","args":{"path":"README.md"}}'))
    run = session.apply_action(
        ActionRequest.from_json('{"action":"run_command","args":{"argv":["pytest","-q"],"timeout":5}}')
    )

    assert read.output == "hello"
    assert run.output == "ok"
    assert sandbox.commands == [["pytest", "-q"]]


def test_session_writes_proposed_patch_inside_sandbox() -> None:
    sandbox = FakeSandbox()
    session = BuilderSession(sandbox=sandbox)

    result = session.apply_action(
        ActionRequest.from_json(
            '{"action":"propose_patch","args":{"path":"README.md","content":"updated"}}'
        )
    )

    assert result.status == "ok"
    assert sandbox.files["README.md"] == "updated"


def test_session_requires_explicit_approval_before_apply() -> None:
    session = BuilderSession(sandbox=FakeSandbox())

    result = session.apply_action(ActionRequest.from_json('{"action":"apply_diff","args":{}}'))

    assert result.status == "needs_approval"
    assert "approval" in result.output


def test_session_slash_commands_use_structured_actions() -> None:
    sandbox = FakeSandbox()
    session = BuilderSession(sandbox=sandbox)

    diff = session.apply_slash_command("/diff")
    test = session.apply_slash_command("/test")
    status = session.apply_slash_command("/status")

    assert diff.output.startswith("diff --git")
    assert test.metadata["returncode"] == 0
    assert status.output.startswith("Builder session")
    assert sandbox.commands == [["uv", "run", "pytest", "-q"]]


def test_session_board_slash_command_lists_kanban_counts() -> None:
    session = BuilderSession(sandbox=FakeSandbox())
    session.message_board.add_todo(title="Implement CLI", owner="mason")

    result = session.apply_slash_command("/board")

    assert result.status == "ok"
    assert "todo=1" in result.output
    assert "wip=0" in result.output
    assert "done=0" in result.output


def test_session_snapshot_exposes_dashboard_state() -> None:
    session = BuilderSession(sandbox=FakeSandbox())

    session.message_board.post_question(agent="mason", question="Pick a test target?")
    session.apply_action(ActionRequest.from_json('{"action":"show_diff","args":{}}'))
    snapshot = session.snapshot()

    assert snapshot["actions"] == 1
    assert snapshot["last_status"] == "ok"
    assert snapshot["approved_to_apply"] is False
    assert snapshot["pending_diff"] is True
    assert snapshot["open_questions"] == 1


def test_session_spec_acceptance_creates_board_todos() -> None:
    session = BuilderSession(sandbox=FakeSandbox())

    session.spec_session.define_spec(
        title="Builder DAG",
        summary="Autonomous feature delivery.",
        acceptance_criteria=["Coverage >= 90%", "Mutation evidence reviewed"],
    )
    session.spec_session.accept()
    todos = session.spec_session.to_todos(owner="auditor")
    snapshot = session.snapshot()

    assert len(todos) == 2
    assert snapshot["board_columns"] == {"todo": 2, "wip": 0, "done": 0}


def test_session_snapshot_exposes_dag_quality_progress() -> None:
    session = BuilderSession(sandbox=FakeSandbox())

    snapshot = session.snapshot()

    assert snapshot["dag"]["columns"] == {"todo": 5, "wip": 0, "done": 0}
    assert snapshot["dag"]["complete"] is False


def test_structured_actions_define_spec_and_leave_human_board_comment() -> None:
    session = BuilderSession(sandbox=FakeSandbox())

    spec_result = session.apply_action(
        ActionRequest.from_json(
            """
            {
              "action": "define_spec",
              "args": {
                "title": "Async builder flow",
                "summary": "Human guides an autonomous DAG from the board.",
                "acceptance_criteria": ["Human comment accepted"]
              }
            }
            """
        )
    )
    todo = session.message_board.add_todo(title="Review finished implementation", owner="auditor")
    done = session.message_board.finish(todo.card_id, summary="Ready for review.")
    comment_result = session.apply_action(
        ActionRequest.from_json(
            f'{{"action":"comment_card","args":{{"card_id":"{done.card_id}","body":"Ship after ruff."}}}}'
        )
    )

    assert spec_result.status == "ok"
    assert comment_result.status == "ok"
    assert session.message_board.get(done.card_id).comments[-1].body == "Ship after ruff."


def test_structured_action_records_quality_and_quality_slash_command_reports_failures() -> None:
    session = BuilderSession(sandbox=FakeSandbox())

    result = session.apply_action(
        ActionRequest.from_json(
            """
            {
              "action": "record_quality",
              "args": {
                "tests_passed": true,
                "coverage_pct": 88.0,
                "mutation_score_pct": 100.0,
                "complexity_grade": "B+",
                "dry_ok": true,
                "code_smells_ok": true,
                "bandit_ok": true,
                "ruff_ok": true,
                "mypy_ok": true
              }
            }
            """
        )
    )
    quality = session.apply_slash_command("/quality")

    assert result.status == "error"
    assert "coverage >= 90%" in quality.output


def test_session_argument_validators_pin_exact_types_and_errors() -> None:
    assert _required_str({"path": "README.md"}, "path") == "README.md"
    assert _required_bool({"tests_passed": True}, "tests_passed") is True
    assert _required_float({"coverage": 90}, "coverage") == 90.0

    with pytest.raises(ValueError, match="path is required"):
        _required_str({"path": ""}, "path")
    with pytest.raises(ValueError, match="tests_passed must be bool"):
        _required_bool({"tests_passed": 1}, "tests_passed")
    with pytest.raises(ValueError, match="coverage must be number"):
        _required_float({"coverage": "90"}, "coverage")


def test_compact_preserves_short_output_and_truncates_long_output() -> None:
    short = "x" * MAX_ACTION_OUTPUT_CHARS
    long = "a" * (MAX_ACTION_OUTPUT_CHARS + 1)

    compacted = _compact(long)

    assert _compact(short) == short
    assert compacted.startswith("a" * (MAX_ACTION_OUTPUT_CHARS // 2))
    assert "\n[...output truncated...]\n" in compacted
    assert compacted.endswith("a" * (MAX_ACTION_OUTPUT_CHARS // 2))
