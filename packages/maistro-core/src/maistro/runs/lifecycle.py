from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeVar

from maistro.runs.model import (
    Attempt,
    AttemptStatus,
    NodeRun,
    Run,
    RunStatus,
    TERMINAL_ATTEMPT_STATUSES,
    TERMINAL_RUN_STATUSES,
)

RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset({RunStatus.QUEUED, RunStatus.CANCELLED}),
    RunStatus.QUEUED: frozenset(
        {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.TIMED_OUT}
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING,
            RunStatus.PAUSED,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }
    ),
    RunStatus.WAITING: frozenset(
        {RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.CANCELLED, RunStatus.TIMED_OUT}
    ),
    RunStatus.PAUSED: frozenset(
        {RunStatus.QUEUED, RunStatus.CANCELLED, RunStatus.TIMED_OUT}
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.TIMED_OUT: frozenset(),
}

ATTEMPT_TRANSITIONS: dict[AttemptStatus, frozenset[AttemptStatus]] = {
    AttemptStatus.CREATED: frozenset({AttemptStatus.RUNNING, AttemptStatus.CANCELLED}),
    AttemptStatus.RUNNING: frozenset(
        {
            AttemptStatus.COMPLETED,
            AttemptStatus.FAILED,
            AttemptStatus.CANCELLED,
            AttemptStatus.TIMED_OUT,
            AttemptStatus.YIELDED,
        }
    ),
    AttemptStatus.COMPLETED: frozenset(),
    AttemptStatus.FAILED: frozenset(),
    AttemptStatus.CANCELLED: frozenset(),
    AttemptStatus.TIMED_OUT: frozenset(),
    AttemptStatus.YIELDED: frozenset(),
}


class InvalidLifecycleTransition(ValueError):
    pass


TLogical = TypeVar("TLogical", Run, NodeRun)


def _now(value: datetime | None) -> datetime:
    return value if value is not None else datetime.now(UTC)


def _validate_run_transition(current: RunStatus, target: RunStatus) -> None:
    if target not in RUN_TRANSITIONS[current]:
        raise InvalidLifecycleTransition(f"illegal transition: {current.value} -> {target.value}")


def _transition_logical(
    record: TLogical,
    target: RunStatus,
    *,
    at: datetime | None = None,
    result: object | None = None,
    error: str | None = None,
) -> TLogical:
    _validate_run_transition(record.status, target)
    timestamp = _now(at)
    values = record.model_dump(mode="python")
    values["status"] = target
    values["updated_at"] = timestamp
    values["result"] = result
    values["error"] = error
    if target is RunStatus.RUNNING and record.started_at is None:
        values["started_at"] = timestamp
    if target in TERMINAL_RUN_STATUSES:
        values["finished_at"] = timestamp
    return type(record).model_validate(values)


def transition_run(
    run: Run,
    target: RunStatus,
    *,
    at: datetime | None = None,
    result: object | None = None,
    error: str | None = None,
) -> Run:
    return _transition_logical(run, target, at=at, result=result, error=error)


def transition_node_run(
    node_run: NodeRun,
    target: RunStatus,
    *,
    at: datetime | None = None,
    result: object | None = None,
    error: str | None = None,
) -> NodeRun:
    return _transition_logical(node_run, target, at=at, result=result, error=error)


def transition_attempt(
    attempt: Attempt,
    target: AttemptStatus,
    *,
    at: datetime | None = None,
    result: object | None = None,
    error: str | None = None,
    metrics: dict[str, object] | None = None,
) -> Attempt:
    if target not in ATTEMPT_TRANSITIONS[attempt.status]:
        raise InvalidLifecycleTransition(
            f"illegal transition: {attempt.status.value} -> {target.value}"
        )

    timestamp = _now(at)
    values = attempt.model_dump(mode="python")
    values["status"] = target
    values["result"] = result
    values["error"] = error
    if metrics is not None:
        values["metrics"] = metrics
    if target is AttemptStatus.RUNNING and attempt.started_at is None:
        values["started_at"] = timestamp
    if target in TERMINAL_ATTEMPT_STATUSES:
        values["finished_at"] = timestamp
    return Attempt.model_validate(values)


__all__ = [
    "ATTEMPT_TRANSITIONS",
    "InvalidLifecycleTransition",
    "RUN_TRANSITIONS",
    "transition_attempt",
    "transition_node_run",
    "transition_run",
]
