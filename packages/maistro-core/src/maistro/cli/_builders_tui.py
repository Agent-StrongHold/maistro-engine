"""Builders interactive app backed by replayable, VM-isolated sessions."""

from __future__ import annotations

# mypy: disable-error-code="misc,untyped-decorator,unused-ignore"
import asyncio
import re
from typing import Any
from uuid import uuid4

from textual import on, work  # type: ignore[import-not-found]
from textual.app import App, ComposeResult  # type: ignore[import-not-found]
from textual.binding import Binding  # type: ignore[import-not-found]
from textual.containers import Horizontal, Vertical  # type: ignore[import-not-found]
from textual.screen import ModalScreen  # type: ignore[import-not-found]
from textual.widgets import (  # type: ignore[import-not-found]
    Button,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
)


class WelcomeScreen(Vertical):
    """Landing screen for new or replayed isolated sessions."""

    def compose(self) -> ComposeResult:
        yield Static(
            "\n  [bold cyan]maistro builders[/bold cyan]\n\n"
            "  Open a repo to start coding in an offline VM.\n"
            "  Paste an approved public HTTPS git URL or replay a recent session.\n",
            id="welcome-title",
        )
        yield Label("  HTTPS repository URL:")
        yield Input(placeholder="https://github.com/org/repo", id="repo-input")
        yield Label("")
        yield Horizontal(
            Button("Open", variant="primary", id="btn-open"),
            Button("Replay", variant="default", id="btn-resume"),
            id="welcome-buttons",
        )
        yield Static("", id="recent-sessions")


