"""ExecutionRuntime: canonical lifecycle boundary for MAIstro work.

The runtime delegates mechanics to specialized executors while keeping
workspace ownership, run identity, lineage, and correlation intact.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from maistro.graph.durable_runs.executor import NodeResolver, resume_durable_dag, run_durable_dag
from maistro.graph.durable_runs.protocol import DurableRunStore
from maistro.graph.durable_runs.types import DurableRunRecord, RunStatus

from .context import bind_execution_context
from .types import ExecutionContext, RunContext, RunKind, RunState, WorkspaceRef


@dataclass(frozen=True, slots=True)
class GraphExecutionResult:
    """Canonical run context plus the graph adapter's durable state."""

    context: ExecutionContext
    durable: DurableRunRecord


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _state_from_durable(status: RunStatus) -> RunState:
    mapping = {
        RunStatus.PENDING: RunState.PENDING,
        RunStatus.RUNNING: RunState.RUNNING,
        RunStatus.PAUSED_WAIT: RunState.PAUSED,
        RunStatus.PAUSED_HITL: RunState.PAUSED,
        RunStatus.COMPLETED: RunState.COMPLETED,
        RunStatus.FAILED: RunState.FAILED,
        RunStatus.CANCELLED: RunState.CANCELLED,
    }
    return mapping[status]


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
        return ExecutionContext(
            run=RunContext(
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
        )

    def child_context(
        self,
        parent: ExecutionContext,
        *,
        kind: RunKind,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        rid = run_id or _new_run_id()
        return ExecutionContext(
            run=RunContext(
                run_id=rid,
                workspace_id=parent.workspace_id,
                kind=kind,
                state=RunState.PENDING,
                root_run_id=parent.root_run_id,
                parent_run_id=parent.run_id,
                actor_id=parent.actor_id,
                correlation_id=parent.correlation_id,
                metadata=metadata or {},
            ),
            services=parent.services,
        )

    async def run_graph(
        self,
        dag: dict[str, Any],
        *,
        workspace: WorkspaceRef | None = None,
        parent: ExecutionContext | None = None,
        node_resolver: NodeResolver,
        inputs: dict[str, Any] | None = None,
        run_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphExecutionResult:
        """Execute a graph as a root run or a lineage-preserving child run."""
        if (workspace is None) == (parent is None):
            raise ValueError("provide exactly one of workspace or parent")
        if parent is not None:
            context = self.child_context(
                parent,
                kind=RunKind.GRAPH,
                run_id=run_id,
                metadata=metadata,
            )
        else:
            assert workspace is not None
            context = self.root_context(
                workspace,
                kind=RunKind.GRAPH,
                run_id=run_id,
                correlation_id=correlation_id,
                metadata=metadata,
            )

        with bind_execution_context(context):
            durable = await run_durable_dag(
                dag,
                store=self._durable_run_store,
                node_resolver=node_resolver,
                inputs=inputs,
                user_id=context.actor_id,
                project_id=context.workspace_id,
                run_id=context.run_id,
            )
        durable = await self._persist_runtime_identity(durable, context)
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
        """Resume a durable graph without losing canonical identity."""
        before = await self._durable_run_store.get(run_id)
        if before is None:
            raise KeyError(f"no such run: {run_id!r}")
        previous = self._context_from_persisted(before)
        with bind_execution_context(previous):
            durable = await resume_durable_dag(
                run_id,
                store=self._durable_run_store,
                node_resolver=node_resolver,
            )
        durable = await self._persist_runtime_identity(durable, previous)
        return GraphExecutionResult(
            context=self._context_from_durable(durable, previous=previous),
            durable=durable,
        )

    async def _persist_runtime_identity(
        self,
        durable: DurableRunRecord,
        context: ExecutionContext,
    ) -> DurableRunRecord:
        """Write canonical identity into the adapter checkpoint."""
        updated = durable.model_copy(
            update={
                "run_kind": context.run.kind.value,
                "root_run_id": context.root_run_id,
                "parent_run_id": context.parent_run_id,
                "correlation_id": context.correlation_id,
                "runtime_metadata": dict(context.run.metadata),
                "version": durable.version + 1,
            }
        )
        return await self._durable_run_store.update(updated)

    @staticmethod
    def _context_from_persisted(durable: DurableRunRecord) -> ExecutionContext:
        if not durable.project_id:
            raise ValueError(
                "cannot resume graph through ExecutionRuntime without workspace ownership"
            )
        root_run_id = durable.root_run_id or durable.run_id
        correlation_id = durable.correlation_id or root_run_id
        try:
            kind = RunKind(durable.run_kind)
        except ValueError:
            kind = RunKind.GRAPH
        return ExecutionContext(
            run=RunContext(
                run_id=durable.run_id,
                workspace_id=durable.project_id,
                kind=kind,
                state=_state_from_durable(durable.status),
                root_run_id=root_run_id,
                parent_run_id=durable.parent_run_id,
                actor_id=durable.user_id,
                correlation_id=correlation_id,
                metadata=dict(durable.runtime_metadata),
            )
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


__all__ = ["ExecutionRuntime", "GraphExecutionResult"]
