"""Legacy Project domain retained only until its consumers move to Workspace.

New code must use :mod:`maistro.workspaces`. Project is no longer a Workspace
alias or persistence authority for canonical product state.
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

__all__ = [
    "KNOWN_DOMAINS",
    "AirtableResourceBinding",
    "DomainConfig",
    "InMemoryProjectStore",
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
    "domain_for",
    "domain_use_cases",
]
