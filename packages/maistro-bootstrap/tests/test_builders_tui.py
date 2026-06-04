"""Textual TUI plumbing tests for builder sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from maistro_bootstrap.builders.actions import ActionResult
from maistro_bootstrap.builders.models import BuilderModelRoles
from maistro_bootstrap.builders.tui import (
    BuildersTUI,
    ChatPane,
    DiffViewer,
    StageIndicator,
    _render_diff,
)
from maistro_bootstrap.builders.turn_record import TurnRecord


@dataclass
class FakeQuality:
    passed: bool


class FakeDagFlow:
    quality: FakeQuality | None = None


class FakeSandbox:
    def __init__(self, diff: str = "") -> None:
        self._diff = diff

    def diff(self) -> str:
        return self._diff


class FakeSession:
    def __init__(self) -> None:
        self.sandbox = FakeSandbox("diff --git a/file b/file\n+added\n-removed")
        self.dagflow = FakeDagFlow()
        self.approved_to_apply = False
        self.commands: list[str] = []

    def apply_slash_command(self, command: str) -> ActionResult:
        self.commands.append(command)
        if command == "/apply":
            status = "ok" if self.approved_to_apply else "error"
            return ActionResult(status=status, output=f"{status}: apply")
        if command == "/test":
            self.dagflow.quality = FakeQuality(passed=True)
        if command == "/reject":
            return ActionResult(status="ok", output="rejected")
        return ActionResult(status="needs_approval", output=f"ran {command}")


class FakeChatPane:
    def __init__(self) -> None:
        self.agent_messages: list[tuple[str, str]] = []
        self.system_messages: list[str] = []

    def append_agent(self, label: str, content: str) -> None:
        self.agent_messages.append((label, content))

    def append_system(self, content: str) -> None:
        self.system_messages.append(content)


class FakeDiffViewer:
    def __init__(self) -> None:
        self.diff_content = ""


class FakeStageIndicator:
    def __init__(self) -> None:
        self.stage = ""
        self.role = ""
        self.quality_status = ""


class FakeRunner:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.state = type("State", (), {"current_stage": "implement"})()
        self.prompts: list[str] = []

    async def execute_turn(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        return self.result

    def _role_for_stage(self, stage: str) -> str:
        return {"implement": "editor", "test": "tester"}.get(stage, "architect")


def _roles() -> BuilderModelRoles:
    return BuilderModelRoles(
        architect="arch-model",
        editor="edit-model",
        tester="test-model",
        fallback="fallback-model",
    )


def _app() -> tuple[BuildersTUI, FakeSession, FakeChatPane, FakeDiffViewer, FakeStageIndicator]:
    session = FakeSession()
    app = BuildersTUI(session, _roles(), task="build the thing")
    chat = FakeChatPane()
    diff = FakeDiffViewer()
    stage = FakeStageIndicator()
    app._chat_pane = chat  # type: ignore[assignment]
    app._diff_viewer = diff  # type: ignore[assignment]
    app._stage_indicator = stage  # type: ignore[assignment]
    return app, session, chat, diff, stage


def test_render_diff_styles_and_truncates_long_content() -> None:
    assert _render_diff("   ") == "[dim](no changes yet)[/dim]"

    rendered = _render_diff("--- old\n+++ new\n@@ hunk\n-added\n+added\n context")
    assert "[bold]--- old[/bold]" in rendered
    assert "[bold]+++ new[/bold]" in rendered
    assert "[cyan]@@ hunk[/cyan]" in rendered
    assert "[red]-added[/red]" in rendered
    assert "[green]+added[/green]" in rendered

    long_rendered = _render_diff("\n".join(f"line {i}" for i in range(502)))
    assert "[dim]... 2 more lines[/dim]" in long_rendered


def test_on_mount_announces_session_and_initial_task() -> None:
    app, _session, chat, _diff, _stage = _app()

    app.on_mount()

    assert "Task: build the thing" in chat.system_messages[0]
    assert "Agent loop ready" in chat.system_messages[1]


def test_slash_command_records_result_and_refreshes_diff() -> None:
    app, session, chat, diff, _stage = _app()

    app._handle_slash("/diff")

    assert session.commands == ["/diff"]
    assert chat.agent_messages == [("[yellow]needs_approval[/yellow]", "ran /diff")]
    assert diff.diff_content == "diff --git a/file b/file\n+added\n-removed"


def test_actions_apply_reject_diff_and_test_use_session_commands() -> None:
    app, session, chat, _diff, _stage = _app()

    app.action_show_diff()
    app.action_run_tests()
    app.action_apply()
    app.action_reject()

    assert session.approved_to_apply is True
    assert session.commands == ["/test", "/apply", "/reject"]
    assert ("diff", "diff --git a/file b/file\n+added\n-removed") in chat.agent_messages
    assert ("test", "ran /test") in chat.agent_messages
    assert ("apply", "ok: apply") in chat.agent_messages
    assert ("reject", "rejected") in chat.agent_messages


def test_refresh_stage_reflects_runner_role_and_quality() -> None:
    app, session, _chat, _diff, stage = _app()
    session.dagflow.quality = FakeQuality(passed=False)
    app._runner.state.current_stage = "test"

    app._refresh_stage()

    assert stage.stage == "test"
    assert stage.role == "tester"
    assert stage.quality_status == "fail"


def test_refresh_diff_ignores_blank_diff() -> None:
    app, session, _chat, diff, _stage = _app()
    session.sandbox = FakeSandbox("")
    diff.diff_content = "keep me"

    app._refresh_diff()

    assert diff.diff_content == "keep me"


def test_prompt_dispatch_runs_worker_and_refreshes_views() -> None:
    app, _session, chat, diff, stage = _app()
    turn = TurnRecord(
        turn_id="turn_0001",
        session_id="session",
        role="editor",
        model="edit-model",
        stage="implement",
        action_name="show_diff",
        status="ok",
    )
    result = type(
        "Result",
        (),
        {
            "turn_record": turn,
            "action_result": ActionResult(status="ok", output="finished"),
            "needs_human_input": False,
            "human_prompt": "",
        },
    )()
    runner = FakeRunner(result)
    app._runner = runner  # type: ignore[assignment]

    def run_worker(coro: Any) -> object:
        asyncio.run(coro)
        return object()

    app.run_worker = run_worker  # type: ignore[method-assign]

    app._handle_prompt("please continue")

    assert runner.prompts == ["please continue"]
    assert chat.system_messages == ["Processing..."]
    assert ("[green]show_diff[/green]", "finished") in chat.agent_messages
    assert diff.diff_content == "diff --git a/file b/file\n+added\n-removed"
    assert stage.stage == "implement"
    assert stage.role == "editor"


def test_prompt_dispatch_surfaces_human_prompt_on_approval() -> None:
    app, _session, chat, _diff, _stage = _app()
    turn = TurnRecord(
        turn_id="turn_0001",
        session_id="session",
        role="editor",
        model="edit-model",
        stage="implement",
        action_name="apply_diff",
        status="needs_approval",
    )
    result = type(
        "Result",
        (),
        {
            "turn_record": turn,
            "action_result": ActionResult(status="needs_approval", output="approve?"),
            "needs_human_input": True,
            "human_prompt": "Use /apply or /reject.",
        },
    )()
    app._runner = FakeRunner(result)  # type: ignore[assignment]
    app.run_worker = lambda coro: asyncio.run(coro)  # type: ignore[method-assign]

    app._handle_prompt("apply it")

    assert ("[yellow]apply_diff[/yellow]", "approve?") in chat.agent_messages
    assert "Use /apply or /reject." in chat.system_messages


def test_user_message_routes_exit_slash_and_prompt() -> None:
    app, _session, _chat, _diff, _stage = _app()
    calls: list[str] = []

    app.action_quit = lambda: calls.append("quit")  # type: ignore[method-assign]
    app._handle_slash = lambda command: calls.append(f"slash:{command}")  # type: ignore[method-assign]
    app._handle_prompt = lambda prompt: calls.append(f"prompt:{prompt}")  # type: ignore[method-assign]

    app.on_chat_pane_user_message(ChatPane.UserMessage("/exit"))
    app.on_chat_pane_user_message(ChatPane.UserMessage("/board"))
    app.on_chat_pane_user_message(ChatPane.UserMessage("keep going"))

    assert calls == ["quit", "slash:/board", "prompt:keep going"]


def test_chat_pane_appends_and_posts_non_blank_messages() -> None:
    pane = ChatPane()
    writes: list[str] = []
    posted: list[str] = []
    input_box = type("InputBox", (), {"value": "  hello  ", "focus": lambda self: None})()
    pane._input = input_box  # type: ignore[assignment]
    pane._log = type("Log", (), {"write": lambda self, text: writes.append(text)})()  # type: ignore[assignment]
    pane.post_message = lambda message: posted.append(message.text)  # type: ignore[method-assign]

    pane.on_mount()
    pane.append_system("ready")
    pane.append_agent("agent", "done")
    pane.on_input_submitted(type("Submitted", (), {"value": "  hello  "})())

    assert "[dim]ready[/dim]" in writes
    assert any("[bold cyan]agent[/bold cyan]: done" in item for item in writes)
    assert any("[bold cyan]you[/bold cyan]: hello" in item for item in writes)
    assert posted == ["hello"]
    assert input_box.value == ""


def test_chat_pane_ignores_blank_submission() -> None:
    pane = ChatPane()
    posted: list[str] = []
    pane.post_message = lambda message: posted.append(message.text)  # type: ignore[method-assign]

    pane.on_input_submitted(type("Submitted", (), {"value": "   "})())

    assert posted == []


def test_widget_watchers_delegate_to_update() -> None:
    updates: list[str] = []
    diff_widget = DiffViewer()
    diff_widget.update = lambda text: updates.append(text)  # type: ignore[method-assign]
    diff_widget.watch_diff_content("+added")
    assert updates == ["[green]+added[/green]"]

    stage_widget = StageIndicator()
    stage_widget.update = lambda text: updates.append(text)  # type: ignore[method-assign]
    stage_widget.stage = "test"
    stage_widget.role = "tester"
    stage_widget.quality_status = "pass"
    stage_widget.watch_stage("test")
    stage_widget.watch_role("tester")
    stage_widget.watch_quality_status("pass")

    assert updates[-1] == (
        " Stage: [bold]test[/bold]  Role: [bold]tester[/bold]  Quality: pass"
    )
