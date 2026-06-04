"""Textual TUI for interactive builder sessions.

Two-pane layout: chat area (left) + diff viewer (right).
Status bar shows DAG stage, model role, quality gate state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    Footer,
    Header,
    Input,
    RichLog,
    Static,
)

from maistro_bootstrap.builders.agent_loop import AgentLoopConfig, TurnRunner
from maistro_bootstrap.builders.models import BuilderModelRoles
from maistro_bootstrap.builders.session import BuilderSession


class DiffViewer(Static):
    """Right pane showing syntax-highlighted unified diff."""

    diff_content: reactive[str] = reactive("")

    def watch_diff_content(self, content: str) -> None:
        self.update(_render_diff(content))


class StageIndicator(Static):
    """Status bar showing current stage, role, and quality."""

    stage: reactive[str] = reactive("spec")
    role: reactive[str] = reactive("architect")
    quality_status: reactive[str] = reactive("pending")

    def watch_stage(self, stage: str) -> None:
        self._refresh()

    def watch_role(self, role: str) -> None:
        self._refresh()

    def watch_quality_status(self, quality: str) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self.update(
            f" Stage: [bold]{self.stage}[/bold]  "
            f"Role: [bold]{self.role}[/bold]  "
            f"Quality: {self.quality_status}"
        )


class ChatPane(Vertical):
    """Left pane with chat log and input."""

    class UserMessage(Message):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    class ActionRequested(Message):
        def __init__(self, action_text: str) -> None:
            self.action_text = action_text
            super().__init__()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._log: RichLog | None = None
        self._input: Input | None = None

    def compose(self) -> ComposeResult:
        self._log = RichLog(id="chat-log", highlight=True, markup=True)
        yield self._log
        self._input = Input(placeholder="Type a command or prompt...", id="chat-input")
        yield self._input

    def on_mount(self) -> None:
        if self._input is not None:
            self._input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        if self._input is not None:
            self._input.value = ""
        self._append_chat("you", text)
        self.post_message(self.UserMessage(text))

    def append_agent(self, label: str, content: str) -> None:
        self._append_chat(label, content)

    def append_system(self, content: str) -> None:
        if self._log is not None:
            self._log.write(f"[dim]{content}[/dim]")

    def _append_chat(self, speaker: str, content: str) -> None:
        if self._log is not None:
            ts = datetime.now(UTC).strftime("%H:%M:%S")
            self._log.write(f"[{ts}] [bold cyan]{speaker}[/bold cyan]: {content}")


class BuildersTUI(App[None]):
    """Interactive builders session with chat + diff panes."""

    TITLE = "maistro builders"
    CSS = """
    #main-container {
        layout: horizontal;
        height: 1fr;
    }
    #chat-pane {
        width: 2fr;
        height: 1fr;
    }
    #diff-pane {
        width: 1fr;
        height: 1fr;
        border-left: solid green;
        padding: 0 1;
    }
    #stage-bar {
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    #chat-log {
        height: 1fr;
        border: solid $primary;
    }
    #chat-input {
        dock: bottom;
        height: 3;
    }
    """

    BINDINGS: list[Binding] = [  # type: ignore[assignment, misc]  # noqa: RUF012
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+d", "show_diff", "Diff"),
        Binding("ctrl+t", "run_tests", "Test"),
        Binding("ctrl+a", "apply", "Apply"),
        Binding("ctrl+r", "reject", "Reject"),
    ]

    def __init__(
        self,
        session: BuilderSession,
        roles: BuilderModelRoles,
        *,
        task: str = "",
        session_id: str = "default",
        config: AgentLoopConfig | None = None,
    ) -> None:
        super().__init__()
        self._session = session
        self._roles = roles
        self._initial_task = task
        self._session_id = session_id
        self._config = config or AgentLoopConfig()
        self._runner = TurnRunner(
            session,
            roles,
            session_id=session_id,
            config=self._config,
        )
        self._chat_pane: ChatPane | None = None
        self._diff_viewer: DiffViewer | None = None
        self._stage_indicator: StageIndicator | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            self._chat_pane = ChatPane(id="chat-pane")
            yield self._chat_pane
            self._diff_viewer = DiffViewer(id="diff-pane")
            self._diff_viewer.diff_content = "(no changes yet)"
            yield self._diff_viewer
        self._stage_indicator = StageIndicator(id="stage-bar")
        yield self._stage_indicator
        yield Footer()

    def on_mount(self) -> None:
        if self._chat_pane is not None:
            self._chat_pane.append_system(
                f"Session started. Task: {self._initial_task or 'interactive'}\n"
                f"Commands: /diff /test /apply /reject /status /board /quality /exit\n"
                f"Or type a natural language prompt."
            )
        if (
            self._initial_task
            and self._runner.state.current_stage == "spec"
            and self._chat_pane is not None
        ):
            self._chat_pane.append_system(
                "Agent loop ready. Press Enter or type a prompt to start."
            )

    def on_chat_pane_user_message(self, message: ChatPane.UserMessage) -> None:
        text = message.text
        if text in ("/exit", "exit", "quit"):
            self.action_quit()  # type: ignore[unused-coroutine]
            return
        if text.startswith("/"):
            self._handle_slash(text)
            return
        self._handle_prompt(text)

    def _handle_slash(self, command: str) -> None:
        result = self._session.apply_slash_command(command)
        if self._chat_pane is not None:
            style = (
                "green"
                if result.status == "ok"
                else "yellow"
                if result.status == "needs_approval"
                else "red"
            )
            self._chat_pane.append_agent(f"[{style}]{result.status}[/{style}]", result.output)
        if command in ("/diff", "/test"):
            self._refresh_diff()

    def _handle_prompt(self, prompt: str) -> None:
        if self._chat_pane is not None:
            self._chat_pane.append_system("Processing...")

        async def _run() -> None:
            result = await self._runner.execute_turn(prompt)
            if self._chat_pane is not None:
                action_label = result.turn_record.action_name or "(no action)"
                style = (
                    "green"
                    if result.action_result.status == "ok"
                    else "yellow"
                    if result.action_result.status == "needs_approval"
                    else "red"
                )
                self._chat_pane.append_agent(
                    f"[{style}]{action_label}[/{style}]",
                    result.action_result.output[:2000],
                )
                if result.needs_human_input and result.human_prompt:
                    self._chat_pane.append_system(result.human_prompt)
            self._refresh_diff()
            self._refresh_stage()

        _worker = self.run_worker(_run())

    def _refresh_diff(self) -> None:
        diff = self._session.sandbox.diff()
        if self._diff_viewer is not None and diff.strip():
            self._diff_viewer.diff_content = diff

    def _refresh_stage(self) -> None:
        stage = self._runner.state.current_stage
        role = self._runner._role_for_stage(stage)
        quality = self._session.dagflow.quality
        quality_str = "pending" if quality is None else ("pass" if quality.passed else "fail")
        if self._stage_indicator is not None:
            self._stage_indicator.stage = stage
            self._stage_indicator.role = role
            self._stage_indicator.quality_status = quality_str

    def action_show_diff(self) -> None:
        self._refresh_diff()
        diff = self._session.sandbox.diff()
        if self._chat_pane is not None:
            self._chat_pane.append_agent("diff", diff[:2000] if diff.strip() else "(no changes)")

    def action_run_tests(self) -> None:
        result = self._session.apply_slash_command("/test")
        if self._chat_pane is not None:
            self._chat_pane.append_agent("test", result.output[:2000])

    def action_apply(self) -> None:
        self._session.approved_to_apply = True
        result = self._session.apply_slash_command("/apply")
        if self._chat_pane is not None:
            self._chat_pane.append_agent(
                "apply" if result.status == "ok" else "apply-failed",
                result.output,
            )

    def action_reject(self) -> None:
        result = self._session.apply_slash_command("/reject")
        if self._chat_pane is not None:
            self._chat_pane.append_agent("reject", result.output)


def _render_diff(content: str) -> str:
    if not content.strip():
        return "[dim](no changes yet)[/dim]"
    lines = content.split("\n")
    rendered: list[str] = []
    for line in lines[:500]:
        if line.startswith("+++") or line.startswith("---"):
            rendered.append(f"[bold]{line}[/bold]")
        elif line.startswith("+"):
            rendered.append(f"[green]{line}[/green]")
        elif line.startswith("-"):
            rendered.append(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            rendered.append(f"[cyan]{line}[/cyan]")
        else:
            rendered.append(line)
    if len(lines) > 500:
        rendered.append(f"[dim]... {len(lines) - 500} more lines[/dim]")
    return "\n".join(rendered)
