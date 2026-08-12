"""Project model — per-user (or team-shared) workspaces.

A user has many DOMAINS (PM, Art, Engineering, Product, custom) and each
domain can hold one or many PROJECTS. A project IS a hyperagent meta-DAG:
its own integrations, dashboards, sub-agent DAGs, skills, and settings —
all scoped per-meta-DAG.

`Workspace` is the canonical architectural/product term introduced by the
runtime spine. It is an alias of `Project` during the compatibility migration,
so existing persistence and callers keep working while new runtime APIs use
workspace terminology.
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

Workspace = Project

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
    "Workspace",
    "domain_for",
    "domain_use_cases",
]
