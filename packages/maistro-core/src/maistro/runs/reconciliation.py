"""Policy-neutral reconciliation between physical Attempts and logical execution.

The reconciler owns universal lifecycle bookkeeping only. It never decides
whether a failed/timed-out/cancelled Attempt is eligible for retry and it never
decides Graph traversal completion. Unsuccessful physical outcomes park the
logical NodeRun (and, when no other logical work is active, the Run) in
``waiting`` so persistence does not claim a worker is still running while
domain policy decides retry, resume, or terminalization.
"""

from __future__ import annotations

from maistro.runs.model import (
    TERMINAL_ATTEMPT_STATUSES,
    TERMINAL_RUN_STATUSES,
    Attempt,
    AttemptStatus,
    NodeRun,
    Run,
    RunStatus,
)
from maistro.runs.store import RunIntegrityError, RunStore


class AttemptLifecycleReconciler:
    """Keep Run/NodeRun activity consistent with canonical physical Attempts."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    async def prepare_execution(self, node_run_id: str) -> NodeRun:
        """Put the containing Run and NodeRun in ``running`` before a physical try."""

        node_run = await self._require_node_run(node_run_id)
        run = await self._require_run(node_run.run_id)
        await self._ensure_run_running(run)
        return await self._ensure_node_run_running(node_run)

    async def reconcile(self, attempt: Attempt) -> NodeRun:
        """Reconcile one already-persisted terminal Attempt into logical activity.

        Success completes the logical NodeRun. Other terminal physical outcomes
        park it in ``waiting`` without deciding retry eligibility. That keeps
        retry policy outside Runtime and outside this universal reconciler while
        preventing a durable phantom ``running`` worker.
        """

        if attempt.status not in TERMINAL_ATTEMPT_STATUSES:
            raise RunIntegrityError("cannot reconcile a non-terminal Attempt")

        persisted = await self._store.get_attempt(attempt.attempt_id)
        if persisted is None:
            raise RunIntegrityError("cannot reconcile an Attempt that is not persisted")
        if persisted.status is not attempt.status:
            raise RunIntegrityError("Attempt reconciliation status differs from persisted state")

        node_run = await self._require_node_run(attempt.node_run_id)
        if attempt.status is AttemptStatus.COMPLETED:
            return await self._complete_node_run(node_run, attempt)

        parked = await self._park_node_run(node_run, attempt)
        await self._park_run_if_inactive(parked.run_id)
        return parked

    async def _ensure_run_running(self, run: Run) -> Run:
        if run.status in TERMINAL_RUN_STATUSES:
            raise RunIntegrityError("cannot execute Attempt under a terminal Run")
        if run.status is RunStatus.RUNNING:
            return run
        if run.status is RunStatus.CREATED:
            run = await self._store.transition_run(run.run_id, RunStatus.QUEUED)
        elif run.status is RunStatus.PAUSED:
            run = await self._store.transition_run(run.run_id, RunStatus.QUEUED)
        if run.status in {RunStatus.QUEUED, RunStatus.WAITING}:
            return await self._store.transition_run(run.run_id, RunStatus.RUNNING)
        raise RunIntegrityError(f"Run {run.run_id!r} cannot enter running from {run.status.value!r}")

    async def _ensure_node_run_running(self, node_run: NodeRun) -> NodeRun:
        if node_run.status in TERMINAL_RUN_STATUSES:
            raise RunIntegrityError("cannot execute Attempt under a terminal NodeRun")
        if node_run.status is RunStatus.RUNNING:
            return node_run
        if node_run.status is RunStatus.CREATED:
            node_run = await self._store.transition_node_run(
                node_run.node_run_id,
                RunStatus.QUEUED,
            )
        elif node_run.status is RunStatus.PAUSED:
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

    async def _complete_node_run(self, node_run: NodeRun, attempt: Attempt) -> NodeRun:
        if node_run.status is RunStatus.COMPLETED:
            return node_run
        if node_run.status is not RunStatus.RUNNING:
            raise RunIntegrityError("completed Attempt requires a running logical NodeRun")
        return await self._store.transition_node_run(
            node_run.node_run_id,
            RunStatus.COMPLETED,
            result=attempt.result,
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


__all__ = ["AttemptLifecycleReconciler"]
