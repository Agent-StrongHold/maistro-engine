"""Typer commands for interactive builder-session tooling."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from maistro_bootstrap.builders.agent_loop import AgentLoopConfig
from maistro_bootstrap.builders.models import load_litellm_models, role_mapping_from_models
from maistro_bootstrap.builders.sandbox import LocalWorktreeSandbox
from maistro_bootstrap.builders.session import BuilderSession
from maistro_bootstrap.builders.store import SessionStore

console = Console()
builders_app = typer.Typer(help="Interactive builders session tooling.")


def register_builders_app(app: typer.Typer) -> None:
    """Attach builder commands under the root installer CLI."""
    app.add_typer(builders_app, name="builders")


def _launch_tui(
    session: BuilderSession,
    roles: object,
    *,
    task: str = "",
    session_id: str = "default",
    config: AgentLoopConfig | None = None,
    autonomy: str = "supervised",
) -> None:
    from maistro_bootstrap.builders.agent_loop import AutonomyLevel as _AL
    from maistro_bootstrap.builders.models import BuilderModelRoles
    from maistro_bootstrap.builders.responses_callable import ResponsesAPICallable
    from maistro_bootstrap.builders.tui import BuildersTUI

    typed_roles = (
        roles
        if isinstance(roles, BuilderModelRoles)
        else BuilderModelRoles(
            architect="default",
            editor="default",
            tester="default",
            fallback="default",
        )
    )
    _autonomy: _AL = autonomy  # type: ignore[assignment]
    loop_config = config or AgentLoopConfig(autonomy=_autonomy)  # pyright: ignore
    app = BuildersTUI(
        session,
        typed_roles,
        task=task,
        session_id=session_id,
        config=loop_config,
    )
    app._runner.set_llm(ResponsesAPICallable())  # type: ignore[arg-type]
    app.run()


_DEFAULT_CONFIGS = [
    Path("litellm_config.yaml"),
    Path("litellm-config.yaml"),
    Path("config/litellm_config.yaml"),
    Path.home() / ".config" / "maistro" / "litellm_config.yaml",
]


def _find_config(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    for candidate in _DEFAULT_CONFIGS:
        if candidate.exists():
            return candidate
    return Path("litellm_config.yaml")


@builders_app.command("session")
def builders_session(
    task: Annotated[
        str | None,
        typer.Argument(help="Task to work on."),
    ] = None,
    repo: Annotated[
        Path,
        typer.Option("--repo", "-r", help="Repo root."),
    ] = Path("."),
    litellm_config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="LiteLLM YAML config path."),
    ] = None,
    autonomy: Annotated[
        str,
        typer.Option("--autonomy", "-a", help="auto | supervised | stage_gated"),
    ] = "supervised",
    session_id: Annotated[
        str,
        typer.Option("--session", "-s", help="Session id."),
    ] = "default",
) -> None:
    """Launch an interactive builder session with TUI."""
    config_path = _find_config(litellm_config)
    models = load_litellm_models(config_path)
    roles = role_mapping_from_models(models)
    initial_task = task or "interactive builder session"

    console.print(
        Panel.fit(
            "\n".join(
                [
                    "[bold]maistro builders[/bold]",
                    f"repo: {repo.resolve()}",
                    f"task: {initial_task}",
                    f"config: {config_path}",
                    f"autonomy: {autonomy}",
                    f"architect: {roles.architect}",
                    f"editor: {roles.editor}",
                    f"tester: {roles.tester}",
                    f"fallback: {roles.fallback}",
                    "",
                    "/diff /test /apply /reject /status /board /quality /exit",
                ]
            ),
        )
    )

    session = BuilderSession(sandbox=LocalWorktreeSandbox(repo))
    _launch_tui(
        session,
        roles,
        task=initial_task,
        session_id=session_id,
        autonomy=autonomy,
    )


@builders_app.command("models")
def builders_models(
    litellm_config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="LiteLLM YAML config."),
    ] = None,
) -> None:
    """Print builder role mapping from the LiteLLM config."""
    config_path = _find_config(litellm_config)
    models = load_litellm_models(config_path)
    roles = role_mapping_from_models(models)
    table = Table(title="Builder model roles")
    table.add_column("role")
    table.add_column("model alias")
    for role, alias in roles.as_rows():
        table.add_row(role, alias)
    console.print(table)


@builders_app.command("list")
def builders_list(
    state_dir: Annotated[
        Path,
        typer.Option("--state-dir", help="Directory containing builder sessions."),
    ] = Path(".maistro-builders"),
) -> None:
    """List persisted builder sessions."""
    table = Table(title="Builder sessions")
    table.add_column("session")
    table.add_column("open")
    table.add_column("todo")
    table.add_column("wip")
    table.add_column("done")
    table.add_column("quality")
    for item in SessionStore(state_dir).list_sessions():
        quality = "pending" if item.quality_passed is None else str(item.quality_passed)
        table.add_row(
            item.session_id,
            str(item.open_questions),
            str(item.todo),
            str(item.wip),
            str(item.done),
            quality,
        )
    console.print(table)


@builders_app.command("board")
def builders_board(
    state_dir: Annotated[
        Path,
        typer.Option("--state-dir", help="Directory containing builder sessions."),
    ] = Path(".maistro-builders"),
    session_id: Annotated[
        str,
        typer.Option("--session", "-s", help="Session id."),
    ] = "default",
    repo: Annotated[
        Path,
        typer.Option("--repo", "-r", help="Repo root."),
    ] = Path("."),
) -> None:
    """Show the Kanban board for a session."""
    session = SessionStore(state_dir).load(session_id, sandbox=LocalWorktreeSandbox(repo))
    _print_board(session)


@builders_app.command("comment")
def builders_comment(
    card_id: Annotated[str, typer.Argument(help="Card id.")],
    body: Annotated[str, typer.Argument(help="Comment body.")],
    state_dir: Annotated[
        Path,
        typer.Option("--state-dir", help="Directory containing builder sessions."),
    ] = Path(".maistro-builders"),
    session_id: Annotated[
        str,
        typer.Option("--session", "-s", help="Session id."),
    ] = "default",
    repo: Annotated[
        Path,
        typer.Option("--repo", "-r", help="Repo root."),
    ] = Path("."),
) -> None:
    """Comment on a board card."""
    store = SessionStore(state_dir)
    session = store.load(session_id, sandbox=LocalWorktreeSandbox(repo))
    session.message_board.add_human_comment(card_id, body)
    store.save(session_id, session)
    console.print(f"commented on {card_id}")


@builders_app.command("move")
def builders_move(
    card_id: Annotated[str, typer.Argument(help="Card id.")],
    status: Annotated[
        str,
        typer.Argument(help="wip | done | resolved"),
    ] = "wip",
    summary: Annotated[
        str,
        typer.Option("--summary", help="Resolution summary."),
    ] = "",
    state_dir: Annotated[
        Path,
        typer.Option("--state-dir", help="Directory containing builder sessions."),
    ] = Path(".maistro-builders"),
    session_id: Annotated[
        str,
        typer.Option("--session", "-s", help="Session id."),
    ] = "default",
    repo: Annotated[
        Path,
        typer.Option("--repo", "-r", help="Repo root."),
    ] = Path("."),
) -> None:
    """Move a board card."""
    store = SessionStore(state_dir)
    session = store.load(session_id, sandbox=LocalWorktreeSandbox(repo))
    if status == "wip":
        session.message_board.start(card_id)
    elif status == "done":
        session.message_board.finish(card_id, summary=summary)
    elif status == "resolved":
        session.message_board.resolve(card_id, resolution=summary)
    else:
        raise typer.BadParameter("status must be: wip, done, resolved")
    store.save(session_id, session)
    console.print(f"moved {card_id} to {status}")


def _print_board(session: BuilderSession) -> None:
    table = Table(title="Builder board")
    table.add_column("status")
    table.add_column("card")
    table.add_column("owner")
    table.add_column("title")
    table.add_column("comments")
    table.add_column("resolution")
    for status, cards in session.message_board.columns().items():
        for card in cards:
            table.add_row(
                status,
                card.card_id,
                card.agent,
                card.question,
                str(len(card.comments)),
                card.resolution,
            )
    for card in session.message_board.open_cards():
        table.add_row(
            "open",
            card.card_id,
            card.agent,
            card.question,
            str(len(card.comments)),
            "",
        )
    console.print(table)


def _print_action_result(result: object) -> None:
    output = getattr(result, "output", "")
    status = getattr(result, "status", "ok")
    style = "green" if status == "ok" else "yellow" if status == "needs_approval" else "red"
    console.print(f"[{style}]{status}[/{style}]")
    if output:
        console.print(output, markup=False, highlight=False)
