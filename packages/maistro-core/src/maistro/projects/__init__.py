"""Workspace ownership model with Project compatibility.

`Workspace` is the canonical product ownership boundary.  The existing
`Project` record and store remain the persistence/API compatibility
representation while callers migrate to Workspace vocabulary.  The aliases
below are intentionally identity-preserving: introducing Workspace must not
create a second durable root, change IDs, or force a database-column rename.

Legacy Project names remain public for compatibility.  New product/domain
code should prefer the Workspace names and use :func:`resolve_workspace_id`
when it needs to accept both canonical ``workspace_id`` and legacy
``project_id`` ownership fields during migration.

Public surface:
  Canonical       — Workspace, WorkspaceMember, WorkspaceRole,
                    WorkspaceSettings, WorkspaceStore,
                    InMemoryWorkspaceStore.
  Compatibility   — Project, ProjectMember, ProjectMemberRole,
                    ProjectSettings, ProjectStore, InMemoryProjectStore.
  Ownership       — resolve_workspace_id(), WorkspaceOwnershipError.
  Resources       — JiraResourceBinding, AirtableResourceBinding,
                    RepoResourceBinding.
  Domains         — KNOWN_DOMAINS (curated set), DomainConfig, domain_for(),
                    domain_use_cases().
"""

from __future__ import annotations

from collections.abc import Mapping

from .domains import KNOWN_DOMAINS, DomainConfig, domain_for, domain_use_cases
from .store import InMemoryProjectStore, ProjectStore
from .types import (
    AirtableResourceBinding,
    JiraResourceBinding,
    Project,
    ProjectAccessDenied,
    ProjectMember,
    ProjectMemberRole,
    ProjectNotFound,
    ProjectQuotaExceeded,
    ProjectSettings,
    RepoResourceBinding,
)

# Canonical names over the existing durable representation.  These are aliases,
# not subclasses or copied DTOs, so legacy Project-backed records and new
# Workspace-facing code share one identity and one persistence contract.
Workspace = Project
WorkspaceMember = ProjectMember
WorkspaceRole = ProjectMemberRole
WorkspaceSettings = ProjectSettings
WorkspaceStore = ProjectStore
InMemoryWorkspaceStore = InMemoryProjectStore
WorkspaceNotFound = ProjectNotFound
WorkspaceAccessDenied = ProjectAccessDenied
WorkspaceQuotaExceeded = ProjectQuotaExceeded


class WorkspaceOwnershipError(ValueError):
    """Raised when durable state has no usable Workspace scope or disagrees.

    During migration an object may expose either canonical ``workspace_id`` or
    legacy ``project_id``.  If both exist they must identify the same durable
    Workspace; silently choosing one would allow cross-Workspace leakage.
    """


def _scope_value(value: object, field: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _validated_scope(value: object | None, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceOwnershipError(f"{field} must be a non-empty string")
    return value


def resolve_workspace_id(value: object) -> str:
    """Return the canonical Workspace id for canonical or legacy state.

    Accepted migration shapes:

    * a Workspace/Project root (its ``id`` is the Workspace identity),
    * an object or mapping with ``workspace_id``,
    * an object or mapping with legacy ``project_id``,
    * an object carrying both fields when they agree.

    Generic ``id`` fields are deliberately not inferred: only the canonical
    Workspace/Project root itself gets that treatment.  Durable child objects
    must declare ownership explicitly so an unrelated object id can never be
    mistaken for a Workspace boundary.
    """
    if isinstance(value, Project):
        return value.id

    workspace_id = _validated_scope(_scope_value(value, "workspace_id"), "workspace_id")
    project_id = _validated_scope(_scope_value(value, "project_id"), "project_id")

    if workspace_id is not None and project_id is not None and workspace_id != project_id:
        raise WorkspaceOwnershipError(
            "workspace_id and project_id identify different Workspaces: "
            f"{workspace_id!r} != {project_id!r}"
        )

    resolved = workspace_id or project_id
    if resolved is None:
        raise WorkspaceOwnershipError(
            "durable object must declare workspace_id (or legacy project_id during migration)"
        )
    return resolved


__all__ = [
    "KNOWN_DOMAINS",
    "AirtableResourceBinding",
    "DomainConfig",
    "InMemoryProjectStore",
    "InMemoryWorkspaceStore",
    "JiraResourceBinding",
    "Project",
    "ProjectAccessDenied",
    "ProjectMember",
    "ProjectMemberRole",
    "ProjectNotFound",
    "ProjectQuotaExceeded",
    "ProjectSettings",
    "ProjectStore",
    "RepoResourceBinding",
    "Workspace",
    "WorkspaceAccessDenied",
    "WorkspaceMember",
    "WorkspaceNotFound",
    "WorkspaceOwnershipError",
    "WorkspaceQuotaExceeded",
    "WorkspaceRole",
    "WorkspaceSettings",
    "WorkspaceStore",
    "domain_for",
    "domain_use_cases",
    "resolve_workspace_id",
]
