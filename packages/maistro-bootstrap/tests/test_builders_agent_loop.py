"""ReAct agent loop tests with mocked LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from maistro_bootstrap.builders.agent_loop import (
    AgentLoopConfig,
    TurnRunner,
    _extract_json,
)
from maistro_bootstrap.builders.models import BuilderModelRoles
from maistro_bootstrap.builders.sandbox import SandboxCommandResult
from maistro_bootstrap.builders.session import BuilderSession


@dataclass
class FakeSandbox:
    files: dict[str, str] = field(default_factory=lambda: {"main.py": "print('hello')"})
    commands: list[list[str]] = field(default_factory=list)

    def read_file(self, path: str) -> str:
        return self.files.get(path, "")

    def write_file(self, path: str, content: str) -> None:
        self.files[path] = content

    def search(self, query: str) -> list[str]:
        return [p for p, c in self.files.items() if query in c]

    def run_command(self, argv: list[str], *, timeout: float) -> SandboxCommandResult:
        self.commands.append(argv)
        return SandboxCommandResult(returncode=0, stdout="ok", stderr="", elapsed_seconds=0.01)

    def diff(self) -> str:
        return "diff --git a/main.py b/main.py\n"


@dataclass
class MockLLM:
    responses: list[str] = field(default_factory=list)
    call_log: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.call_log.append({"model": model, "messages": messages})
        if not self.responses:
            return {"content": '{"action": "summarize", "args": {}}', "tokens": 42}
        return {"content": self.responses.pop(0), "tokens": 42}


def _roles() -> BuilderModelRoles:
    return BuilderModelRoles(
        architect="test-arch",
        editor="test-edit",
        tester="test-test",
        fallback="test-fb",
    )


def _session() -> BuilderSession:
    return BuilderSession(sandbox=FakeSandbox())


def _runner(session: BuilderSession | None = None) -> TurnRunner:
    return TurnRunner(session or _session(), _roles(), session_id="test")


@pytest.mark.asyncio
async def test_execute_turn_parses_valid_action() -> None:
    session = _session()
    runner = _runner(session)
    llm = MockLLM(responses=['{"action": "read_file", "args": {"path": "main.py"}}'])
    runner.set_llm(llm)

    result = await runner.execute_turn("Read the main file")

    assert result.action_result.status == "ok"
    assert result.turn_record.action_name == "read_file"
    assert result.turn_record.role == "architect"
    assert result.turn_record.model == "test-arch"
    assert result.turn_record.succeeded is True
    assert len(runner.state.turns) == 1


@pytest.mark.asyncio
async def test_execute_turn_retries_on_invalid_json() -> None:
    session = _session()
    runner = _runner(session)
    llm = MockLLM(
        responses=[
            "I'll read the file for you.",
            '{"action": "read_file", "args": {"path": "main.py"}}',
        ]
    )
    runner.set_llm(llm)

    result = await runner.execute_turn("Read main")

    assert result.action_result.status == "ok"
    assert result.turn_record.retry_count == 1
    assert len(llm.call_log) == 2


@pytest.mark.asyncio
async def test_execute_turn_fails_after_max_retries() -> None:
    session = _session()
    runner = _runner(session)
    llm = MockLLM(responses=["not json", "still not json", "nope", "never"])
    runner.set_llm(llm)

    result = await runner.execute_turn("Do something")

    assert result.action_result.status == "error"
    assert result.turn_record.retry_count == 3
    assert result.needs_human_input is True


@pytest.mark.asyncio
async def test_execute_turn_captures_quality_delta() -> None:
    session = _session()
    runner = _runner(session)
    llm = MockLLM(responses=['{"action": "read_file", "args": {"path": "main.py"}}'])
    runner.set_llm(llm)
    runner.state.quality_snapshot = {"coverage_pct": 80.0}

    result = await runner.execute_turn(
        "Read file",
        quality_before={"coverage_pct": 80.0},
    )

    assert result.turn_record.quality_before == {"coverage_pct": 80.0}


@pytest.mark.asyncio
async def test_autonomy_auto_only_pauses_on_approval() -> None:
    session = _session()
    config = AgentLoopConfig(autonomy="auto")
    runner = TurnRunner(session, _roles(), session_id="test", config=config)
    llm = MockLLM(responses=['{"action": "read_file", "args": {"path": "main.py"}}'])
    runner.set_llm(llm)

    result = await runner.execute_turn("Read")
    assert result.needs_human_input is False


@pytest.mark.asyncio
async def test_autonomy_supervised_pauses_on_error() -> None:
    session = _session()
    config = AgentLoopConfig(autonomy="supervised")
    runner = TurnRunner(session, _roles(), session_id="test", config=config)
    llm = MockLLM(responses=['{"action": "run_command", "args": {"argv": ["false"]}}'])
    runner.set_llm(llm)

    sandbox = session.sandbox
    assert hasattr(sandbox, "run_command")
    original_run = sandbox.run_command

    def _failing_run(argv: list[str], *, timeout: float) -> SandboxCommandResult:
        return SandboxCommandResult(returncode=1, stdout="", stderr="fail", elapsed_seconds=0.01)

    sandbox.run_command = _failing_run  # type: ignore[assignment]
    result = await runner.execute_turn("Run tests")
    sandbox.run_command = original_run  # type: ignore[assignment]

    assert result.needs_human_input is True


@pytest.mark.asyncio
async def test_autonomy_stage_gated_always_pauses() -> None:
    session = _session()
    config = AgentLoopConfig(autonomy="stage_gated")
    runner = TurnRunner(session, _roles(), session_id="test", config=config)
    llm = MockLLM(responses=['{"action": "read_file", "args": {"path": "main.py"}}'])
    runner.set_llm(llm)

    result = await runner.execute_turn("Read")
    assert result.needs_human_input is True


@pytest.mark.asyncio
async def test_role_for_stage_maps_correctly() -> None:
    runner = _runner()
    assert runner._role_for_stage("spec") == "architect"
    assert runner._role_for_stage("plan") == "architect"
    assert runner._role_for_stage("implement") == "editor"
    assert runner._role_for_stage("test") == "tester"
    assert runner._role_for_stage("audit") == "architect"


@pytest.mark.asyncio
async def test_build_context_includes_session_state() -> None:
    session = _session()
    session.apply_action(
        __import__("maistro_bootstrap.builders.actions", fromlist=["ActionRequest"]).ActionRequest(
            action="read_file",
            args={"path": "main.py"},
        )
    )
    runner = _runner(session)
    context = runner._build_context()

    assert "spec" in context
    assert "Actions taken: 1" in context


def test_extract_json_finds_first_balanced_object() -> None:
    assert _extract_json('here is {"a": 1} and {"b": 2}') == '{"a": 1}'
    assert _extract_json('```json\n{"action": "read"}\n```') == '{"action": "read"}'
    assert _extract_json("no json here") is None
    assert _extract_json('nested {"a": {"b": 2}} obj') == '{"a": {"b": 2}}'


@pytest.mark.asyncio
async def test_turn_record_tokens_accumulate_on_retry() -> None:
    session = _session()
    runner = _runner(session)
    llm = MockLLM(
        responses=[
            "bad",
            '{"action": "read_file", "args": {"path": "main.py"}}',
        ]
    )
    runner.set_llm(llm)

    result = await runner.execute_turn("Read")
    assert result.turn_record.tokens_used == 84  # 42 * 2 calls