class SessionPickerScreen(ModalScreen[str | None]):
    """Modal to pick a durable patch session to replay."""

    BINDINGS = [("escape", "cancel", "Cancel")]  # type: ignore[assignment, misc]  # noqa: RUF012

    def __init__(self, sessions: list[Any]) -> None:
        super().__init__()
        self.sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical(id="session-picker"):
            yield Static("[bold]Replayable sessions[/bold]\n")
            for session in self.sessions:
                label = (
                    f"{session.session_id}  "
                    f"[dim]{session.repo_url}  {session.updated_at[:16]}[/dim]"
                )
                yield Button(label, id=f"pick-{session.session_id}", classes="session-btn")
            yield Button("Cancel", variant="default", id="pick-cancel")

    @on(Button.Pressed, "#pick-cancel")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, ".session-btn")
    def pick(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        self.dismiss(button_id.replace("pick-", "", 1))


class CodingScreen(Vertical):
    """Agent chat and diff viewer for one offline VM session."""

    BINDINGS = [  # type: ignore[assignment, misc]  # noqa: RUF012
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+s", "save_replay", "Save"),
        Binding("ctrl+d", "show_diff", "Diff"),
        Binding("ctrl+a", "apply_changes", "Apply"),
        Binding("ctrl+r", "reject_changes", "Reject"),
    ]

    def __init__(self, session_id: str, repo_url: str, session: Any, store: Any) -> None:
        super().__init__()
        self.session_id = session_id
        self.repo_url = repo_url
        self.session = session
        self.store = store

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Vertical(
                Static(
                    f"[bold]session:[/bold] {self.session_id}  "
                    f"[bold]repo:[/bold] {self.repo_url}  "
                    f"[bold]isolation:[/bold] {self.session.sandbox.backend_name}/"
                    f"{self.session.sandbox.isolation_tier}",
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
        chat.write(
            "[dim]Offline VM session started. Changes are saved as replayable patches.[/dim]"
        )
        self.query_one("#chat-input", Input).focus()

    def on_unmount(self) -> None:
        try:
            self._save_replay()
        finally:
            self.session.sandbox.close()

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

            runner = TurnRunner(session=self.session, config=AgentLoopConfig())
            runner.set_llm(ResponsesAPICallable())  # type: ignore[arg-type]
            messages = [
                {"role": "system", "content": "You are a coding assistant."},
                {"role": "user", "content": text},
            ]
            result = await runner.execute_turn(messages=messages)
            chat.write(f"\n[bold green]agent:[/bold green] {result.get('content', 'done')}")
            await asyncio.to_thread(self._save_replay)
        except ImportError:
            chat.write("[yellow]Agent not available (maistro-bootstrap not installed).[/yellow]")
        except Exception as exc:
            chat.write(f"[red]Error: {exc}[/red]")

    def action_show_diff(self) -> None:
        diff = self.query_one("#diff-viewer", RichLog)
        diff.clear()
        diff.write(self.session.sandbox.diff() or "[dim]No diff yet.[/dim]")

    def action_save_replay(self) -> None:
        chat = self.query_one("#chat-log", RichLog)
        try:
            self._save_replay()
            chat.write("[dim]Replay patch saved.[/dim]")
        except Exception as exc:
            chat.write(f"[red]Failed to save replay patch: {exc}[/red]")

    def action_apply_changes(self) -> None:
        chat = self.query_one("#chat-log", RichLog)
        chat.write("[dim]Apply-to-repo is not enabled; export/review the replay patch.[/dim]")

    def action_reject_changes(self) -> None:
        chat = self.query_one("#chat-log", RichLog)
        chat.write("[dim]Close this session to discard its live VM state.[/dim]")

    def _save_replay(self) -> None:
        self.store.save(
            session_id=self.session_id,
            repo_url=self.repo_url,
            base_commit=self.session.sandbox.base_commit,
            patch=self.session.sandbox.diff(),
        )


class BuildersApp(App[None]):
    """Interactive coding environment with VM isolation and patch replay."""

    TITLE = "maistro builders"
    CSS = """
    #welcome-title { padding: 1 2; }
    #repo-input { margin: 0 2; width: 90%; }
    #welcome-buttons { margin: 0 2; height: 3; }
    #welcome-buttons Button { margin-right: 1; }
    #session-picker { padding: 1 2; border: solid green; width: 80; height: auto; }
    #coding-layout { height: 1fr; }
    #chat-pane { width: 2fr; }
    #diff-pane { width: 1fr; border-left: solid $surface; }
    #chat-log { height: 1fr; }
    #diff-viewer { height: 1fr; }
    #session-bar { padding: 0 1; background: $surface; }
    #diff-title { padding: 0 1; background: $surface; }
    """

    BINDINGS = [("ctrl+q", "quit", "Quit")]  # type: ignore[assignment, misc]  # noqa: RUF012

    def __init__(self) -> None:
        super().__init__()
        from maistro.builders.session_store import BuilderSessionStore

        self._store = BuilderSessionStore()

    def compose(self) -> ComposeResult:
        yield Header()
        yield WelcomeScreen()
        yield Footer()

    def on_mount(self) -> None:
        self._load_recent_sessions()

    @work
    async def _load_recent_sessions(self) -> None:
        from maistro.builders.capabilities import CapabilityState, capability_counts

        sessions = await asyncio.to_thread(self._store.list_sessions)
        recent = self.query_one("#recent-sessions", Static)
        counts = capability_counts()
        posture = (
            f"\n  [dim]Capabilities: {counts[CapabilityState.AVAILABLE]} available, "
            f"{counts[CapabilityState.BROKER_REQUIRED]} require secure brokers, "
            f"{counts[CapabilityState.PROHIBITED]} prohibited.[/dim]"
        )
        if not sessions:
            recent.update(
                "\n  [dim]No replayable sessions. Secure mode requires an available Kata VM runtime.[/dim]"
                + posture
            )
            return
        lines = ["\n  [bold]Replayable sessions:[/bold]"]
        for session in sessions[:5]:
            lines.append(f"  {session.session_id}  [dim]{session.repo_url}[/dim]")
        recent.update("\n".join(lines) + posture)

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
        sessions = self._store.list_sessions()
        if not sessions:
            self.query_one("#recent-sessions", Static).update(
                "\n  [dim]No replayable sessions found.[/dim]"
            )
            return
        self.push_screen(SessionPickerScreen(sessions), self._on_session_picked)

    def _on_session_picked(self, session_id: str | None) -> None:
        if session_id:
            self._replay_session(session_id)

    @work(exclusive=True)
    async def _open_repo(self, repo: str) -> None:
        from maistro.builders.isolated_workspace import IsolatedBuilderSandbox
        from maistro_bootstrap.builders.session import BuilderSession

        session_id = _make_session_id(repo)
        recent = self.query_one("#recent-sessions", Static)
        recent.update("\n  [dim]Cloning in a temporary VM and creating an offline worker...[/dim]")
        try:
            sandbox = await asyncio.to_thread(IsolatedBuilderSandbox.create, repo)
            session = BuilderSession(sandbox=sandbox)
            await asyncio.to_thread(
                self._store.save,
                session_id=session_id,
                repo_url=repo,
                base_commit=sandbox.base_commit,
                patch="",
            )
            self._open_coding_screen(session_id, repo, session)
        except Exception as exc:
            recent.update(f"\n  [red]Failed to create isolated session: {exc}[/red]")

    @work(exclusive=True)
    async def _replay_session(self, session_id: str) -> None:
        from maistro.builders.isolated_workspace import IsolatedBuilderSandbox
        from maistro_bootstrap.builders.session import BuilderSession

        recent = self.query_one("#recent-sessions", Static)
        recent.update("\n  [dim]Replaying patch into a fresh offline VM...[/dim]")
        try:
            saved = await asyncio.to_thread(self._store.get, session_id)
            if saved is None:
                raise KeyError(f"Replay session {session_id!r} does not exist")
            patch = await asyncio.to_thread(self._store.load_patch, session_id)
            sandbox = await asyncio.to_thread(
                IsolatedBuilderSandbox.create,
                saved.repo_url,
                patch=patch,
                base_commit=saved.base_commit,
            )
            self._open_coding_screen(
                saved.session_id,
                saved.repo_url,
                BuilderSession(sandbox=sandbox),
            )
        except Exception as exc:
            recent.update(f"\n  [red]Failed to replay isolated session: {exc}[/red]")

    def _open_coding_screen(self, session_id: str, repo: str, session: Any) -> None:
        welcome = self.query_one(WelcomeScreen)
        welcome.remove()
        self.mount(CodingScreen(session_id, repo, session, self._store))


def _make_session_id(repo_url: str) -> str:
    repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    slug = re.sub(r"[^a-zA-Z0-9-]", "-", repo_name).strip("-")[:80] or "repo"
    return f"{slug}-{uuid4().hex[:8]}"
