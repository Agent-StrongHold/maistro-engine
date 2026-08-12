"""Durable run record types.

These are the persisted graph-adapter shape. Canonical execution identity is
carried alongside graph-specific checkpoint state so resume/recovery never
loses workspace ownership, lineage, or correlation.
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
    PAUSED_WAIT = "paused_wait"
    PAUSED_HITL = "paused_hitl"
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
    output: dict[str, Any] | None = None
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
    attempts: int = 0


class DurableRunRecord(BaseModel):
    """Top-level durable graph snapshot.

    `project_id` remains the persisted compatibility name for workspace
    ownership. New runtime-created records also persist root/parent/correlation
    identity. Those fields are optional so records written before the runtime
    spine remain readable and resumable through legacy entry points.
    """

    model_config = ConfigDict(extra="ignore")

    run_id: str
    dag_id: str
    dag_snapshot: dict[str, Any]
    inputs: dict[str, Any] = Field(default_factory=dict)
    status: RunStatus = RunStatus.PENDING
    current_node_id: str | None = None
    node_records: list[DurableNodeRecord] = Field(default_factory=list)
    blackboard_snapshot: dict[str, Any] = Field(default_factory=dict)
    hitl_answers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    resume_at: datetime | None = None

    # Identity + scope. `project_id` is workspace_id at the compatibility
    # boundary until the persistence schema is deliberately migrated.
    user_id: str | None = None
    project_id: str | None = None
    run_kind: str = "graph"
    root_run_id: str | None = None
    parent_run_id: str | None = None
    correlation_id: str | None = None

    started_at: datetime
    last_step_at: datetime
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    version: int = 0
