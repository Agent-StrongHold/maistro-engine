"""RunStore-compatible lifecycle view over durable Graph persistence.

The durable Graph record already owns the canonical Run and NodeRuns. This
adapter keeps physical Attempts in that same optimistic-concurrency envelope so
AttemptExecutionService can operate without introducing a second lifecycle
store or dual-writing execution identity.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable

from maistro.runs.lifecycle import transition_attempt, transition_node_run, transition_run
from maistro.runs.model import (
    TERMINAL_RUN_STATUSES,
    Attempt,
    AttemptStatus,
    NodeRun,
    Run,
    RunStatus,
)
from maistro.runs.store import ActiveAttemptExists, RunIntegrityError

from .protocol import DurableRunStore
from .types import DurableRunRecord


class DurableRunExecutionStore:
    """Expose canonical execution lifecycle operations over one durable Run store."""

    def __init__(self, store: DurableRunStore) -> None:
        self._store = store
        self._lock = asyncio.Lock()

    async def get_run(self, run_id: str) -> Run | None:
        record = await self._store.get(run_id)
        return record.run.model_copy(deep=True) if record is not None else None

    async def transition_run(
        self,
        run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> Run:
        updated = await self._mutate(
            run_id,
            lambda record: self._with_run(
                record,
                transition_run(record.run, target, at=at, result=result, error=error),
            ),
        )
        return updated.run.model_copy(deep=True)

    async def get_node_run(self, node_run_id: str) -> NodeRun | None:
        record = await self._record_for_node_run(node_run_id)
        if record is None:
            return None
        node_run = next(item for item in record.node_runs if item.node_run_id == node_run_id)
        return node_run.model_copy(deep=True)

    async def list_node_runs(self, run_id: str) -> list[NodeRun]:
        record = await self._store.get(run_id)
        if record is None:
            raise RunIntegrityError(f"Run {run_id!r} does not exist")
        return [node_run.model_copy(deep=True) for node_run in record.node_runs]

    async def transition_node_run(
        self,
        node_run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> NodeRun:
        record = await self._record_for_node_run(node_run_id)
        if record is None:
            raise RunIntegrityError(f"NodeRun {node_run_id!r} does not exist")
        run_id = record.run_id

        def update(current: DurableRunRecord) -> DurableRunRecord:
            node_runs = list(current.node_runs)
            for index, node_run in enumerate(node_runs):
                if node_run.node_run_id != node_run_id:
                    continue
                node_runs[index] = transition_node_run(
                    node_run,
                    target,
                    at=at,
                    result=result,
                    error=error,
                )
                return current.model_copy(update={"node_runs": tuple(node_runs)})
            raise RunIntegrityError(f"NodeRun {node_run_id!r} does not exist")

        updated = await self._mutate(run_id, update)
        node_run = next(item for item in updated.node_runs if item.node_run_id == node_run_id)
        return node_run.model_copy(deep=True)

    async def create_attempt(
        self,
        node_run_id: str,
        *,
        runtime_id: str = "python",
        executor_id: str = "",
        deadline_at: datetime | None = None,
        resume_checkpoint_id: str | None = None,
    ) -> Attempt:
        record = await self._record_for_node_run(node_run_id)
        if record is None:
            raise RunIntegrityError(f"NodeRun {node_run_id!r} does not exist")
        run_id = record.run_id
        created: Attempt | None = None

        def update(current: DurableRunRecord) -> DurableRunRecord:
            nonlocal created
            node_run = next(
                (item for item in current.node_runs if item.node_run_id == node_run_id),
                None,
            )
            if node_run is None:
                raise RunIntegrityError(f"NodeRun {node_run_id!r} does not exist")
            if node_run.status in TERMINAL_RUN_STATUSES:
                raise RunIntegrityError("cannot create Attempt under a terminal NodeRun")

            existing = [
                attempt for attempt in current.attempts if attempt.node_run_id == node_run_id
            ]
            if any(
                attempt.status in {AttemptStatus.CREATED, AttemptStatus.RUNNING}
                for attempt in existing
            ):
                raise ActiveAttemptExists(
                    f"NodeRun {node_run_id!r} already has an active Attempt"
                )
            created = Attempt(
                node_run_id=node_run_id,
                ordinal=max((attempt.ordinal for attempt in existing), default=0) + 1,
                runtime_id=runtime_id,
                executor_id=executor_id,
                deadline_at=deadline_at,
                resume_checkpoint_id=resume_checkpoint_id,
            )
            return current.model_copy(update={"attempts": (*current.attempts, created)})

        await self._mutate(run_id, update)
        assert created is not None
        return created.model_copy(deep=True)

    async def get_attempt(self, attempt_id: str) -> Attempt | None:
        record = await self._record_for_attempt(attempt_id)
        if record is None:
            return None
        attempt = next(item for item in record.attempts if item.attempt_id == attempt_id)
        return attempt.model_copy(deep=True)

    async def list_attempts(self, node_run_id: str) -> list[Attempt]:
        record = await self._record_for_node_run(node_run_id)
        if record is None:
            raise RunIntegrityError(f"NodeRun {node_run_id!r} does not exist")
        return [
            attempt.model_copy(deep=True)
            for attempt in record.attempts
            if attempt.node_run_id == node_run_id
        ]

    async def transition_attempt(
        self,
        attempt_id: str,
        target: AttemptStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
        metrics: dict[str, object] | None = None,
    ) -> Attempt:
        record = await self._record_for_attempt(attempt_id)
        if record is None:
            raise RunIntegrityError(f"Attempt {attempt_id!r} does not exist")
        run_id = record.run_id

        def update(current: DurableRunRecord) -> DurableRunRecord:
            attempts = list(current.attempts)
            for index, attempt in enumerate(attempts):
                if attempt.attempt_id != attempt_id:
                    continue
                attempts[index] = transition_attempt(
                    attempt,
                    target,
                    at=at,
                    result=result,
                    error=error,
                    metrics=metrics,
                )
                return current.model_copy(update={"attempts": tuple(attempts)})
            raise RunIntegrityError(f"Attempt {attempt_id!r} does not exist")

        updated = await self._mutate(run_id, update)
        attempt = next(item for item in updated.attempts if item.attempt_id == attempt_id)
        return attempt.model_copy(deep=True)

    async def _record_for_node_run(self, node_run_id: str) -> DurableRunRecord | None:
        # DurableRunStore is keyed by Run, so discovery is intentionally narrow:
        # execution callers already know the containing Run through persisted NodeRuns.
        for status in RunStatus:
            records = await self._store.list_by_status(status, limit=1000)
            for record in records:
                if any(item.node_run_id == node_run_id for item in record.node_runs):
                    return record
        return None

    async def _record_for_attempt(self, attempt_id: str) -> DurableRunRecord | None:
        for status in RunStatus:
            records = await self._store.list_by_status(status, limit=1000)
            for record in records:
                if any(item.attempt_id == attempt_id for item in record.attempts):
                    return record
        return None

    async def _mutate(
        self,
        run_id: str,
        mutate: Callable[[DurableRunRecord], DurableRunRecord],
    ) -> DurableRunRecord:
        async with self._lock:
            current = await self._store.get(run_id)
            if current is None:
                raise RunIntegrityError(f"Run {run_id!r} does not exist")
            changed = mutate(current)
            candidate = changed.model_copy(update={"version": current.version + 1})
            return await self._store.update(candidate)

    @staticmethod
    def _with_run(record: DurableRunRecord, run: Run) -> DurableRunRecord:
        return record.model_copy(update={"run": run})


__all__ = ["DurableRunExecutionStore"]
