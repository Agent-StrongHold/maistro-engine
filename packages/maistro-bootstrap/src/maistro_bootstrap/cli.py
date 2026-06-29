"""Typer CLI for maistro-install (single command, no subcommands)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from rich.console import Console

from maistro_bootstrap.materialize import materialize_install_artifacts
from maistro_bootstrap.plan import build_install_plan, run_apply_spec
from maistro_bootstrap.repo_root import find_maistro_engine_root
from maistro_bootstrap.schema import InstallAnswersV1, parse_answers_dict
from maistro_bootstrap.wizard import collect_answers_interactive

console = Console()


def _load_raw_answers(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise typer.BadParameter("Answers file must be a YAML mapping at the top level.")
    return data


def _resolve_answers(answers_file: Path | None) -> InstallAnswersV1:
    if answers_file is not None:
        return parse_answers_dict(_load_raw_answers(answers_file))
    if not sys.stdin.isatty():
        console.print(
            "[red]No TTY and no --answers-file. Pass --answers-file or run interactively.[/red]"
        )
        raise typer.Exit(2)
    return collect_answers_interactive()


def _print_human_plan(plan: dict[str, Any], answers: InstallAnswersV1, repo: str | None) -> None:
    console.print("[bold]Resolved plan[/bold]")
    console.print(f"  features:               {sorted(answers.features)}")
    console.print(f"  compose_addons:         {sorted(answers.compose_addons)}")
    console.print(f"  product:                {answers.product or '(none)'}")
    console.print(f"  stack_bringup:          {answers.stack_bringup}")
    console.print(f"  repo_root:              {repo}\n")

    for line in plan.get("shell_commands", []):
        console.print(line, markup=False, highlight=False)

    cc = plan.get("copier_command")
    if cc:
        console.print("\n# Copier (install copier: uv tool install copier)", markup=False)
        console.print(cc, markup=False, highlight=False)

    spec = plan.get("apply_spec")
    if spec:
        console.print("\n[bold]Apply spec[/bold] (use [cyan]maistro-install --apply[/cyan]):")
        console.print(f"  cwd: {spec['cwd']}\n  argv: {spec['argv']}")
    elif answers.stack_bringup == "root_full":
        console.print(
            "\n[yellow]stack_bringup=root_full but apply_spec is missing (no repo root).[/yellow]"
        )


def _maybe_apply(plan: dict[str, Any], yes: bool) -> None:
    spec = plan.get("apply_spec")
    if not spec:
        console.print("[red]No apply_spec in plan; nothing to run.[/red]")
        raise typer.Exit(3)
    if not yes:
        ok = typer.confirm(
            "Run compose build now (docker|podman compose build --pull never)?", default=False
        )
        if not ok:
            console.print("Aborted.")
            raise typer.Exit(0)
    code = run_apply_spec(spec)
    if code != 0:
        console.print(f"[red]apply_spec exited with code {code}[/red]")
        raise typer.Exit(code)
    console.print("[green]apply_spec completed.[/green]")


def main(
    answers_file: Annotated[
        Path | None,
        typer.Option(
            "--answers-file",
            help="YAML answers (see docs/install/examples/).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Print only (default). Use --no-dry-run with --apply to run compose build.",
        ),
    ] = True,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Emit install plan as JSON (Tier 0 / API parity)."),
    ] = False,
    apply_flag: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Run apply_spec only (docker|podman compose build --pull never from repo root).",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation before --apply."),
    ] = False,
    maistro_root: Annotated[
        Path | None,
        typer.Option(
            "--maistro-root",
            help="maistro-engine clone root (default: auto-detect or MAISTRO_REPO_ROOT).",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = None,
    copier_dest: Annotated[
        str,
        typer.Option(
            "--copier-dest",
            help="Destination path for printed copier copy command.",
        ),
    ] = "../my-product",
    materialize_dir: Annotated[
        Path | None,
        typer.Option(
            "--materialize-dir",
            help="Write install artifacts to this directory without starting services.",
            file_okay=False,
            dir_okay=True,
        ),
    ] = None,
) -> None:
    """Resolve install answers into a plan; optionally run compose build (apply)."""
    answers = _resolve_answers(answers_file)
    rr = maistro_root if maistro_root is not None else find_maistro_engine_root()
    plan = build_install_plan(answers, repo_root=rr, copier_dest=copier_dest)

    if materialize_dir is not None:
        written = materialize_install_artifacts(plan, materialize_dir)
        console.print(f"[green]Wrote {len(written)} install artifacts to {materialize_dir}[/green]")

    if json_out:
        console.print_json(data=plan)
        if apply_flag and not dry_run:
            _maybe_apply(plan, yes)
        elif apply_flag and dry_run:
            console.print("[yellow]--apply ignored because --dry-run is set.[/yellow]")
        return

    _print_human_plan(plan, answers, plan.get("repo_root"))
    if materialize_dir is not None:
        console.print(f"\n[bold]Materialized artifacts[/bold]: {materialize_dir}")

    if apply_flag:
        if dry_run:
            console.print("\n[yellow]--apply ignored because --dry-run is set.[/yellow]")
        else:
            _maybe_apply(plan, yes)
    else:
        console.print(
            "\n[dim]Print-only: run shell commands above, or pass --apply with --no-dry-run "
            "to run compose build only.[/dim]"
        )


def run() -> None:
    typer.run(main)


if __name__ == "__main__":
    run()
