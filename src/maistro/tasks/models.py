"""Task domain models — Pydantic schemas for the task API."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from maistro.agents.types import ExecutionMode


class TaskStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    CODING = "coding"
    REVIEWING = "reviewing"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCreate(BaseModel):
    """Request body for POST /tasks."""

    description: str
    workspace: str = "/tmp/maistro-workspace"
    tier: int | None = None
    branch: str | None = None
    constraints: list[str] = Field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.WORKFLOW


class TaskProgress(BaseModel):
    subtasks: int = 0
    completed: int = 0
    current: str = ""


class TaskResult(BaseModel):
    files_changed: list[str] = Field(default_factory=list)
    tests_passed: int | None = None
    tests_failed: int | None = None
    review_score: float | None = None
    branch: str | None = None
    commit: str | None = None
    error: str | None = None


class TaskResponse(BaseModel):
    """Response body for GET /tasks/:id."""

    task_id: str
    status: TaskStatus
    description: str
    workspace: str
    tier: int
    phase: str | None = None
    progress: TaskProgress = Field(default_factory=TaskProgress)
    result: TaskResult | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]
