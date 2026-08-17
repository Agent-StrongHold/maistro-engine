from __future__ import annotations

import math
import uuid
from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

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


class _FrozenDict(dict[Any, Any]):
    """Dict-shaped immutable-by-value evidence that remains JSON serializable."""

    @staticmethod
    def _deny(*_args: object, **_kwargs: object) -> None:
        raise TypeError("AttemptResult evidence is immutable")

    __setitem__ = _deny
    __delitem__ = _deny
    clear = _deny
    pop = _deny
    setdefault = _deny
    update = _deny

    def popitem(self) -> tuple[Any, Any]:
        raise TypeError("AttemptResult evidence is immutable")

    def __deepcopy__(self, _memo: dict[int, object]) -> _FrozenDict:
        return self


class _FrozenList(list[Any]):
    """List-shaped immutable-by-value evidence that preserves list equality/JSON shape."""

    @staticmethod
    def _deny(*_args: object, **_kwargs: object) -> None:
        raise TypeError("AttemptResult evidence is immutable")

    __setitem__ = _deny
    __delitem__ = _deny
    append = _deny
    clear = _deny
    extend = _deny
    insert = _deny
    pop = _deny
    remove = _deny
    reverse = _deny
    sort = _deny

    def __iadd__(self, _values: Iterable[Any]) -> Self:
        raise TypeError("AttemptResult evidence is immutable")

    def __imul__(self, _value: int) -> Self:
        raise TypeError("AttemptResult evidence is immutable")

    def __deepcopy__(self, _memo: dict[int, object]) -> _FrozenList:
        return self


def _freeze_evidence_value(value: Any) -> Any:
    """Detach and recursively freeze common mutable result containers."""
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze_evidence_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze_evidence_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_evidence_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_evidence_value(item) for item in value)
    if isinstance(value, BaseModel):
        return value.model_copy(deep=True)
    try:
        return deepcopy(value)
    except Exception:
        return value


def evidence_values_equal(left: Any, right: Any) -> bool:
    """Compare persisted projections, including non-reflexive numeric values such as NaN."""
    if left is right:
        return True
    if (
        isinstance(left, float)
        and isinstance(right, float)
        and math.isnan(left)
        and math.isnan(right)
    ):
        return True
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            evidence_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            evidence_values_equal(l_item, r_item)
            for l_item, r_item in zip(left, right, strict=True)
        )
    try:
        return bool(left == right)
    except Exception:
        return False


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


TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.TIMED_OUT,
    }
)


class AttemptStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    YIELDED = "yielded"


TERMINAL_ATTEMPT_STATUSES = frozenset(
    {
        AttemptStatus.COMPLETED,
        AttemptStatus.FAILED,
        AttemptStatus.CANCELLED,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.YIELDED,
    }
)


class Run(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=_id)
    workspace_id: str
    project_id: str
    graph: Graph
    status: RunStatus = RunStatus.CREATED
    result: Any = None
    error: str | None = None
    actor_principal_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def _validate(self) -> Run:
        _require_non_empty(self.run_id, "run_id")
        _require_non_empty(self.workspace_id, "workspace_id")
        _require_non_empty(self.project_id, "project_id")
        _validate_finished_at(
            terminal=self.status in TERMINAL_RUN_STATUSES,
            finished_at=self.finished_at,
            subject="Run",
        )
        return self


class AttemptResult(BaseModel):
    """Immutable physical evidence captured from one terminal Attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    attempt_id: str
    node_run_id: str
    ordinal: int
    status: AttemptStatus
    result: Any = None
    error: str | None = None
    metrics: dict[str, object] = Field(default_factory=dict)
    finished_at: datetime

    @model_validator(mode="after")
    def _validate(self) -> AttemptResult:
        if self.status not in TERMINAL_ATTEMPT_STATUSES:
            raise ValueError("AttemptResult requires a terminal Attempt status")
        _require_non_empty(self.attempt_id, "attempt_id")
        _require_non_empty(self.node_run_id, "node_run_id")
        object.__setattr__(self, "result", _freeze_evidence_value(self.result))
        object.__setattr__(self, "metrics", _FrozenDict(_freeze_evidence_value(self.metrics)))
        return self


class AcceptedNodeOutcome(BaseModel):
    """Authoritative logical acceptance of immutable physical Attempt evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_result: AttemptResult
    accepted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NodeRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_run_id: str = Field(default_factory=_id)
    run_id: str
    node_id: str
    ordinal: int
    status: RunStatus = RunStatus.CREATED
    result: Any = None
    accepted_outcome: AcceptedNodeOutcome | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def _validate(self) -> NodeRun:
        _require_non_empty(self.node_run_id, "node_run_id")
        _require_non_empty(self.run_id, "run_id")
        _require_non_empty(self.node_id, "node_id")
        if self.ordinal < 1:
            raise ValueError("NodeRun ordinal must be >= 1")
        _validate_finished_at(
            terminal=self.status in TERMINAL_RUN_STATUSES,
            finished_at=self.finished_at,
            subject="NodeRun",
        )
        if self.accepted_outcome is not None:
            evidence = self.accepted_outcome.attempt_result
            if evidence.node_run_id != self.node_run_id:
                raise ValueError("AcceptedNodeOutcome belongs to a different NodeRun")
            if evidence.status is not AttemptStatus.COMPLETED:
                raise ValueError("AcceptedNodeOutcome requires COMPLETED physical evidence")
            if self.status is not RunStatus.COMPLETED:
                raise ValueError("AcceptedNodeOutcome requires a COMPLETED NodeRun")
            if not evidence_values_equal(self.result, evidence.result):
                raise ValueError("NodeRun.result must project the accepted AttemptResult result")
        return self


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(default_factory=_id)
    node_run_id: str
    ordinal: int
    status: AttemptStatus = AttemptStatus.CREATED
    runtime_id: str = "python"
    executor_id: str = ""
    resume_checkpoint_id: str | None = None
    deadline_at: datetime | None = None
    result: Any = None
    error: str | None = None
    metrics: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def _validate(self) -> Attempt:
        _require_non_empty(self.attempt_id, "attempt_id")
        _require_non_empty(self.node_run_id, "node_run_id")
        if self.ordinal < 1:
            raise ValueError("Attempt ordinal must be >= 1")
        _validate_finished_at(
            terminal=self.status in TERMINAL_ATTEMPT_STATUSES,
            finished_at=self.finished_at,
            subject="Attempt",
        )
        return self

    def to_result(self) -> AttemptResult:
        if self.status not in TERMINAL_ATTEMPT_STATUSES or self.finished_at is None:
            raise ValueError("AttemptResult requires terminal physical evidence")
        return AttemptResult(
            attempt_id=self.attempt_id,
            node_run_id=self.node_run_id,
            ordinal=self.ordinal,
            status=self.status,
            result=self.result,
            error=self.error,
            metrics=self.metrics,
            finished_at=self.finished_at,
        )


__all__ = [
    "AcceptedNodeOutcome",
    "Attempt",
    "AttemptResult",
    "AttemptStatus",
    "evidence_values_equal",
    "NodeRun",
    "Run",
    "RunStatus",
    "TERMINAL_ATTEMPT_STATUSES",
    "TERMINAL_RUN_STATUSES",
]
