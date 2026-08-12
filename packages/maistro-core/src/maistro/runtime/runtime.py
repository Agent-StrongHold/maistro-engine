"""ExecutionRuntime: the canonical lifecycle boundary for MAIstro work.

The runtime delegates mechanics to specialized executors. Its job is to keep
workspace ownership, run identity, lineage, and correlation intact while work
moves through those executors.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from maistro.graph.durable_runs.executor import (
    NodeResolver,
    resume_durable_dag,
    run_durable_dag,
)
from maistro.graph.durable_runs.protocol import DurableRunStore
from maistro.graph.durable_runs.types import DurableRunRecord, RunStatus

from .types import ExecutionContext, RunContext, RunKind, RunState, WorkspaceRef


@dataclass(frozen=True, slots=True)
class GraphExecutionResult:
    """Canonical run context plus the graph adapter's durable state."""

    context: ExecutionContext
    durable: DurableRunRecord


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _state_from_durable(status: RunStatus) -> RunState:
    if status == RunStatus.PENDING:
        return RunState.PENDING
    if status == RunStatus.RUNNING:
        return RunState.RUNNING
    if status in (RunStatus.PAUSED_WAIT, RunStatus.PAUSED_HITL):
        return RunState.PAUSED
    if status == RunStatus.COMPLETED:
        return RunState.COMPLETED
    if status == RunStatus.FAILED:
        return RunState.FAILED
    if status == RunStatus.CANCELLED:
        return RunState.CANCELLED
    raise ValueError(f"unsupported durable run status: {status!r}")


class ExecutionRuntime:
    """Canonical runtime boundary for execution and capability correlation."""

    def __init__(self, *, durable_run_store: DurableRunStore) -> None:
        self._durable_run_store = durable_run_store

    def root_context(
        self,
        workspace: WorkspaceRef,
        *,
        kind: RunKind,
        run_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        rid = run_id or _new_run_id()
        run = RunContext(
            run_id=rid,
            workspace_id=workspace.workspace_id,
            kind=kind,
            state=RunState.PENDING,
            root_run_id=rid,
            parent_run_id=None,
            actor_id=workspace.actor_id,
            correlation_id=correlation_id or rid,
            metadata=metadata or {},
        )
        return ExecutionContext(run=run)

    def child_context(
        self,
        parent: ExecutionContext,
        *,
        kind: RunKind,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        rid = run_id or _new_run_id()
        run = RunContext(
            run_id=rid,
            workspace_id=parent.workspace_id,
            kind=kind,
            state=RunState.PENDING,
            root_run_id=parent.root_run_id,
            parent_run_id=parent.run_id,
            actor_id=parent.actor_id,
            correlation_id=parent.correlation_id,
            metadata=metadata or {},
        )
        return ExecutionContext(run=run, services=parent.services)

    async def run_graph(
        self,
        dag: dict[str, Any],
        *,
        workspace: WorkspaceRef,
        node_resolver: NodeResolver,
        inputs: dict[str, Any] | None = None,
        run_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphExecutionResult:
        context = self.root_context(
            workspace,
            kind=RunKind.GRAPH,
            run_id=run_id,
            correlation_id=correlation_id,
            metadata=metadata,
        )
        durable = await run_durable_dag(
            dag,
            store=self._durable_run_store,
            node_resolver=node_resolver,
            inputs=inputs,
            user_id=workspace.actor_id,
            project_id=workspace.workspace_id,
            run_id=context.run_id,
        )
        return GraphExecutionResult(
            context=self._context_from_durable(durable, previous=context),
            durable=durable,
        )

    async def resume_graph(
        self,
        run_id: str,
        *,
        node_resolver: NodeResolver,
    ) -> GraphExecutionResult:
        before = await self._durable_run_store.get(run_id)
        if before is None:
            raise KeyError(f"no such run: {run_id!r}")
        if not before.project_id:
            raise ValueError(
                "cannot resume graph through ExecutionRuntime without workspace ownership"
            )
        previous = ExecutionContext(
            run=RunContext(
                run_id=before.run_id,
                workspace_id=before.project_id,
                kind=RunKind.GRAPH,
                state=_state_from_durable(before.status),
                root_run_id=before.run_id,
                parent_run_id=None,
                actor_id=before.user_id,
                correlation_id=before.run_id,
                metadata={},
            )
        )
        durable = await resume_durable_dag(
            run_id,
            store=self._durable_run_store,
            node_resolver=node_resolver,
        )
        return GraphExecutionResult(
            context=self._context_from_durable(durable, previous=previous),
            durable=durable,
        )

    @staticmethod
    def _context_from_durable(
        durable: DurableRunRecord,
        *,
        previous: ExecutionContext,
    ) -> ExecutionContext:
        if not durable.project_id:
            raise ValueError("durable graph run lost workspace/project identity")
        run = previous.run.model_copy(
            update={
                "run_id": durable.run_id,
                "workspace_id": durable.project_id,
                "state": _state_from_durable(durable.status),
            }
        )
        return previous.model_copy(update={"run": run})


__all__ = [
    "ExecutionRuntime",
    "GraphExecutionResult",
]
