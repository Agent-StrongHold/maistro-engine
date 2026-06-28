"""Write a resolved maistro-install plan to an install target directory."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

import yaml


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_yaml(path: Path, data: Any) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _write_tutorial(path: Path, todos: list[str]) -> None:
    lines = ["# Maistro first-run setup", ""]
    lines.extend(f"- [ ] {todo}" for todo in todos)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_entrypoint(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'cd "$(dirname "$0")"\n'
        "echo 'Maistro install artifacts are materialized in:' \"$PWD\"\n"
        "echo 'Review install-answers.yaml and compose.override.yml before starting services.'\n"
        "echo 'Next: docker compose -f compose.override.yml config'\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def materialize_install_artifacts(plan: dict[str, Any], target_dir: Path) -> list[Path]:
    """Materialize generated installer artifacts and return written paths.

    This is intentionally file-only: it never starts containers, installs packages, or writes secrets.
    """
    artifacts = plan.get("generated_artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("plan is missing generated_artifacts")

    target_dir.mkdir(parents=True, exist_ok=True)
    answers = plan.get("answers", {})
    compose = artifacts.get("compose_override_preview", {})
    todos = artifacts.get("tutorial_todo", [])
    if not isinstance(todos, list):
        todos = []

    files: list[tuple[str, str, Any]] = [
        ("install-plan.json", "json", plan),
        ("install-answers.yaml", "yaml", answers),
        ("compose.override.yml", "yaml", compose),
        ("sandbox-policy.json", "json", artifacts.get("sandbox_policy", {})),
        ("bootstrap-users.json", "json", artifacts.get("bootstrap_users", [])),
        ("delivery.json", "json", artifacts.get("delivery", {})),
        ("first-agents.json", "json", artifacts.get("reactor", {}).get("first_agents", [])),
        ("identity-root.json", "json", artifacts.get("identity_root", {})),
        ("unsupported-options.json", "json", artifacts.get("unsupported_options", {})),
    ]

    written: list[Path] = []
    for name, kind, data in files:
        path = target_dir / name
        if kind == "json":
            _write_json(path, data)
        else:
            _write_yaml(path, data)
        written.append(path)

    tutorial = target_dir / "tutorial-todo.md"
    _write_tutorial(tutorial, [str(todo) for todo in todos])
    written.append(tutorial)

    entrypoint = target_dir / "install.sh"
    _write_entrypoint(entrypoint)
    written.append(entrypoint)

    return written
