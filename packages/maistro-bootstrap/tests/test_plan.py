"""Golden-style tests for install plan builder (no Docker required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maistro_bootstrap.plan import build_install_plan
from maistro_bootstrap.schema import parse_answers_dict


def test_plan_includes_compose_profile_hints() -> None:
    raw = {
        "schema_version": "1",
        "features": ["llm_proxy", "observability"],
        "stack_bringup": "none",
    }
    answers = parse_answers_dict(raw)
    plan = build_install_plan(answers, repo_root=Path("/tmp/x"))
    hints = plan.get("compose_profile_hints", [])
    assert any("llm_proxy" in h for h in hints)
    assert any("observability" in h for h in hints)


@pytest.mark.ac("SPEC-180/AC-1")
def test_golden_plan_shape() -> None:
    raw = {
        "schema_version": "1",
        "features": ["core_lib"],
        "stack_bringup": "none",
        "deployment_tier": "proxmox",
    }
    plan = build_install_plan(parse_answers_dict(raw), repo_root=None)
    assert plan["kind"] == "maistro_install_plan"
    assert "compose_profile_hints" in plan
    assert any("Proxmox" in n for n in plan["preview_notes"])


def test_plan_includes_uv_sync_for_core_lib() -> None:
    raw = {
        "schema_version": "1",
        "features": ["core_lib"],
        "stack_bringup": "none",
    }
    answers = parse_answers_dict(raw)
    plan = build_install_plan(answers, repo_root=Path("/tmp/fake-root"))
    lines = "\n".join(plan["shell_commands"])
    assert "uv sync" in lines


def test_apply_spec_when_root_full_and_repo_root() -> None:
    raw = {
        "schema_version": "1",
        "features": [],
        "stack_bringup": "root_full",
        "container_runtime": "docker",
    }
    answers = parse_answers_dict(raw)
    fake = Path("/tmp/maistro-fake-root")
    plan = build_install_plan(answers, repo_root=fake)
    spec = plan["apply_spec"]
    assert spec is not None
    assert spec["cwd"] == str(fake)
    assert spec["argv"] == ["docker", "compose", "build", "--pull", "never"]


def test_apply_spec_podman_runtime() -> None:
    raw = {
        "schema_version": "1",
        "features": [],
        "stack_bringup": "root_full",
        "container_runtime": "podman",
    }
    answers = parse_answers_dict(raw)
    plan = build_install_plan(answers, repo_root=Path("/tmp/x"))
    assert plan["apply_spec"]["argv"][0] == "podman"


def test_stub_manifest_preview_for_llm_proxy() -> None:
    raw = {
        "schema_version": "1",
        "features": ["llm_proxy"],
        "stack_bringup": "none",
    }
    answers = parse_answers_dict(raw)
    plan = build_install_plan(answers, repo_root=None)
    joined = " ".join(plan["preview_notes"])
    assert "litellm" in joined.lower() or "preview" in joined.lower()


def test_golden_plan_root_full_without_repo_root_has_no_apply_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("maistro_bootstrap.plan.find_maistro_engine_root", lambda: None)
    plan = build_install_plan(
        parse_answers_dict({"schema_version": "1", "stack_bringup": "root_full"})
    )

    assert plan["repo_root"] is None
    assert plan["apply_spec"] is None
    assert plan["shell_commands"] == [
        "# === maistro-install plan (default: print only) ===",
        "# stack_bringup=root_full: [preview] Repo root not found — set MAISTRO_REPO_ROOT "
        "or run from inside maistro-engine; apply will not run.",
    ]
    assert plan["preview_notes"] == [
        "stack_bringup=root_full: [preview] Repo root not found — set MAISTRO_REPO_ROOT "
        "or run from inside maistro-engine; apply will not run."
    ]


def test_golden_plan_observability_and_gateway_preview_notes() -> None:
    plan = build_install_plan(
        parse_answers_dict(
            {
                "schema_version": "1",
                "features": ["observability"],
                "llm_gateway": "other",
                "observability_backend": "langfuse_v3",
                "stack_bringup": "none",
            }
        ),
        repo_root=Path("/tmp/maistro-root"),
    )

    assert plan["preview_notes"] == [
        "[preview] Root compose includes `langfuse`; choosing Arize or Langfuse v2/v3 in answers "
        "is a manifest hint until matching services are added to compose.",
        "observability=langfuse_v3: [preview] Stack includes `langfuse` service; "
        "image major version pinning is a separate compose change.",
        "llm_gateway=other: [preview] No alternate gateway merged in Tier 0; "
        "use direct SDK calls or add a compose profile later.",
    ]
    assert plan["compose_profile_hints"] == [
        "# Compose profile stub (root docker-compose.yml is always-on today):",
        "# When profiles land: COMPOSE_PROFILES=llm,observability docker compose up -d",
        "# See docs/install/compose-slices.example.yml",
        "# [preview] feature observability → future profile `observability` toggles Langfuse slice.",
    ]
