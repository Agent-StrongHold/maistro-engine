"""Attempt execution adapter over one durable Graph checkpoint envelope."""

from __future__ import annotations

import asyncio
from datetime import datetime

from maistro.graph.durable_runs.protocol import DurableRunStore
from maistro.graph.durable_runs.types import DurableRunRecord
from maistro.runs.execution_store import AttemptExecutionStore
from maistro.runs.lifecycle import transition_attempt, transition_node_run, transition_run
from maistro.runs.model import (
    TERMINAL_RUN_STATUSES,
    AcceptedNodeOutcome,
    Attempt,
    AttemptStatus,
    ExecutionLease,
    NodeRun,
    Run,
    RunStatus,
)
from maistro.runs.store import (
    ActiveAttemptExists,
    AttemptNotFound,
    NodeRunNotFound,
    RunIntegrityError,
    RunNotFound,
    StaleExecutionFence,
)


class DurableAttemptExecutionStore(AttemptExecutionStore):
    """Expose one durable Graph Run through the canonical Attempt persistence seam.

    Durable Graph traversal still owns the checkpoint envelope. This adapter
    serializes lifecycle mutations inside the process and persists each mutation
    through the store's optimistic version contract. It does not create Runs or
    NodeRuns and therefore cannot become a competing ownership repository.
    """

    def __init__(self, durable_store: DurableRunStore, *, run_id: str) -> None:
        self._durable_store = durable_store
        self._run_id = run_id
        self._lock = asyncio.Lock()

    async def get_run(self, run_id: str) -> Run | None:
        if run_id != self._run_id:
            return None
        record = await self._durable_store.get(run_id)
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
        if run_id != self._run_id:
            raise RunNotFound(run_id)
        async with self._lock:
            record = await self._require_record()
            updated = transition_run(record.run, target, at=at, result=result, error=error)
            await self._persist(record, run=updated)
            return updated.model_copy(deep=True)

    async def get_node_run(self, node_run_id: str) -> NodeRun | None:
        record = await self._durable_store.get(self._run_id)
        if record is None:
            return None
        node_run = next((item for item in record.node_runs if item.node_run_id == node_run_id), None)
        return node_run.model_copy(deep=True) if node_run is not None else None

    async def list_node_runs(self, run_id: str) -> list[NodeRun]:
        if run_id != self._run_id:
            raise RunNotFound(run_id)
        record = await self._require_record()
        return [item.model_copy(deep=True) for item in record.node_runs]

    async def transition_node_run(
        self,
        node_run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
        accepted_outcome: AcceptedNodeOutcome | None = None,
    ) -> NodeRun:
        async with self._lock:
            record = await self._require_record()
            index = self._node_run_index(record, node_run_id)
            updated = transition_node_run(
                record.node_runs[index],
                target,
                at=at,
                result=result,
                error=error,
                accepted_outcome=accepted_outcome,
            )
            node_runs = list(record.node_runs)
            node_runs[index] = updated
            await self._persist(record, node_runs=tuple(node_runs))
            return updated.model_copy(deep=True)

    async def create_attempt(
        self,
        node_run_id: str,
        *,
        runtime_id: str = "python",
        executor_id: str = "",
        deadline_at: datetime | None = None,
        resume_checkpoint_id: str | None = None,
        lease_holder: str | None = None,
    ) -> Attempt:
        async with self._lock:
            record = await self._require_record()
            node_run = record.node_runs[self._node_run_index(record, node_run_id)]
            if node_run.status in TERMINAL_RUN_STATUSES:
                raise RunIntegrityError("cannot create Attempt under a terminal NodeRun")
            existing = [item for item in record.attempts if item.node_run_id == node_run_id]
            if any(
                item.status in {AttemptStatus.CREATED, AttemptStatus.RUNNING} for item in existing
            ):
                raise ActiveAttemptExists(f"NodeRun {node_run_id!r} already has an active Attempt")
            ordinal = max((item.ordinal for item in existing), default=0) + 1
            attempt = Attempt(
                node_run_id=node_run_id,
                ordinal=ordinal,
                runtime_id=runtime_id,
                executor_id=executor_id,
                deadline_at=deadline_at,
                resume_checkpoint_id=resume_checkpoint_id,
            )
            if lease_holder is not None:
                lease = ExecutionLease(
                    node_run_id=node_run_id,
                    attempt_id=attempt.attempt_id,
                    lease_epoch=ordinal,
                    holder=lease_holder,
                )
                attempt = Attempt.model_validate(
                    {**attempt.model_dump(mode="python"), "execution_lease": lease}
                )
            await self._persist(record, attempts=(*record.attempts, attempt))
            return attempt.model_copy(deep=True)

    async def get_attempt(self, attempt_id: str) -> Attempt | None:
        record = await self._durable_store.get(self._run_id)
        if record is None:
            return None
        attempt = next((item for item in record.attempts if item.attempt_id == attempt_id), None)
        return attempt.model_copy(deep=True) if attempt is not None else None

    async def list_attempts(self, node_run_id: str) -> list[Attempt]:
        record = await self._require_record()
        self._node_run_index(record, node_run_id)
        return [
            item.model_copy(deep=True)
            for item in record.attempts
            if item.node_run_id == node_run_id
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
        fencing_token: str | None = None,
    ) -> Attempt:
        async with self._lock:
            record = await self._require_record()
            index = self._attempt_index(record, attempt_id)
            current = record.attempts[index]
            self._validate_fence(current, fencing_token)
            updated = transition_attempt(
                current,
                target,
                at=at,
                result=result,
                error=error,
                metrics=metrics,
            )
            attempts = list(record.attempts)
            attempts[index] = updated
            await self._persist(record, attempts=tuple(attempts))
            return updated.model_copy(deep=True)

    async def _require_record(self) -> DurableRunRecord:
        record = await self._durable_store.get(self._run_id)
        if record is None:
            raise RunNotFound(self._run_id)
        return record

    async def _persist(self, record: DurableRunRecord, **updates: object) -> DurableRunRecord:
        values = record.model_dump(mode="python")
        values.update(updates)
        values["version"] = record.version + 1
        return await self._durable_store.update(DurableRunRecord.model_validate(values))

    @staticmethod
    def _node_run_index(record: DurableRunRecord, node_run_id: str) -> int:
        for index, item in enumerate(record.node_runs):
            if item.node_run_id == node_run_id:
                return index
        raise NodeRunNotFound(node_run_id)

    @staticmethod
    def _attempt_index(record: DurableRunRecord, attempt_id: str) -> int:
        for index, item in enumerate(record.attempts):
            if item.attempt_id == attempt_id:
                return index
        raise AttemptNotFound(attempt_id)

    @staticmethod
    def _validate_fence(attempt: Attempt, fencing_token: str | None) -> None:
        lease = attempt.execution_lease
        if lease is not None and fencing_token != lease.fencing_token:
            raise StaleExecutionFence(
                f"Attempt {attempt.attempt_id!r} update rejected by execution fence"
            )


__all__ = ["DurableAttemptExecutionStore"]
