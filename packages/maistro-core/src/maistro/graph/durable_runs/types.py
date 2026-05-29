"""Durable run record types.

These are the *persisted* shape — what the executor checkpoints between
node steps. JSON-serializable so any backend (SQLite, Postgres, …) can
round-trip them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(StrEnum):
    """Top-level state for a durable run."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED_WAIT = "paused_wait"  # external condition (Jira subtasks, etc.)
    PAUSED_HITL = "paused_hitl"  # waiting on human input
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodePhase(StrEnum):
    """Per-node phase as a run progresses."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class DurableNodeRecord(BaseModel):
    """A single node's result snapshot inside a durable run."""

    model_config = ConfigDict(extra="ignore")

    node_id: str
    kind: str = ""
    phase: NodePhase = NodePhase.PENDING
    output: dict[str, Any] | None = None  # serialized output (Pydantic .model_dump())
    latency_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    model_used: str | None = None
    cost_usd: float = 0.0
    pause_metadata: dict[str, Any] = Field(default_factory=dict)
    resume_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # Attempt count (incremented per resume so the optimizer can score
    # "this node took N tries to converge").
    attempts: int = 0


class DurableRunRecord(BaseModel):
    """Top-level durable run snapshot.

    The full DAG topology is captured under `dag_snapshot` so a later
    executor can replay or resume even if the live DagBuilder definition
    has changed since the run started.
    """

    model_config = ConfigDict(extra="ignore")

    run_id: str
    dag_id: str
    dag_snapshot: dict[str, Any]  # serialized DAGFile / GraphConfig
    inputs: dict[str, Any] = Field(default_factory=dict)
    status: RunStatus = RunStatus.PENDING
    # Cursor: which node is "next to run" after the current checkpoint. None
    # at the start (use dag.entry); set after every step.
    current_node_id: str | None = None
    # Ordered history of node results.
    node_records: list[DurableNodeRecord] = Field(default_factory=list)
    # Lifted from the graph blackboard between checkpoints so dashboard
    # accumulators, node_annotations, etc. survive a pause.
    blackboard_snapshot: dict[str, Any] = Field(default_factory=dict)
    # HITL: keyed by node_id, value is the user's answer payload (set by
    # POST /v1/dag-runs/{run_id}/answer).
    hitl_answers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Wait: when status==paused_wait, the earliest time the executor should
    # try to re-poll. The runtime scheduler reads this.
    resume_at: datetime | None = None
    # Identity + scope.
    user_id: str | None = None
    project_id: str | None = None
    # Lifecycle timestamps.
    started_at: datetime
    last_step_at: datetime
    finished_at: datetime | None = None
    # On failure.
    error_code: str | None = None
    error_message: str | None = None
    # Sequence number — bumps on every checkpoint write so concurrent
    # writers can do optimistic concurrency control (avoid double-resume).
    version: int = 0
