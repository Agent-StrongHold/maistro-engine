"""ReAct agent loop for interactive builder sessions.

Drives the think → act → observe cycle using LiteLLM with role-specific models.
Each turn produces a TurnRecord for evolve fitness evaluation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from maistro_bootstrap.builders.actions import ActionRequest, ActionResult
from maistro_bootstrap.builders.models import BuilderModelRoles
from maistro_bootstrap.builders.session import BuilderSession
from maistro_bootstrap.builders.turn_record import TurnRecord

AutonomyLevel = Literal["auto", "supervised", "stage_gated"]

SYSTEM_PROMPTS: dict[str, str] = {
    "architect": (
        "You are a senior software architect planning a change.\n"
        "Analyze the task, research the codebase, and produce a structured plan.\n"
        "Respond with exactly one JSON action per turn.\n"
        "Available actions: search, read_file, define_spec, accept_spec, post_question, summarize.\n"
        'Format: {"action": "<name>", "args": {<key-value pairs>}}\n'
        "After gathering enough context, use define_spec to formalize acceptance criteria."
    ),
    "editor": (
        "You are an expert code editor implementing a planned change.\n"
        "Read files, write patches, and verify your changes compile.\n"
        "Respond with exactly one JSON action per turn.\n"
        "Available actions: search, read_file, propose_patch, run_command, show_diff, summarize.\n"
        'Format: {"action": "<name>", "args": {<key-value pairs>}}\n'
        "After implementing, use show_diff to preview your changes."
    ),
    "tester": (
        "You are a thorough test engineer writing tests for a change.\n"
        "Read the implementation, write tests, and run them.\n"
        "Respond with exactly one JSON action per turn.\n"
        "Available actions: search, read_file, propose_patch, run_command, show_diff, record_quality.\n"
        'Format: {"action": "<name>", "args": {<key-value pairs>}}\n'
        "After tests pass, use record_quality to capture the quality gate."
    ),
}

ACTION_ROLE_MAP: dict[str, str] = {
    "search": "architect",
    "read_file": "architect",
    "define_spec": "architect",
    "accept_spec": "architect",
    "post_question": "architect",
    "summarize": "architect",
    "propose_patch": "editor",
    "run_command": "editor",
    "show_diff": "editor",
    "apply_diff": "editor",
    "record_quality": "tester",
    "comment_card": "architect",
}

STAGE_ROLE_MAP: dict[str, str] = {
    "spec": "architect",
    "plan": "architect",
    "implement": "editor",
    "test": "tester",
    "audit": "architect",
}

MAX_RETRIES_PER_TURN = 3
MAX_OBSERVATION_CHARS = 8000


@dataclass
class AgentLoopConfig:
    autonomy: AutonomyLevel = "supervised"
    max_turns: int = 50
    quality_gates_required: bool = True
    min_coverage_pct: float = 90.0
    min_mutation_score_pct: float = 90.0


@dataclass
class AgentTurnResult:
    turn_record: TurnRecord
    action_result: ActionResult
    needs_human_input: bool = False
    human_prompt: str = ""


@dataclass
class AgentLoopState:
    current_stage: str = "spec"
    turns: list[TurnRecord] = field(default_factory=list)
    turn_count: int = 0
    quality_snapshot: dict[str, Any] = field(default_factory=dict)


class TurnRunner:
    """Executes one ReAct turn: build context → call LLM → parse action → execute → record."""

    def __init__(
        self,
        session: BuilderSession,
        roles: BuilderModelRoles,
        *,
        session_id: str = "default",
        config: AgentLoopConfig | None = None,
    ) -> None:
        self._session = session
        self._roles = roles
        self._session_id = session_id
        self._config = config or AgentLoopConfig()
        self._state = AgentLoopState()
        self._llm_call: LLMCallable | None = None

    @property
    def state(self) -> AgentLoopState:
        return self._state

    @property
    def session(self) -> BuilderSession:
        return self._session

    def set_llm(self, llm: LLMCallable) -> None:
        self._llm_call = llm

    def _role_for_stage(self, stage: str) -> str:
        return STAGE_ROLE_MAP.get(stage, "architect")

    def _model_for_role(self, role: str) -> str:
        return getattr(self._roles, role, self._roles.fallback)

    def _build_context(self) -> str:
        snapshot = self._session.snapshot()
        parts: list[str] = []
        parts.append(f"Current stage: {self._state.current_stage}")
        parts.append(f"Actions taken: {snapshot['actions']}")
        if snapshot.get("pending_diff"):
            parts.append("There is a pending diff waiting for review.")
        if snapshot.get("open_questions"):
            parts.append(f"Open questions: {snapshot['open_questions']}")
        spec_status = snapshot.get("spec_status", "none")
        if spec_status != "none":
            parts.append(f"Spec status: {spec_status}")
        dag = snapshot.get("dag", {})
        if isinstance(dag, dict):
            columns = dag.get("columns", {})
            parts.append(
                f"Board: todo={columns.get('todo', 0)} wip={columns.get('wip', 0)} done={columns.get('done', 0)}"
            )
        if self._session.transcript:
            tail = self._session.transcript[-3:]
            parts.append("Recent actions:")
            for entry in tail:
                parts.append(f"  {entry.get('action', '?')} → {entry.get('status', '?')}")
        return "\n".join(parts)

    def _build_messages(self, user_prompt: str) -> list[dict[str, str]]:
        role = self._role_for_stage(self._state.current_stage)
        system = SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["architect"])
        context = self._build_context()
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Context:\n{context}\n\nTask: {user_prompt}"},
        ]

    async def execute_turn(
        self,
        user_prompt: str,
        *,
        quality_before: dict[str, Any] | None = None,
    ) -> AgentTurnResult:
        role = self._role_for_stage(self._state.current_stage)
        model = self._model_for_role(role)
        messages = self._build_messages(user_prompt)

        quality_before = quality_before or dict(self._state.quality_snapshot)
        started = time.monotonic()

        llm_response = await self._call_llm(model, messages)
        raw_content = llm_response.get("content", "")
        tokens_used = llm_response.get("tokens", 0)

        action_request = self._parse_action(raw_content)
        retries = 0
        while action_request is None and retries < MAX_RETRIES_PER_TURN:
            retries += 1
            error_msg = f"Previous response was not a valid action. Respond with JSON only.\nError: could not parse action from: {raw_content[:200]}"
            messages.append({"role": "assistant", "content": raw_content})
            messages.append({"role": "user", "content": error_msg})
            llm_response = await self._call_llm(model, messages)
            raw_content = llm_response.get("content", "")
            tokens_used += llm_response.get("tokens", 0)
            action_request = self._parse_action(raw_content)

        elapsed = time.monotonic() - started

        if action_request is None:
            turn = self._make_turn(
                role=role,
                model=model,
                prompt=user_prompt,
                raw_response=raw_content,
                elapsed=elapsed,
                tokens=tokens_used,
                retries=retries,
                quality_before=quality_before,
                status="error",
                output=f"Failed to parse action after {MAX_RETRIES_PER_TURN} retries",
            )
            self._state.turns.append(turn)
            self._state.turn_count += 1
            return AgentTurnResult(
                turn_record=turn,
                action_result=ActionResult(status="error", output=turn.output),
                needs_human_input=True,
                human_prompt="Agent could not produce a valid action. Please provide guidance.",
            )

        action_result = self._session.apply_action(action_request)

        quality_after = self._capture_quality()
        turn = self._make_turn(
            role=role,
            model=model,
            prompt=user_prompt,
            action_request=action_request,
            action_result=action_result,
            elapsed=elapsed,
            tokens=tokens_used,
            retries=retries,
            quality_before=quality_before,
            quality_after=quality_after,
        )
        self._state.turns.append(turn)
        self._state.turn_count += 1

        needs_human = self._should_pause(action_result, action_request)
        human_prompt = ""
        if needs_human:
            if action_result.status == "needs_approval":
                human_prompt = "Agent requests approval to apply diff. Use /apply or /reject."
            elif action_result.status == "error":
                human_prompt = f"Action failed: {action_result.output[:200]}"

        return AgentTurnResult(
            turn_record=turn,
            action_result=action_result,
            needs_human_input=needs_human,
            human_prompt=human_prompt,
        )

    def _should_pause(self, result: ActionResult, request: ActionRequest) -> bool:
        if self._config.autonomy == "auto":
            return result.status == "needs_approval"
        if self._config.autonomy == "supervised":
            return result.status in ("needs_approval", "error")
        return True

    def _capture_quality(self) -> dict[str, Any]:
        quality = self._session.dagflow.quality
        if quality is None:
            return {}
        return {
            "tests_passed": quality.tests_passed,
            "coverage_pct": quality.coverage_pct,
            "mutation_score_pct": quality.mutation_score_pct,
            "passed": quality.passed,
        }

    def _make_turn(
        self,
        *,
        role: str,
        model: str,
        prompt: str,
        elapsed: float,
        tokens: int,
        retries: int,
        quality_before: dict[str, Any],
        quality_after: dict[str, Any] | None = None,
        status: str = "ok",
        output: str = "",
        action_request: ActionRequest | None = None,
        action_result: ActionResult | None = None,
        raw_response: str = "",
    ) -> TurnRecord:
        if action_result is not None:
            status = action_result.status
            output = action_result.output
        return TurnRecord(
            turn_id=f"turn_{self._state.turn_count:04d}",
            session_id=self._session_id,
            role=role,
            model=model,
            stage=self._state.current_stage,
            input_prompt=prompt[:2000],
            action_name=action_request.action if action_request else "",
            action_args=action_request.args if action_request else {},
            status=status,
            output=output[:MAX_OBSERVATION_CHARS],
            output_metadata=action_result.metadata if action_result else {},
            quality_before=quality_before,
            quality_after=quality_after or {},
            elapsed_seconds=elapsed,
            tokens_used=tokens,
            retry_count=retries,
        )

    async def _call_llm(self, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        if self._llm_call is not None:
            return await self._llm_call(model, messages)
        return {"content": '{"action": "summarize", "args": {}}', "tokens": 0}

    def _parse_action(self, content: str) -> ActionRequest | None:
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        json_str = _extract_json(text)
        if json_str is None:
            return None
        try:
            return ActionRequest.from_json(json_str)
        except (ValueError, Exception):
            return None


def _extract_json(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


class LLMCallable:
    """Protocol for LLM call injection (testing / Responses API / LiteLLM)."""

    async def __call__(self, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        raise NotImplementedError
