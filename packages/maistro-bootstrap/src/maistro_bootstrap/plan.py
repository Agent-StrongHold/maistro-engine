"""Build a structured install plan (JSON-serializable) from validated answers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

from maistro_bootstrap.platform_detect import deployment_tier_gate_message
from maistro_bootstrap.repo_root import find_maistro_engine_root
from maistro_bootstrap.resolver import (
    commands_for,
    commands_for_compose_addons_run_podman,
    commands_for_compose_addons_validate,
    copier_command,
    podman_install_preface_lines,
    should_print_podman_preface,
)
from maistro_bootstrap.schema import InstallAnswersV1


def effective_runtime(answers: InstallAnswersV1) -> str:
    if answers.container_runtime != "auto":
        return answers.container_runtime
    if answers.deployment_tier == "local_podman":
        return "podman"
    return "docker"


def _stub_preview_lines(answers: InstallAnswersV1) -> list[str]:
    manifest = Path(__file__).resolve().parent / "stub_manifest.yaml"
    if not manifest.is_file():
        return []
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    fp = data.get("feature_preview") or {}
    ca = data.get("compose_addons") or {}
    out: list[str] = []
    for f in answers.features:
        if f in fp:
            out.append(str(fp[f]))
    for a in answers.compose_addons:
        if a in ca:
            out.append(str(ca[a]))
    return out


def _preview_for_observability(answers: InstallAnswersV1) -> list[str]:
    notes: list[str] = []
    ob = answers.observability_backend
    if ob == "arize":
        notes.append(
            "observability=arize: [preview] Root compose ships Langfuse today, not Arize; "
            "add a compose fragment or product override when ready."
        )
    elif ob in ("langfuse_v2", "langfuse_v3"):
        notes.append(
            f"observability={ob}: [preview] Stack includes `langfuse` service; "
            "image major version pinning is a separate compose change."
        )
    return notes


def _preview_for_gateway(answers: InstallAnswersV1) -> list[str]:
    if answers.llm_gateway == "other":
        return [
            "llm_gateway=other: [preview] No alternate gateway merged in Tier 0; "
            "use direct SDK calls or add a compose profile later."
        ]
    return []


def _compose_profile_hints(answers: InstallAnswersV1) -> list[str]:
    """Stub-phase lines until root compose uses profiles (see compose-slices.example.yml)."""
    lines = [
        "# Compose profile stub (root docker-compose.yml is always-on today):",
        "# When profiles land: COMPOSE_PROFILES=llm,observability docker compose up -d",
        "# See docs/install/compose-slices.example.yml",
    ]
    if "llm_proxy" in answers.features:
        lines.append("# [preview] feature llm_proxy → future profile `llm` toggles LiteLLM slice.")
    if "observability" in answers.features:
        lines.append(
            "# [preview] feature observability → future profile `observability` toggles Langfuse slice."
        )
    return lines


def build_install_plan(
    answers: InstallAnswersV1,
    *,
    repo_root: Path | None = None,
    copier_dest: str = "../my-product",
) -> dict[str, Any]:
    """Single JSON shape for CLI `--json` and Hive `POST /v1/install/plan`."""
    rr = repo_root if repo_root is not None else find_maistro_engine_root()
    features = set(answers.features)
    compose_addons = set(answers.compose_addons)

    shell_lines: list[str] = ["# === maistro-install plan (default: print only) ==="]
    shell_lines.extend(commands_for(features))
    shell_lines.extend(commands_for_compose_addons_validate(compose_addons))
    if should_print_podman_preface(compose_addons):
        shell_lines.extend([*podman_install_preface_lines(), ""])
    shell_lines.extend(commands_for_compose_addons_run_podman(compose_addons))

    preview_notes = [
        *_stub_preview_lines(answers),
        *_preview_for_observability(answers),
        *_preview_for_gateway(answers),
    ]
    if answers.stack_bringup == "root_full" and rr is None:
        preview_notes.append(
            "stack_bringup=root_full: [preview] Repo root not found — set MAISTRO_REPO_ROOT "
            "or run from inside maistro-engine; apply will not run."
        )
    elif answers.stack_bringup == "root_full" and rr is not None:
        preview_notes.append(
            "stack_bringup=root_full: --apply runs `compose build --pull never` (images with "
            "`build:` only; no `up` / no pulls for compose `image:` services). "
            "When ready, run `docker compose up -d` (or podman) yourself to start dependencies."
        )

    gate = deployment_tier_gate_message(answers.deployment_tier)
    if gate:
        preview_notes.append(gate)

    for n in preview_notes:
        shell_lines.append(f"# {n}")

    apply_spec: dict[str, Any] | None = None
    if answers.stack_bringup == "root_full" and rr is not None:
        rt = effective_runtime(answers)
        binary = "podman" if rt == "podman" else "docker"
        apply_spec = {
            "cwd": str(rr),
            "argv": [binary, "compose", "build", "--pull", "never"],
            "description": (
                f"Build compose images with a Dockerfile from {rr} ({binary}); "
                "does not start containers or pull `image:`-only services"
            ),
        }

    copier_line: str | None = None
    if answers.product:
        copier_line = copier_command(answers.product, copier_dest)

    return {
        "kind": "maistro_install_plan",
        "plan_version": 1,
        "answers": answers.model_dump(mode="json"),
        "repo_root": str(rr) if rr else None,
        "shell_commands": shell_lines,
        "compose_profile_hints": _compose_profile_hints(answers),
        "preview_notes": preview_notes,
        "apply_spec": apply_spec,
        "copier_command": copier_line,
    }


def shell_script_from_plan(plan: dict[str, Any]) -> str:
    """Flatten shell_commands for human copy-paste."""
    return "\n".join(plan.get("shell_commands", [])) + "\n"


def run_apply_spec(spec: dict[str, Any]) -> int:
    """Run compose build argv with cwd (no shell). Returns process exit code."""
    argv = [str(x) for x in spec["argv"]]
    cwd = str(spec["cwd"])
    proc = subprocess.run(list(argv), cwd=cwd, check=False)
    return int(proc.returncode)
