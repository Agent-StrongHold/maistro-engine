from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maistro.graph.definitions import Graph


def _id() -> str:
    return uuid.uuid4().hex


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_finished_at(
    *,
    terminal: bool,
    finished_at: datetime | None,
    subject: str,
) -> None:
    if terminal and finished_at is None:
        raise ValueError(f"terminal {subject} requires finished_at")
    if not terminal and finished_at is not None:
        raise ValueError(f"non-terminal {subject} cannot have finished_at")


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
ACCEPTED_NODE_OUTCOME_STATUSES = frozenset(
    {
        RunStatus.WAITING,
        RunStatus.PAUSED,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
    }
)


class GraphSnapshot(BaseModel):
    """Immutable-by-value Graph definition captured when a Run is created."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_id: str
    workspace_id: str
    project_id: str
    content_hash: str
    definition_json: str

    @classmethod
    def from_graph(cls, graph: Graph) -> GraphSnapshot:
        return cls(
            graph_id=graph.graph_id,
            workspace_id=graph.workspace_id,
            project_id=graph.project_id,
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
        if graph.project_id != self.project_id:
            raise ValueError("graph snapshot project_id does not match definition")
        if graph.content_hash != self.content_hash:
            raise ValueError("graph snapshot content_hash does not match definition")
        return self


class Run(BaseModel):
    """One logical execution of a stable Graph snapshot in one Project scope."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=_id)
    workspace_id: str
    project_id: str
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
        _require_non_empty(self.workspace_id, "workspace_id")
        _require_non_empty(self.project_id, "project_id")
        self._validate_scope_identity()
        if self.parent_run_id == self.run_id:
            raise ValueError("Run cannot be its own parent")
        _validate_finished_at(
            terminal=self.status in TERMINAL_RUN_STATUSES,
            finished_at=self.finished_at,
            subject="Run",
        )
        return self

    def _validate_scope_identity(self) -> None:
        if self.graph.workspace_id != self.workspace_id:
            raise ValueError("Run and Graph snapshot must belong to the same Workspace")
        if self.graph.project_id != self.project_id:
            raise ValueError("Run and Graph snapshot must belong to the same Project")


class ExecutionLease(BaseModel):
    """Durable authority token for one physical Attempt execution epoch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_run_id: str
    attempt_id: str
    lease_epoch: int = Field(ge=1)
    holder: str
    fencing_token: str = Field(default_factory=_id)
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_lease(self) -> ExecutionLease:
        _require_non_empty(self.node_run_id, "node_run_id")
        _require_non_empty(self.attempt_id, "attempt_id")
        _require_non_empty(self.holder, "holder")
        _require_non_empty(self.fencing_token, "fencing_token")
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise ValueError("ExecutionLease.expires_at must be later than issued_at")
        return self


class AttemptResult(BaseModel):
    """Immutable evidence produced by one terminal physical Attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str
    node_run_id: str
    ordinal: int = Field(ge=1)
    status: AttemptStatus
    result: Any | None = None
    error: str | None = None
    finished_at: datetime

    @model_validator(mode="after")
    def _validate_attempt_result(self) -> AttemptResult:
        _require_non_empty(self.attempt_id, "attempt_id")
        _require_non_empty(self.node_run_id, "node_run_id")
        if self.status not in TERMINAL_ATTEMPT_STATUSES:
            raise ValueError("AttemptResult requires a terminal physical Attempt status")
        return self

    @classmethod
    def from_attempt(cls, attempt: Attempt) -> AttemptResult:
        if attempt.status not in TERMINAL_ATTEMPT_STATUSES or attempt.finished_at is None:
            raise ValueError("AttemptResult can only be created from a terminal Attempt")
        return cls(
            attempt_id=attempt.attempt_id,
            node_run_id=attempt.node_run_id,
            ordinal=attempt.ordinal,
            status=attempt.status,
            result=attempt.result,
            error=attempt.error,
            finished_at=attempt.finished_at,
        )


class AcceptedNodeOutcome(BaseModel):
    """One physical result accepted as authoritative for a logical NodeRun disposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_run_id: str
    attempt_result: AttemptResult
    logical_status: RunStatus = RunStatus.COMPLETED
    accepted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _validate_accepted_outcome(self) -> AcceptedNodeOutcome:
        _require_non_empty(self.node_run_id, "node_run_id")
        if self.attempt_result.node_run_id != self.node_run_id:
            raise ValueError("accepted AttemptResult must belong to the NodeRun")
        if self.attempt_result.status is not AttemptStatus.COMPLETED:
            raise ValueError("only a physically completed AttemptResult can be accepted")
        if self.logical_status not in ACCEPTED_NODE_OUTCOME_STATUSES:
            raise ValueError("accepted Node outcome has an unsupported logical disposition")
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
    accepted_outcome: AcceptedNodeOutcome | None = None
    result: Any | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _validate_node_run(self) -> NodeRun:
        _require_non_empty(self.run_id, "run_id")
        _require_non_empty(self.node_id, "node_id")
        if self.accepted_outcome is not None:
            if self.accepted_outcome.node_run_id != self.node_run_id:
                raise ValueError("accepted outcome must belong to this NodeRun")
            if self.status is not self.accepted_outcome.logical_status:
                raise ValueError("NodeRun status must match its accepted logical outcome")
            if self.result != self.accepted_outcome.attempt_result.result:
                raise ValueError("NodeRun.result must project the accepted AttemptResult")
        _validate_finished_at(
            terminal=self.status in TERMINAL_RUN_STATUSES,
            finished_at=self.finished_at,
            subject="NodeRun",
        )
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
    execution_lease: ExecutionLease | None = None
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
        _require_non_empty(self.node_run_id, "node_run_id")
        if self.execution_lease is not None:
            if self.execution_lease.attempt_id != self.attempt_id:
                raise ValueError("ExecutionLease.attempt_id must match Attempt.attempt_id")
            if self.execution_lease.node_run_id != self.node_run_id:
                raise ValueError("ExecutionLease.node_run_id must match Attempt.node_run_id")
        _validate_finished_at(
            terminal=self.status in TERMINAL_ATTEMPT_STATUSES,
            finished_at=self.finished_at,
            subject="Attempt",
        )
        return self


__all__ = [
    "ACCEPTED_NODE_OUTCOME_STATUSES",
    "TERMINAL_ATTEMPT_STATUSES",
    "TERMINAL_RUN_STATUSES",
    "AcceptedNodeOutcome",
    "Attempt",
    "AttemptResult",
    "AttemptStatus",
    "ExecutionLease",
    "GraphSnapshot",
    "NodeRun",
    "Run",
    "RunStatus",
]
