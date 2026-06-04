"""`maistro builders` subcommand — interactive coding sessions.

Creates an isolated dev container (Docker/Podman), clones the target repo,
and launches the Textual TUI for an interactive agent session.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from rich.console import Console
from rich.panel import Panel
from typer import Typer

app = Typer(help="Interactive builder coding sessions.")
console = Console()


@app.command("session")
def builders_session(
    task: Annotated[
        str | None,
        typer.Argument(help="Task description."),
    ] = None,
    repo: Annotated[
        str,
        typer.Option("--repo", "-r", help="Git URL or local path."),
    ] = ".",
    autonomy: Annotated[
        str,
        typer.Option("--autonomy", "-a", help="auto | supervised | stage_gated"),
    ] = "supervised",
    ttl: Annotated[
        int,
        typer.Option("--ttl", help="Session TTL in hours."),
    ] = 72,
    image: Annotated[
        str,
        typer.Option("--image", help="Container image."),
    ] = "maistro-builders:latest",
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Default model alias."),
    ] = None,
) -> None:
    """Launch an interactive builder session in an isolated container."""
    from maistro.cli._container.lifecycle import SessionLifecycle

    lifecycle = SessionLifecycle()
    session_id = SessionLifecycle.make_session_id(repo if repo != "." else "local")

    task_text = task or "interactive builder session"

    console.print(
        Panel.fit(
            "\n".join(
                [
                    "[bold]maistro builders[/bold]",
                    f"session: {session_id}",
                    f"repo: {repo}",
                    f"task: {task_text}",
                    f"autonomy: {autonomy}",
                    f"ttl: {ttl}h",
                    f"image: {image}",
                    "",
                    "Creating dev container...",
                ]
            )
        )
    )

    info = lifecycle.create_session(
        session_id=session_id,
        repo_url=repo,
        task=task_text,
        ttl_hours=ttl,
        image=image,
    )

    console.print(f"[green]Container {info.short_id} running[/green]")

    try:
        _launch_tui_in_container(info, task_text, autonomy, model)
    except KeyboardInterrupt:
        console.print("\n[yellow]Session paused. Resume with:[/yellow]")
        console.print(f"  [bold]maistro builders resume {session_id}[/bold]")
        lifecycle.stop_session(session_id)


@app.command("resume")
def builders_resume(
    session_id: Annotated[
        str,
        typer.Argument(help="Session ID to resume."),
    ],
) -> None:
    """Resume a stopped builder session."""
    from maistro.cli._container.lifecycle import SessionLifecycle

    lifecycle = SessionLifecycle()
    console.print(f"[bold]Resuming session {session_id}...[/bold]")

    info = lifecycle.resume_session(session_id)
    console.print(f"[green]Container {info.short_id} running[/green]")

    task = info.labels.get("maistro.task", "resumed session")
    _launch_tui_in_container(info, task, "supervised", None)


@app.command("stop")
def builders_stop(
    session_id: Annotated[
        str,
        typer.Argument(help="Session ID to stop."),
    ],
) -> None:
    """Stop a running builder session."""
    from maistro.cli._container.lifecycle import SessionLifecycle

    lifecycle = SessionLifecycle()
    lifecycle.stop_session(session_id)
    console.print(f"[green]Session {session_id} stopped.[/green]")


@app.command("list")
def builders_list() -> None:
    """List all builder sessions."""
    from maistro.cli._container.lifecycle import SessionLifecycle

    lifecycle = SessionLifecycle()
    sessions = lifecycle.list_sessions()

    if not sessions:
        console.print("[dim]No builder sessions.[/dim]")
        return

    from rich.table import Table

    table = Table(title="Builder sessions")
    table.add_column("session")
    table.add_column("status")
    table.add_column("image")
    table.add_column("repo")
    table.add_column("task")
    table.add_column("created")

    for info in sessions:
        table.add_row(
            info.name,
            info.status.value,
            info.image,
            info.labels.get("maistro.repo_url", "?"),
            info.labels.get("maistro.task", "")[:40],
            info.created.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@app.command("archive")
def builders_archive(
    session_id: Annotated[
        str,
        typer.Argument(help="Session ID to archive."),
    ],
) -> None:
    """Archive a session (remove container, keep volume)."""
    from maistro.cli._container.lifecycle import SessionLifecycle

    lifecycle = SessionLifecycle()
    volume = lifecycle.archive_session(session_id)
    console.print(f"[green]Session {session_id} archived to volume {volume}.[/green]")


@app.command("prune")
def builders_prune(
    max_age_hours: Annotated[
        int,
        typer.Option("--max-age", help="Max age in hours for stopped sessions."),
    ] = 168,
) -> None:
    """Archive all stopped sessions older than max age."""
    from maistro.cli._container.lifecycle import SessionLifecycle

    lifecycle = SessionLifecycle()
    pruned = lifecycle.prune_sessions(max_age_hours=max_age_hours)
    if pruned:
        for sid in pruned:
            console.print(f"  [dim]archived {sid}[/dim]")
        console.print(f"[green]Pruned {len(pruned)} sessions.[/green]")
    else:
        console.print("[dim]No sessions to prune.[/dim]")


def _launch_tui_in_container(
    info: object,
    task: str,
    autonomy: str,
    model: str | None,
) -> None:
    """Launch the builders TUI connected to a container's filesystem.

    Falls back to the local filesystem TUI if the container runtime
    is not available (dev mode).
    """
    try:
        from maistro_bootstrap.builders.agent_loop import AgentLoopConfig
        from maistro_bootstrap.builders.models import BuilderModelRoles
        from maistro_bootstrap.builders.responses_callable import ResponsesAPICallable
        from maistro_bootstrap.builders.sandbox import LocalWorktreeSandbox
        from maistro_bootstrap.builders.session import BuilderSession
        from maistro_bootstrap.builders.tui import BuildersTUI

        container_name = getattr(info, "name", "local")
        repo_path = f"/var/lib/maistro/sessions/{container_name}"

        import os

        if os.path.isdir(repo_path):
            sandbox = LocalWorktreeSandbox(Path(repo_path))
        else:
            sandbox = LocalWorktreeSandbox(Path("."))

        session = BuilderSession(sandbox=sandbox)
        roles = BuilderModelRoles(
            architect=model or "mistral-small",
            editor=model or "mistral-small",
            tester=model or "mistral-small",
            fallback=model or "mistral-small",
        )

        tui = BuildersTUI(
            session,
            roles,
            task=task,
            session_id=container_name,
            config=AgentLoopConfig(),
        )
        tui._runner.set_llm(ResponsesAPICallable())  # type: ignore[arg-type]
        tui.run()

    except ImportError:
        console.print("[yellow]maistro-bootstrap not installed — running in headless mode[/yellow]")
        console.print(
            f"Container is running. Attach with: [bold]docker exec -it maistro-{getattr(info, 'name', 'session')} bash[/bold]"
        )


# Re-export typer for the Annotated type hint
import typer  # noqa: E402
