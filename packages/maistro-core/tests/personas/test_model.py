"""Live Persona model tests for ADR-081226-e626."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maistro.personas import Persona, PersonaSurface


def test_persona_is_workspace_owned_product_context_not_execution_root() -> None:
    persona = Persona(
        id="persona-builders",
        workspace_id="ws-1",
        name="Builders",
        purpose="Build and refine MAIstro workflows",
    )

    dumped = persona.model_dump()
    assert dumped["workspace_id"] == "ws-1"
    assert "run_id" not in dumped
    assert "status" not in dumped
    assert "attempts" not in dumped


def test_persona_exposes_known_and_extension_surfaces() -> None:
    persona = Persona(
        id="persona-builders",
        workspace_id="ws-1",
        name="Builders",
        allowed_surfaces={PersonaSurface.UI, PersonaSurface.BUILDERS_CLI, "canvas_book_ui"},
    )

    assert persona.allows_surface(PersonaSurface.UI)
    assert persona.allows_surface("builders_cli")
    assert persona.allows_surface("canvas_book_ui")
    assert not persona.allows_surface(PersonaSurface.BUILDERS_RSI)


def test_persona_catalogs_and_availability_are_references() -> None:
    persona = Persona(
        id="persona-builders",
        workspace_id="ws-1",
        name="Builders",
        node_template_ids=["node-template-frank", "node-template-auditor"],
        graph_template_ids=["graph-template-builders"],
        available_capability_ids=["capability-github"],
        available_binding_ids=["binding-workspace-github"],
        source_template_id="persona-template-builders",
        source_template_version="3",
    )

    assert persona.node_template_ids == ["node-template-frank", "node-template-auditor"]
    assert persona.graph_template_ids == ["graph-template-builders"]
    assert persona.source_template_id == "persona-template-builders"
    assert persona.source_template_version == "3"


def test_persona_permissions_can_only_narrow_parent_authority() -> None:
    persona = Persona(
        id="persona-safe",
        workspace_id="ws-1",
        name="Safe Persona",
        permission_ceiling={"runs.execute", "artifacts.read", "credentials.admin"},
    )

    effective = persona.effective_permissions({"runs.execute", "artifacts.read", "graphs.edit"})

    assert effective == frozenset({"runs.execute", "artifacts.read"})
    assert "credentials.admin" not in effective


def test_empty_permission_ceiling_is_fail_closed() -> None:
    persona = Persona(id="persona-safe", workspace_id="ws-1", name="Safe Persona")
    assert persona.effective_permissions({"runs.execute"}) == frozenset()


def test_persona_defaults_are_explicit_future_object_configuration() -> None:
    persona = Persona(
        id="persona-builders",
        workspace_id="ws-1",
        name="Builders",
        default_model_id="model-sonnet",
        default_provider_id="provider-anthropic",
        policy_defaults={"approval": "required"},
        defaults={"temperature": 0.2},
        extension_metadata={"builders": {"show_rsi": True}},
    )

    assert persona.default_model_id == "model-sonnet"
    assert persona.default_provider_id == "provider-anthropic"
    assert persona.policy_defaults == {"approval": "required"}
    assert persona.defaults == {"temperature": 0.2}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "", "workspace_id": "ws-1", "name": "Persona"},
        {"id": "p-1", "workspace_id": " ", "name": "Persona"},
        {"id": "p-1", "workspace_id": "ws-1", "name": ""},
        {
            "id": "p-1",
            "workspace_id": "ws-1",
            "name": "Persona",
            "allowed_surfaces": {""},
        },
    ],
)
def test_persona_rejects_blank_identity_and_scope_names(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Persona(**kwargs)
