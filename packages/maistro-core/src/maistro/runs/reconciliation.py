"""Policy-neutral reconciliation between physical Attempts and logical execution.

The reconciler owns universal lifecycle bookkeeping only. It never decides
whether a failed/timed-out/cancelled Attempt is eligible for retry and it never
decides Graph traversal completion. Physical completion is first captured as
immutable AttemptResult evidence; only an explicit AcceptedNodeOutcome makes
that result authoritative for the logical NodeRun.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from maistro.runs.model import (
    TERMINAL_ATTEMPT_STATUSES,
    TERMINAL_RUN_STATUSES,
    AcceptedNodeOutcome,
    Attempt,
    AttemptResult,
    AttemptStatus,
    NodeRun,
    Run,
    RunStatus,
)
from maistro.runs.store import RunIntegrityError


@runtime_checkable
class AttemptLifecycleStore(Protocol):
    """Minimal persisted lifecycle contract required around physical Attempts."""

    async def get_run(self, run_id: str) -> Run | None: ...

    async def transition_run(
        self,
        run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> Run: ...

    async def get_node_run(self, node_run_id: str) -> NodeRun | None: ...

    async def list_node_runs(self, run_id: str) -> list[NodeRun]: ...

    async def transition_node_run(
        self,
        node_run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> NodeRun: ...

    async def get_attempt(self, attempt_id: str) -> Attempt | None: ...


class AttemptLifecycleReconciler:
    """Keep Run/NodeRun activity consistent with canonical physical Attempts."""

    def __init__(self, store: AttemptLifecycleStore) -> None:
        self._store = store

    async def prepare_execution(self, node_run_id: str) -> NodeRun:
        """Put the containing Run and NodeRun in ``running`` before a physical try."""
        node_run = await self._require_node_run(node_run_id)
        run = await self._require_run(node_run.run_id)
        await self._ensure_run_running(run)
        return await self._ensure_node_run_running(node_run)

    async def reconcile(self, attempt: Attempt) -> NodeRun:
        """Reconcile one already-persisted terminal Attempt into logical activity."""
        if attempt.status not in TERMINAL_ATTEMPT_STATUSES:
            raise RunIntegrityError("cannot reconcile a non-terminal Attempt")

        persisted = await self._store.get_attempt(attempt.attempt_id)
        if persisted is None:
            raise RunIntegrityError("cannot reconcile an Attempt that is not persisted")
        if persisted.status is not attempt.status:
            raise RunIntegrityError("Attempt reconciliation status differs from persisted state")

        node_run = await self._require_node_run(attempt.node_run_id)
        if attempt.status is AttemptStatus.COMPLETED:
            result = AttemptResult.from_attempt(persisted)
            outcome = AcceptedNodeOutcome(
                node_run_id=node_run.node_run_id,
                attempt_result=result,
            )
            return await self._accept_node_outcome(node_run, outcome)

        parked = await self._park_node_run(node_run, attempt)
        await self._park_run_if_inactive(parked.run_id)
        return parked

    async def _ensure_run_running(self, run: Run) -> Run:
        if run.status in TERMINAL_RUN_STATUSES:
            raise RunIntegrityError("cannot execute Attempt under a terminal Run")
        if run.status is RunStatus.RUNNING:
            return run
        if run.status in {RunStatus.CREATED, RunStatus.PAUSED}:
            run = await self._store.transition_run(run.run_id, RunStatus.QUEUED)
        if run.status in {RunStatus.QUEUED, RunStatus.WAITING}:
            return await self._store.transition_run(run.run_id, RunStatus.RUNNING)
        raise RunIntegrityError(
            f"Run {run.run_id!r} cannot enter running from {run.status.value!r}"
        )

    async def _ensure_node_run_running(self, node_run: NodeRun) -> NodeRun:
        if node_run.status in TERMINAL_RUN_STATUSES:
            raise RunIntegrityError("cannot execute Attempt under a terminal NodeRun")
        if node_run.status is RunStatus.RUNNING:
            return node_run
        if node_run.status in {RunStatus.CREATED, RunStatus.PAUSED}:
            node_run = await self._store.transition_node_run(
                node_run.node_run_id,
                RunStatus.QUEUED,
            )
        if node_run.status in {RunStatus.QUEUED, RunStatus.WAITING}:
            return await self._store.transition_node_run(
                node_run.node_run_id,
                RunStatus.RUNNING,
            )
        raise RunIntegrityError(
            f"NodeRun {node_run.node_run_id!r} cannot enter running from {node_run.status.value!r}"
        )

    async def _accept_node_outcome(
        self,
        node_run: NodeRun,
        outcome: AcceptedNodeOutcome,
    ) -> NodeRun:
        if node_run.status is RunStatus.COMPLETED:
            accepted = node_run.accepted_outcome
            if accepted is None:
                # Pre-upgrade completed rows projected the physical result but
                # did not persist AcceptedNodeOutcome. The lifecycle/store
                # permit exactly this evidence-only backfill after validating
                # the referenced Attempt against canonical storage.
                return await self._store.transition_node_run(
                    node_run.node_run_id,
                    RunStatus.COMPLETED,
                    result=node_run.result,
                    accepted_outcome=outcome,
                )
            if accepted.attempt_result != outcome.attempt_result:
                raise RunIntegrityError("NodeRun already has a different accepted outcome")
            return node_run
        if node_run.status is not RunStatus.RUNNING:
            raise RunIntegrityError("completed Attempt requires a running logical NodeRun")
        return await self._store.transition_node_run(
            node_run.node_run_id,
            RunStatus.COMPLETED,
            result=outcome.attempt_result.result,
            accepted_outcome=outcome,
        )

    async def _park_node_run(self, node_run: NodeRun, attempt: Attempt) -> NodeRun:
        if node_run.status in TERMINAL_RUN_STATUSES or node_run.status in {
            RunStatus.WAITING,
            RunStatus.PAUSED,
        }:
            return node_run
        if node_run.status is not RunStatus.RUNNING:
            raise RunIntegrityError("terminal Attempt requires a running logical NodeRun")
        return await self._store.transition_node_run(
            node_run.node_run_id,
            RunStatus.WAITING,
            error=attempt.error,
        )

    async def _park_run_if_inactive(self, run_id: str) -> Run:
        run = await self._require_run(run_id)
        if run.status is not RunStatus.RUNNING:
            return run
        node_runs = await self._store.list_node_runs(run_id)
        if any(
            node_run.status in {RunStatus.CREATED, RunStatus.QUEUED, RunStatus.RUNNING}
            for node_run in node_runs
        ):
            return run
        return await self._store.transition_run(run_id, RunStatus.WAITING)

    async def _require_run(self, run_id: str) -> Run:
        run = await self._store.get_run(run_id)
        if run is None:
            raise RunIntegrityError(f"Run {run_id!r} does not exist")
        return run

    async def _require_node_run(self, node_run_id: str) -> NodeRun:
        node_run = await self._store.get_node_run(node_run_id)
        if node_run is None:
            raise RunIntegrityError(f"NodeRun {node_run_id!r} does not exist")
        return node_run


__all__ = ["AttemptLifecycleReconciler", "AttemptLifecycleStore"]
