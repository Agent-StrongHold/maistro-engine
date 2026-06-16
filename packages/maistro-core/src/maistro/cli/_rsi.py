"""`maistro rsi` installed interface for autonomous sandbox campaigns."""

from __future__ import annotations

# Typer expresses CLI option metadata through function defaults.
# ruff: noqa: B008
import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

app = typer.Typer(help="Run resumable autonomous improvement campaigns.")
console = Console()


@app.command("start")  # type: ignore[untyped-decorator]
def start(
    repo_url: str = typer.Option(..., help="Credential-free HTTPS Git repository."),
    objective: str = typer.Option(
        ..., help="Improvement objective supplied to the candidate agent."
    ),
    test_command: str = typer.Option(..., help="Fixed regression command run in fresh sandboxes."),
    benchmark_command: str | None = typer.Option(
        None, help="Fixed command whose final line is real-fidelity score JSON."
    ),
    campaign_id: str | None = typer.Option(None),
    base_ref: str = typer.Option("develop"),
    max_iterations: int = typer.Option(10),
    provider_failure_limit: int = typer.Option(3),
    provider_retry_delay_seconds: float = typer.Option(30.0),
    model: str | None = typer.Option(None),
    sandbox_image: str | None = typer.Option(None),
    protected_path: list[str] | None = typer.Option(None),
    state_dir: Path | None = typer.Option(None),
) -> None:
    """Create and run a target-agnostic campaign."""
    cli = _rsi_cli()
    _execute(
        lambda: cli.start_campaign(
            state_root=state_dir or cli.default_state_root(),
            campaign_id=campaign_id,
            repo_url=repo_url,
            objective=objective,
            test_command=test_command,
            benchmark_command=benchmark_command,
            base_ref=base_ref,
            max_iterations=max_iterations,
            provider_failure_limit=provider_failure_limit,
            provider_retry_delay_seconds=provider_retry_delay_seconds,
            model=model,
            sandbox_image=sandbox_image,
            protected_paths=protected_path,
        )
    )


@app.command("resume")  # type: ignore[untyped-decorator]
def resume(campaign_id: str, state_dir: Path | None = typer.Option(None)) -> None:
    """Resume a campaign from its pinned commit and accepted patch."""
    cli = _rsi_cli()
    _execute(
        lambda: cli.resume_campaign(
            state_root=state_dir or cli.default_state_root(), campaign_id=campaign_id
        )
    )


@app.command("status")  # type: ignore[untyped-decorator]
def status(campaign_id: str, state_dir: Path | None = typer.Option(None)) -> None:
    """Show durable campaign status."""
    cli = _rsi_cli()
    _execute(
        lambda: cli.campaign_status(
            state_root=state_dir or cli.default_state_root(), campaign_id=campaign_id
        )
    )


@app.command("stop")  # type: ignore[untyped-decorator]
def stop(campaign_id: str, state_dir: Path | None = typer.Option(None)) -> None:
    """Request a durable stop between trials."""
    cli = _rsi_cli()
    _execute(
        lambda: cli.stop_campaign(
            state_root=state_dir or cli.default_state_root(), campaign_id=campaign_id
        )
    )


def _rsi_cli() -> Any:
    try:
        from maistro_rsi import cli
    except ImportError:
        console.print(
            "[red]maistro-rsi is not installed.[/red]\n"
            "Install the RSI capability with: [bold]pip install 'maistro-core[rsi]'[/bold]"
        )
        raise typer.Exit(1) from None
    return cli


def _print_state(state: Any) -> None:
    console.print_json(json.dumps(asdict(state), sort_keys=True))


def _execute(operation: Callable[[], Any]) -> None:
    try:
        _print_state(operation())
    except Exception as exc:
        console.print(f"[red]maistro rsi failed:[/red] {exc}")
        raise typer.Exit(1) from None
