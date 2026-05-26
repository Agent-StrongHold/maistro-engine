"""Project model — per-user (or team-shared) workspaces.

A user has many DOMAINS (PM, Art, Engineering, Product, custom) and each
domain can hold one or many PROJECTS. A project IS a hyperagent meta-DAG:
its own integrations, dashboards, sub-agent DAGs, skills, and settings —
all scoped per-meta-DAG.

PM Fleet is the first user of the substrate. Other domains (canvas_creative,
engineering_rfc) are token seats at v0.2: they prove the substrate is
domain-neutral but ship with minimal default DAGs + no dedicated UI yet.

Public surface:
  Types          — Project, ProjectMember, ProjectMemberRole,
                   ProjectSettings, JiraResourceBinding,
                   AirtableResourceBinding, RepoResourceBinding.
  Exceptions     — ProjectNotFound, ProjectAccessDenied,
                   ProjectQuotaExceeded.
  Stores         — ProjectStore Protocol + InMemoryProjectStore reference.
  Domains        — KNOWN_DOMAINS (curated set), DomainConfig, domain_for(),
                   domain_use_cases().
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
    "AirtableResourceBinding",
    "DomainConfig",
    "InMemoryProjectStore",
    "JiraResourceBinding",
    "KNOWN_DOMAINS",
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
