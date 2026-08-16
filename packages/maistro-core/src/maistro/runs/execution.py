"""Canonical Attempt -> ExecutionRuntime execution seam.

This service owns the domain-side ordering around one physical try: prepare the
logical Run/NodeRun, create and persist the Attempt, mark it running, invoke
Runtime using ``attempt_id`` as the physical execution identity, and persist the
terminal physical outcome. Simple callers may retain default logical
reconciliation; richer domains may defer acceptance and assign the logical
NodeRun disposition themselves. Runtime never mutates Run/NodeRun state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from maistro.runs.execution_store import AttemptExecutionStore
from maistro.runs.model import Attempt, AttemptStatus
from maistro.runs.reconciliation import AttemptLifecycleReconciler
from maistro.runs.store import RunIntegrityError
from maistro.runtime import ExecutionCallable, ExecutionRuntime, RuntimeDeadlineExceeded

AttemptReconciler = Callable[[Attempt], Awaitable[None]]


class AttemptExecutionService:
    """Execute physical Attempts while keeping lifecycle authority in domain code."""

    def __init__(
        self,
        *,
        store: AttemptExecutionStore,
        runtime: ExecutionRuntime,
        reconciler: AttemptReconciler | None = None,
    ) -> None:
        self._store = store
        self._runtime = runtime
        self._lifecycle = AttemptLifecycleReconciler(store)
        self._after_reconcile = reconciler

    async def execute(
        self,
        node_run_id: str,
        work_item: Any,
        execution_context: Any,
        *,
        executor: ExecutionCallable,
        executor_id: str = "",
        runtime_id: str | None = None,
        timeout_s: float | None = None,
        resume_checkpoint_id: str | None = None,
        reconcile_completed: bool = True,
    ) -> Attempt:
        """Run one fenced physical Attempt.

        ``reconcile_completed=False`` preserves a physically completed Attempt
        while leaving the NodeRun running so domain logic can explicitly accept
        that physical result as COMPLETED, FAILED, WAITING, or PAUSED. Physical
        failures/cancellation/timeouts still reconcile immediately because no
        successful result exists for domain acceptance.

        A completed physical result awaiting acceptance is authoritative
        candidate evidence. It must be reconciled or explicitly rejected by the
        owning domain before another physical Attempt can be dispatched, or a
        retry could duplicate external side effects.
        """
        await self._reject_unaccepted_completion(node_run_id)

        deadline_at = None
        if timeout_s is not None:
            if timeout_s <= 0:
                raise ValueError("timeout_s must be > 0")
            deadline_at = datetime.now(UTC) + timedelta(seconds=timeout_s)

        runtime_name = runtime_id or type(self._runtime).__name__
        await self._lifecycle.prepare_execution(node_run_id)
        attempt = await self._store.create_attempt(
            node_run_id,
            runtime_id=runtime_name,
            executor_id=executor_id,
            deadline_at=deadline_at,
            resume_checkpoint_id=resume_checkpoint_id,
            lease_holder=executor_id or runtime_name,
        )
        lease = attempt.execution_lease
        if lease is None:
            raise RunIntegrityError("store-created Attempt is missing its execution lease")
        token = lease.fencing_token
        attempt = await self._store.transition_attempt(
            attempt.attempt_id,
            AttemptStatus.RUNNING,
            fencing_token=token,
        )

        try:
            result = await self._runtime.execute(
                work_item,
                execution_context,
                execution_id=attempt.attempt_id,
                executor=executor,
                timeout_s=timeout_s,
            )
        except asyncio.CancelledError:
            terminal = await self._terminalize(
                attempt.attempt_id,
                AttemptStatus.CANCELLED,
                fencing_token=token,
                error="execution cancelled",
            )
            await self._reconcile(terminal)
            raise
        except RuntimeDeadlineExceeded as exc:
            terminal = await self._terminalize(
                attempt.attempt_id,
                AttemptStatus.TIMED_OUT,
                fencing_token=token,
                error=str(exc),
            )
            await self._reconcile(terminal)
            raise
        except Exception as exc:
            terminal = await self._terminalize(
                attempt.attempt_id,
                AttemptStatus.FAILED,
                fencing_token=token,
                error=str(exc),
            )
            await self._reconcile(terminal)
            raise

        terminal = await self._terminalize(
            attempt.attempt_id,
            AttemptStatus.COMPLETED,
            fencing_token=token,
            result=result,
        )
        if reconcile_completed:
            await self._reconcile(terminal)
        return terminal

    async def _reject_unaccepted_completion(self, node_run_id: str) -> None:
        node_run = await self._store.get_node_run(node_run_id)
        if node_run is None:
            raise RunIntegrityError(f"NodeRun {node_run_id!r} does not exist")
        if node_run.accepted_outcome is not None:
            return
        attempts = await self._store.list_attempts(node_run_id)
        pending = next(
            (attempt for attempt in reversed(attempts) if attempt.status is AttemptStatus.COMPLETED),
            None,
        )
        if pending is not None:
            raise RunIntegrityError(
                "completed Attempt awaits domain acceptance; reconcile persisted evidence before redispatch"
            )

    async def cancel(self, attempt_id: str) -> bool:
        return await self._runtime.cancel(attempt_id)

    async def _terminalize(
        self,
        attempt_id: str,
        status: AttemptStatus,
        *,
        fencing_token: str,
        result: object | None = None,
        error: str | None = None,
    ) -> Attempt:
        return await self._store.transition_attempt(
            attempt_id,
            status,
            result=result,
            error=error,
            fencing_token=fencing_token,
        )

    async def _reconcile(self, attempt: Attempt) -> None:
        await self._lifecycle.reconcile(attempt)
        if self._after_reconcile is not None:
            await self._after_reconcile(attempt.model_copy(deep=True))


__all__ = ["AttemptExecutionService", "AttemptReconciler"]
