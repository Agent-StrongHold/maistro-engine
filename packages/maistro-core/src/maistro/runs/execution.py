"""Canonical Attempt -> ExecutionRuntime execution seam.

This service owns the domain-side ordering around one physical try: prepare the
logical Run/NodeRun, create and persist the Attempt, mark it running, invoke
Runtime using ``attempt_id`` as the physical execution identity, persist the
terminal Attempt outcome, then perform policy-neutral logical reconciliation.
Runtime never mutates Run/NodeRun state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from maistro.runs.model import Attempt, AttemptStatus
from maistro.runs.reconciliation import AttemptLifecycleReconciler, AttemptLifecycleStore
from maistro.runtime import ExecutionCallable, ExecutionRuntime, RuntimeDeadlineExceeded

AttemptReconciler = Callable[[Attempt], Awaitable[None]]


@runtime_checkable
class AttemptExecutionStore(AttemptLifecycleStore, Protocol):
    async def create_attempt(
        self,
        node_run_id: str,
        *,
        runtime_id: str = "python",
        executor_id: str = "",
        deadline_at: datetime | None = None,
        resume_checkpoint_id: str | None = None,
    ) -> Attempt: ...

    async def transition_attempt(
        self,
        attempt_id: str,
        target: AttemptStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
        metrics: dict[str, object] | None = None,
    ) -> Attempt: ...


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
        reconcile_logical: bool = True,
    ) -> Attempt:
        """Create, run, terminalize, and optionally defer successful reconciliation.

        ``reconcile_logical=False`` allows Graph-like domains to interpret a
        *successfully completed* physical result themselves. It never suppresses
        reconciliation of cancellation, timeout, or failure: once physical work
        is gone those exceptional terminal facts must be reflected in logical
        persistence before the exception propagates.
        """
        deadline_at = None
        if timeout_s is not None:
            if timeout_s <= 0:
                raise ValueError("timeout_s must be > 0")
            deadline_at = datetime.now(UTC) + timedelta(seconds=timeout_s)

        await self._lifecycle.prepare_execution(node_run_id)
        attempt = await self._store.create_attempt(
            node_run_id,
            runtime_id=runtime_id or type(self._runtime).__name__,
            executor_id=executor_id,
            deadline_at=deadline_at,
            resume_checkpoint_id=resume_checkpoint_id,
        )
        attempt = await self._store.transition_attempt(attempt.attempt_id, AttemptStatus.RUNNING)

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
                error="execution cancelled",
            )
            await self._reconcile(terminal)
            raise
        except RuntimeDeadlineExceeded as exc:
            terminal = await self._terminalize(
                attempt.attempt_id,
                AttemptStatus.TIMED_OUT,
                error=str(exc),
            )
            await self._reconcile(terminal)
            raise
        except Exception as exc:
            terminal = await self._terminalize(
                attempt.attempt_id,
                AttemptStatus.FAILED,
                error=str(exc),
            )
            await self._reconcile(terminal)
            raise

        terminal = await self._terminalize(
            attempt.attempt_id,
            AttemptStatus.COMPLETED,
            result=result,
        )
        if reconcile_logical:
            await self._reconcile(terminal)
        return terminal

    async def cancel(self, attempt_id: str) -> bool:
        return await self._runtime.cancel(attempt_id)

    async def _terminalize(
        self,
        attempt_id: str,
        status: AttemptStatus,
        *,
        result: object | None = None,
        error: str | None = None,
    ) -> Attempt:
        return await self._store.transition_attempt(
            attempt_id,
            status,
            result=result,
            error=error,
        )

    async def _reconcile(self, attempt: Attempt) -> None:
        await self._lifecycle.reconcile(attempt)
        if self._after_reconcile is not None:
            await self._after_reconcile(attempt.model_copy(deep=True))


__all__ = ["AttemptExecutionService", "AttemptExecutionStore", "AttemptReconciler"]
