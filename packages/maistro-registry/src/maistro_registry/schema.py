"""Pydantic schema for ADR/spec front-matter, per `engine#ADR-031`.

Required fields:

- Identity: id, title, repo, kind
- Lifecycle: status, created (+ optional accepted, implemented)
- Relationships: substrate, implements, related, supersedes, blocks, blocked-by
- Contracts and tests: contracts, tests
- Classification: layer, owners

Cross-references use the form `<repo>#<id>` where `<repo>` is one of the
four-repo system members and `<id>` matches `(ADR|SPEC)-NNN`.

Design notes:

- All fields are required; empty lists are valid for relationship and
  contracts/tests fields.
- `extra = forbid` so unknown fields fail validation rather than silently
  passing through. This is the per-ADR-031 contract.
- `populate_by_name = True` so YAML can use either `blocked-by` (canonical)
  or `blocked_by` (Python-attr).
"""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Status(StrEnum):
    PROPOSED = "Proposed"
    ACCEPTED = "Accepted"
    IMPLEMENTED = "Implemented"
    SUPERSEDED = "Superseded"
    BLOCKED = "Blocked"
    ABANDONED = "Abandoned"


class Kind(StrEnum):
    ADR = "adr"
    SPEC = "spec"


class Layer(StrEnum):
    FOUNDATION = "Foundation"
    ORCHESTRATION = "Orchestration"
    AGENTS = "Agents"
    TOOLS = "Tools"
    MEMORY = "Memory"
    OBSERVABILITY = "Observability"
    RELIABILITY = "Reliability"
    GOVERNANCE = "Governance"
    USER_CLIENT = "UserClient"


class Repo(StrEnum):
    ENGINE = "maistro-engine"
    MAISTRO = "Project_mAIstro"
    TURING = "AgentTuring"
    STRONGHOLD = "stronghold"


class Contract(StrEnum):
    BOUNDARY = "boundary"
    BEHAVIORAL = "behavioral"
    CROSS_SERVICE = "cross-service"


# Local id pattern: e.g. ADR-024, SPEC-138
_ID_PATTERN = re.compile(r"^(ADR|SPEC)-\d{3}$")

# Cross-repo reference pattern: e.g. maistro-engine#ADR-024
_REF_PATTERN = re.compile(
    r"^(maistro-engine|Project_mAIstro|AgentTuring|stronghold)#(ADR|SPEC)-\d{3}$"
)


def _is_valid_id(value: str) -> bool:
    return bool(_ID_PATTERN.match(value))


def _is_valid_ref(value: str) -> bool:
    return bool(_REF_PATTERN.match(value))


class FrontMatter(BaseModel):
    """Canonical front-matter schema for ADRs and specs across the four-repo system."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    # Identity
    id: str
    title: str
    repo: Repo
    kind: Kind

    # Lifecycle
    status: Status
    created: date
    accepted: date | None = None
    implemented: date | None = None

    # Relationships (each entry is `<repo>#<id>`)
    substrate: list[str] = Field(default_factory=list)
    implements: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list, alias="blocked-by")

    # Contracts and tests
    contracts: list[Contract] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)

    # Provenance: repo paths (packages/…, apps/…) this record governs/derives from.
    source: list[str] = Field(default_factory=list)

    # Classification
    layer: Layer
    owners: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not _is_valid_id(v):
            raise ValueError(f"id must match ^(ADR|SPEC)-NNN$, got {v!r}")
        return v

    @field_validator(
        "substrate",
        "implements",
        "related",
        "supersedes",
        "blocks",
        "blocked_by",
    )
    @classmethod
    def _validate_refs(cls, v: list[str]) -> list[str]:
        for ref in v:
            if not _is_valid_ref(ref):
                raise ValueError(
                    f"reference must match `<repo>#<ID>`, got {ref!r}. "
                    f"Repos: maistro-engine, Project_mAIstro, AgentTuring, stronghold."
                )
        return v

    @field_validator("owners")
    @classmethod
    def _validate_owners(cls, v: list[str]) -> list[str]:
        for owner in v:
            if not owner.startswith("@"):
                raise ValueError(f"owner must start with @, got {owner!r}")
        return v
