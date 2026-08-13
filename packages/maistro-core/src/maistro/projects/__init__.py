"""Legacy Project API plus the canonical Workspace compatibility bridge.

``Project`` remains the durable representation during migration. New code should
prefer :mod:`maistro.workspaces`; Workspace exports here are retained so callers
using the first compatibility surface continue to resolve the same durable IDs.
"""

from __future__ import annotations

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
from .workspace import (
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
    "WorkspaceMembership",
    "WorkspaceNotFound",
    "WorkspaceOwnershipError",
    "WorkspaceQuotaExceeded",
    "WorkspaceRole",
    "WorkspaceSettings",
    "WorkspaceStore",
    "domain_for",
    "domain_use_cases",
    "legacy_project_role_for_workspace_role",
    "membership_for",
    "memberships_for",
    "resolve_workspace_id",
    "workspace_role_from_legacy",
]
