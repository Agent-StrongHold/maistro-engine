from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maistro.graph.definitions import Graph


def _id() -> str:
    return uuid.uuid4().hex


class RunStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class AttemptStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    YIELDED = "yielded"


TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.TIMED_OUT,
    }
)
TERMINAL_ATTEMPT_STATUSES = frozenset(
    {
        AttemptStatus.COMPLETED,
        AttemptStatus.FAILED,
        AttemptStatus.CANCELLED,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.YIELDED,
    }
)


class GraphSnapshot(BaseModel):
    """Immutable-by-value Graph definition captured when a Run is created."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_id: str
    workspace_id: str
    content_hash: str
    definition_json: str

    @classmethod
    def from_graph(cls, graph: Graph) -> GraphSnapshot:
        return cls(
            graph_id=graph.graph_id,
            workspace_id=graph.workspace_id,
            content_hash=graph.content_hash,
            definition_json=graph.model_dump_json(),
        )

    def materialize(self) -> Graph:
        return Graph.model_validate_json(self.definition_json)

    @model_validator(mode="after")
    def _validate_snapshot(self) -> GraphSnapshot:
        graph = self.materialize()
        if graph.graph_id != self.graph_id:
            raise ValueError("graph snapshot graph_id does not match definition")
        if graph.workspace_id != self.workspace_id:
            raise ValueError("graph snapshot workspace_id does not match definition")
        if graph.content_hash != self.content_hash:
            raise ValueError("graph snapshot content_hash does not match definition")
        return self


class Run(BaseModel):
    """One logical execution of a stable Workspace-owned Graph snapshot."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=_id)
    workspace_id: str
    graph: GraphSnapshot
    status: RunStatus = RunStatus.CREATED
    parent_run_id: str | None = None
    parent_node_run_id: str | None = None
    persona_id: str | None = None
    actor_principal_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _validate_run(self) -> Run:
        if not self.workspace_id.strip():
            raise ValueError("workspace_id must be a non-empty string")
        if self.graph.workspace_id != self.workspace_id:
            raise ValueError("Run and Graph snapshot must belong to the same Workspace")
        if self.parent_run_id == self.run_id:
            raise ValueError("Run cannot be its own parent")
        if self.status in TERMINAL_RUN_STATUSES and self.finished_at is None:
            raise ValueError("terminal Run requires finished_at")
        if self.status not in TERMINAL_RUN_STATUSES and self.finished_at is not None:
            raise ValueError("non-terminal Run cannot have finished_at")
        return self


class NodeRun(BaseModel):
    """One logical execution of one Node within a Run."""

    model_config = ConfigDict(extra="forbid")

    node_run_id: str = Field(default_factory=_id)
    run_id: str
    node_id: str
    ordinal: int = Field(ge=1)
    status: RunStatus = RunStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: Any | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _validate_node_run(self) -> NodeRun:
        if not self.run_id.strip() or not self.node_id.strip():
            raise ValueError("run_id and node_id must be non-empty strings")
        if self.status in TERMINAL_RUN_STATUSES and self.finished_at is None:
            raise ValueError("terminal NodeRun requires finished_at")
        if self.status not in TERMINAL_RUN_STATUSES and self.finished_at is not None:
            raise ValueError("non-terminal NodeRun cannot have finished_at")
        return self


class Attempt(BaseModel):
    """One physical try under a NodeRun."""

    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(default_factory=_id)
    node_run_id: str
    ordinal: int = Field(ge=1)
    status: AttemptStatus = AttemptStatus.CREATED
    runtime_id: str = "python"
    executor_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    deadline_at: datetime | None = None
    resume_checkpoint_id: str | None = None
    result: Any | None = None
    error: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_attempt(self) -> Attempt:
        if not self.node_run_id.strip():
            raise ValueError("node_run_id must be a non-empty string")
        if self.status in TERMINAL_ATTEMPT_STATUSES and self.finished_at is None:
            raise ValueError("terminal Attempt requires finished_at")
        if self.status not in TERMINAL_ATTEMPT_STATUSES and self.finished_at is not None:
            raise ValueError("non-terminal Attempt cannot have finished_at")
        return self


__all__ = [
    "Attempt",
    "AttemptStatus",
    "GraphSnapshot",
    "NodeRun",
    "Run",
    "RunStatus",
    "TERMINAL_ATTEMPT_STATUSES",
    "TERMINAL_RUN_STATUSES",
]
