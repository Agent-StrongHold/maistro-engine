"""Canonical execution contracts for the MAIstro runtime spine.

These types intentionally stay small. Specialized executors keep their own
adapter state; this module carries the identity, ownership, lineage, lifecycle,
and correlation that must survive across every execution path.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunKind(StrEnum):
    GRAPH = "graph"
    AGENT = "agent"
    TEAM = "team"
    TASK = "task"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    EVOLVE = "evolve"


class RunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkspaceRef(BaseModel):
    """Authorized workspace identity at an execution boundary."""

    model_config = ConfigDict(frozen=True)

    workspace_id: str = Field(min_length=1)
    actor_id: str | None = None


class RunContext(BaseModel):
    """Canonical identity and lineage for one unit of execution."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    kind: RunKind
    state: RunState = RunState.PENDING
    root_run_id: str = Field(min_length=1)
    parent_run_id: str | None = None
    actor_id: str | None = None
    correlation_id: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_root_lineage(self) -> "RunContext":
        if self.parent_run_id is None and self.root_run_id != self.run_id:
            raise ValueError("top-level run must use its own run_id as root_run_id")
        return self


class ExecutionContext(BaseModel):
    """Context passed through adapters and cross-cutting capabilities."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    run: RunContext
    services: dict[str, Any] = Field(default_factory=dict)

    @property
    def run_id(self) -> str:
        return self.run.run_id

    @property
    def workspace_id(self) -> str:
        return self.run.workspace_id

    @property
    def root_run_id(self) -> str:
        return self.run.root_run_id

    @property
    def parent_run_id(self) -> str | None:
        return self.run.parent_run_id

    @property
    def correlation_id(self) -> str:
        return self.run.correlation_id

    @property
    def actor_id(self) -> str | None:
        return self.run.actor_id
