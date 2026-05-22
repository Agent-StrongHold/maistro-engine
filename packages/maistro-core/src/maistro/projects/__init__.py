"""Project model — per-user (or team-shared) workspaces.

Public surface:
  Types          — :class:`Project`, :class:`ProjectMember`,
                   :class:`ProjectMemberRole`, :class:`ProjectSettings`,
                   :class:`JiraResourceBinding`,
                   :class:`AirtableResourceBinding`,
                   :class:`RepoResourceBinding`.
  Exceptions     — :class:`ProjectNotFound`, :class:`ProjectAccessDenied`,
                   :class:`ProjectQuotaExceeded`.
  Stores         — :class:`ProjectStore` Protocol +
                   :class:`InMemoryProjectStore` reference impl.
"""

from __future__ import annotations

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
    "AirtableResourceBinding",
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
]
