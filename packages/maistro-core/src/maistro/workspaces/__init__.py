"""Canonical Workspace domain surface.

The durable representation is still the legacy :mod:`maistro.projects` Project
record during migration. Import Workspace concepts from this package in new
code so collaboration uses owner/contributor/member vocabulary without creating
a second persistence root.
"""

from __future__ import annotations

from maistro.projects.workspace import (
    InMemoryWorkspaceStore,
    Workspace,
    WorkspaceAccessDenied,
    WorkspaceMember,
    WorkspaceMembership,
    WorkspaceNotFound,
    WorkspaceOwnershipError,
    WorkspaceQuotaExceeded,
    WorkspaceRole,
    WorkspaceSettings,
    WorkspaceStore,
    legacy_project_role_for_workspace_role,
    membership_for,
    memberships_for,
    resolve_workspace_id,
    workspace_role_from_legacy,
)

__all__ = [
    "InMemoryWorkspaceStore",
    "Workspace",
    "WorkspaceAccessDenied",
    "WorkspaceMember",
    "WorkspaceMembership",
    "WorkspaceNotFound",
    "WorkspaceOwnershipError",
    "WorkspaceQuotaExceeded",
    "WorkspaceRole",
    "WorkspaceSettings",
    "WorkspaceStore",
    "legacy_project_role_for_workspace_role",
    "membership_for",
    "memberships_for",
    "resolve_workspace_id",
    "workspace_role_from_legacy",
]
