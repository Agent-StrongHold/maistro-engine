"""Live Persona domain model.

`PersonaTemplate` remains the reusable authoring/template definition.  This
module defines the live, Workspace-owned product context described by
ADR-081226-e626.  A Persona selects surfaces, template catalogs, defaults and
availability ceilings; it never owns execution lifecycle state.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PersonaSurface(StrEnum):
    """Well-known product surfaces.

    Persona surface values are intentionally stored as strings so specialized
    packages can register additional surfaces without extending this enum.  The
    enum is a convenience vocabulary for the surfaces core MAIstro knows about.
    """

    UI = "ui"
    API = "api"
    BUILDERS_CLI = "builders_cli"
    BUILDERS_RSI = "builders_rsi"


class Persona(BaseModel):
    """A live product context owned by exactly one Workspace.

    Catalog and availability fields contain references only.  Persona does not
    copy template content, credentials, provider implementations, or Run state.
    Defaults apply when new objects are created and are not retroactive.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    workspace_id: str
    name: str
    purpose: str = ""
    description: str = ""
    theme: str | None = None

    # Surface names are free strings by design.  PersonaSurface provides the
    # standard vocabulary while product packages remain free to add their own.
    allowed_surfaces: set[str] = Field(default_factory=set)

    # Catalog references.  The referenced template objects remain independently
    # versioned and owned according to the template/provenance architecture.
    node_template_ids: list[str] = Field(default_factory=list)
    graph_template_ids: list[str] = Field(default_factory=list)

    # Permission names represent a ceiling below Workspace authority.  An empty
    # ceiling grants nothing; callers must intersect with parent authority.
    permission_ceiling: set[str] = Field(default_factory=set)
    policy_defaults: dict[str, Any] = Field(default_factory=dict)

    # Availability references, never embedded credentials or provider objects.
    available_capability_ids: list[str] = Field(default_factory=list)
    available_binding_ids: list[str] = Field(default_factory=list)

    # Defaults for future object creation.  Existing Nodes, Graphs and Runs are
    # not mutated when these values change.
    default_model_id: str | None = None
    default_provider_id: str | None = None
    defaults: dict[str, Any] = Field(default_factory=dict)

    # Optional provenance when this Persona was adopted/created from an
    # existing PersonaTemplate or other versioned template source.
    source_template_id: str | None = None
    source_template_version: str | None = None

    # Product/domain packages may attach namespaced metadata without growing the
    # canonical model for every specialized UX concern.
    extension_metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("id", "workspace_id", "name")
    @classmethod
    def _require_non_blank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("allowed_surfaces", "permission_ceiling")
    @classmethod
    def _require_non_blank_names(cls, values: set[str]) -> set[str]:
        if any(not value.strip() for value in values):
            raise ValueError("surface and permission names must be non-empty strings")
        return values

    def allows_surface(self, surface: str | PersonaSurface) -> bool:
        """Return whether this Persona exposes a named product surface."""
        return str(surface) in self.allowed_surfaces

    def effective_permissions(self, parent_permissions: Iterable[str]) -> frozenset[str]:
        """Narrow parent authority to this Persona's permission ceiling.

        This helper deliberately cannot add a permission absent from the parent
        Workspace/User chain.  Later Graph/Node/Binding/Invocation layers apply
        the same intersection rule to the result.
        """
        return frozenset(parent_permissions).intersection(self.permission_ceiling)


__all__ = ["Persona", "PersonaSurface"]
