"""Builders interactive app — Textual TUI.

Flow:
  1. Welcome screen: "Open a repo" (paste URL/path) or "Resume session" (pick from list)
  2. App clones repo into a dev container (or resumes existing)
  3. Drops into the coding session TUI (agent loop + diff viewer)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static


class WelcomeScreen(Vertical):
    """Landing screen — pick a repo or resume a session."""

    def compose(self) -> ComposeResult:
        yield Static(
            "\n  [bold cyan]maistro builders[/bold cyan]\n\n"
            "  Open a repo to start coding.\n"
            "  Paste a git URL, a local path, or pick a recent session.\n",
            id="welcome-title",
        )
        yield Label("  Repo URL or path:")
        yield Input(
            placeholder="https://github.com/org/repo  or  /path/to/local/repo",
            id="repo-input",
        )
        yield Label("")
        yield Horizontal(
            Button("Open", variant="primary", id="btn-open"),
            Button("Resume", variant="default", id="btn-resume"),
            id="welcome-buttons",
        )
        yield Static("", id="recent-sessions")


class SessionPickerScreen(ModalScreen[str | None]):
    """Modal to pick a recent session to resume."""

    BINDINGS = [("escape", "cancel", "Cancel")]  # type: ignore[assignment, misc]  # noqa: RUF012

    def __init__(self, sessions: list[Any]) -> None:
        super().__init__()
        self.sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical(id="session-picker"):
            yield Static("[bold]Recent sessions[/bold]\n")
            for s in self.sessions:
                status_icon = {"running": "🟢", "stopped": "⚪"}.get(s.status.value, "⚫")
                label = (
                    f"{status_icon} {s.name}  "
                    f"[dim]{s.labels.get('maistro.repo_url', '?')}  "
                    f"{s.created.strftime('%Y-%m-%d %H:%M')}[/dim]"
                )
                yield Button(label, id=f"pick-{s.name}", classes="session-btn")
            yield Button("Cancel", variant="default", id="pick-cancel")

    @on(Button.Pressed, "#pick-cancel")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, ".session-btn")
    def pick(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        session_id = btn_id.replace("pick-", "", 1)
        self.dismiss(session_id)


class CodingScreen(Vertical):
    """The actual coding session — agent chat + diff viewer."""

    BINDINGS = [  # type: ignore[assignment, misc]  # noqa: RUF012
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+d", "show_diff", "Diff"),
        Binding("ctrl+a", "apply_changes", "Apply"),
        Binding("ctrl+r", "reject_changes", "Reject"),
    ]

    def __init__(self, session_id: str, repo_url: str) -> None:
        super().__init__()
        self.session_id = session_id
        self.repo_url = repo_url

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Vertical(
                Static(
                    f"[bold]session:[/bold] {self.session_id}  [bold]repo:[/bold] {self.repo_url}",
                    id="session-bar",
                ),
                RichLog(id="chat-log", highlight=True, markup=True),
                Input(placeholder="Tell the agent what to do...", id="chat-input"),
                id="chat-pane",
            ),
            Vertical(
                Static("[bold]diff[/bold]", id="diff-title"),
                RichLog(id="diff-viewer", highlight=True, markup=True),
                id="diff-pane",
            ),
            id="coding-layout",
        )

    def on_mount(self) -> None:
        chat = self.query_one("#chat-log", RichLog)
        chat.write("[dim]Session started. Type a task or ask a question.[/dim]")
        self.query_one("#chat-input", Input).focus()

    @on(Input.Submitted, "#chat-input")
    def on_chat_input(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        chat = self.query_one("#chat-log", RichLog)
        chat.write(f"\n[bold cyan]you:[/bold cyan] {text}")
        chat.write("[dim]agent is thinking...[/dim]")
        self._run_agent_turn(text)

    @work(exclusive=True)
    async def _run_agent_turn(self, text: str) -> None:
        chat = self.query_one("#chat-log", RichLog)
        try:
            from maistro_bootstrap.builders.agent_loop import AgentLoopConfig, TurnRunner
            from maistro_bootstrap.builders.responses_callable import ResponsesAPICallable
            from maistro_bootstrap.builders.sandbox import LocalWorktreeSandbox
            from maistro_bootstrap.builders.session import BuilderSession

            session = BuilderSession(sandbox=LocalWorktreeSandbox(Path(".")))
            runner = TurnRunner(session=session, config=AgentLoopConfig())
            runner.set_llm(ResponsesAPICallable())  # type: ignore[arg-type]

            messages = [
                {"role": "system", "content": "You are a coding assistant."},
                {"role": "user", "content": text},
            ]
            result = await runner.execute_turn(messages=messages)

            chat.write(f"\n[bold green]agent:[/bold green] {result.get('content', 'done')}")
        except ImportError:
            chat.write("[yellow]Agent not available (maistro-bootstrap not installed).[/yellow]")
            chat.write(f"[dim]You said: {text}[/dim]")
        except Exception as exc:
            chat.write(f"[red]Error: {exc}[/red]")

    def action_show_diff(self) -> None:
        diff = self.query_one("#diff-viewer", RichLog)
        diff.write("[dim]No diff yet.[/dim]")

    def action_apply_changes(self) -> None:
        chat = self.query_one("#chat-log", RichLog)
        chat.write("[dim]No changes to apply.[/dim]")

    def action_reject_changes(self) -> None:
        chat = self.query_one("#chat-log", RichLog)
        chat.write("[dim]No changes to reject.[/dim]")


class BuildersApp(App[None]):
    """maistro builders — interactive AI coding environment."""

    TITLE = "maistro builders"
    CSS = """
    #welcome-title { padding: 1 2; }
    #repo-input { margin: 0 2; width: 90%; }
    #welcome-buttons { margin: 0 2; height: 3; }
    #welcome-buttons Button { margin-right: 1; }
    #session-picker { padding: 1 2; border: solid green; width: 60; height: auto; }
    #coding-layout { height: 1fr; }
    #chat-pane { width: 2fr; }
    #diff-pane { width: 1fr; border-left: solid $surface; }
    #chat-log { height: 1fr; }
    #diff-viewer { height: 1fr; }
    #session-bar { padding: 0 1; background: $surface; }
    #diff-title { padding: 0 1; background: $surface; }
    """

    BINDINGS = [("ctrl+q", "quit", "Quit")]  # type: ignore[assignment, misc]  # noqa: RUF012

    def compose(self) -> ComposeResult:
        yield Header()
        yield WelcomeScreen()
        yield Footer()

    def on_mount(self) -> None:
        self._load_recent_sessions()

    @work
    async def _load_recent_sessions(self) -> None:
        try:
            from maistro.cli._container.lifecycle import SessionLifecycle

            lifecycle = SessionLifecycle()
            sessions = lifecycle.list_sessions()
            if sessions:
                lines = ["\n  [bold]Recent sessions:[/bold]"]
                for s in sessions[:5]:
                    icon = {"running": "🟢", "stopped": "⚪"}.get(s.status.value, "⚫")
                    lines.append(
                        f"  {icon} {s.name}  [dim]{s.labels.get('maistro.repo_url', '?')}[/dim]"
                    )
                recent = self.query_one("#recent-sessions", Static)
                recent.update("\n".join(lines))
        except Exception:
            pass

    @on(Input.Submitted, "#repo-input")
    def on_repo_submitted(self, event: Input.Submitted) -> None:
        repo = event.value.strip()
        if repo:
            self._open_repo(repo)

    @on(Button.Pressed, "#btn-open")
    def on_open_button(self) -> None:
        repo = self.query_one("#repo-input", Input).value.strip()
        if repo:
            self._open_repo(repo)

    @on(Button.Pressed, "#btn-resume")
    def on_resume_button(self) -> None:
        self._show_session_picker()

    def _show_session_picker(self) -> None:
        try:
            from maistro.cli._container.lifecycle import SessionLifecycle

            sessions = SessionLifecycle().list_sessions()
            if not sessions:
                self.query_one("#recent-sessions", Static).update(
                    "\n  [dim]No sessions found.[/dim]"
                )
                return
            self.push_screen(SessionPickerScreen(sessions), self._on_session_picked)
        except Exception as exc:
            self.query_one("#recent-sessions", Static).update(f"\n  [red]Error: {exc}[/red]")

    def _on_session_picked(self, session_id: str | None) -> None:
        if session_id:
            self._open_coding_screen(session_id, f"resumed:{session_id}")

    @work
    async def _open_repo(self, repo: str) -> None:
        from maistro.cli._container.lifecycle import SessionLifecycle

        lifecycle = SessionLifecycle()
        session_id = SessionLifecycle.make_session_id(repo)

        try:
            lifecycle.create_session(
                session_id=session_id,
                repo_url=repo,
            )
            self._open_coding_screen(session_id, repo)
        except Exception as exc:
            recent = self.query_one("#recent-sessions", Static)
            recent.update(f"\n  [red]Failed to create session: {exc}[/red]")

    def _open_coding_screen(self, session_id: str, repo: str) -> None:
        welcome = self.query_one(WelcomeScreen)
        welcome.remove()
        self.mount(CodingScreen(session_id, repo))
