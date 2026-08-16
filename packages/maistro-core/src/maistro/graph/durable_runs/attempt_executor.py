"""Canonical durable Graph execution through physical Attempts.

Traversal semantics stay in :mod:`maistro.graph.durable_runs.executor`. This
module owns the execution firewall: every frontier NodeRun is physically
executed by ``AttemptExecutionService -> ExecutionRuntime`` before the proven
Graph folding/routing helpers advance logical state.
"""

from __future__ import annotations

import asyncio
from typing import Any

from maistro.graph.definitions import Graph
from maistro.graph.execution_state import GraphExecutionState
from maistro.graph.nodes.base import NodeResult
from maistro.runs.execution import AttemptExecutionService
from maistro.runs.lifecycle import transition_run
from maistro.runs.model import RunStatus
from maistro.runtime import ExecutionRuntime, PythonExecutionRuntime

from . import executor as traversal
from .execution_store import DurableRunExecutionStore
from .protocol import DurableRunStore
from .types import DurableRunRecord

NodeResolver = traversal.NodeResolver


async def run_durable_graph(
    graph: Graph,
    *,
    store: DurableRunStore,
    node_resolver: NodeResolver,
    inputs: dict[str, Any] | None = None,
    actor_principal_id: str | None = None,
    run_id: str | None = None,
    runtime: ExecutionRuntime | None = None,
) -> DurableRunRecord:
    """Start a durable Graph whose physical node work crosses the Attempt firewall."""

    run = traversal._new_run(  # noqa: SLF001 - same-package traversal primitive
        graph,
        run_id=run_id,
        actor_principal_id=actor_principal_id,
    )
    state = GraphExecutionState(
        run_id=run.run_id,
        active_node_ids=(traversal._entry_node(graph),),  # noqa: SLF001
        blackboard_snapshot={
            "task_objective": graph.name,
            "metadata": {},
            "node_annotations": {},
        },
        metadata={"initial_inputs": dict(inputs or {}), "hitl_answers": {}},
    )
    record = DurableRunRecord(run=run, graph_state=state, version=1)
    await store.create(record)
    return await _walk(
        record,
        store=store,
        node_resolver=node_resolver,
        runtime=runtime or PythonExecutionRuntime(),
    )


async def resume_durable_graph(
    run_id: str,
    *,
    store: DurableRunStore,
    node_resolver: NodeResolver,
    runtime: ExecutionRuntime | None = None,
) -> DurableRunRecord:
    """Resume a durable Graph while preserving the same physical runtime boundary."""

    record = await store.get(run_id)
    if record is None:
        raise KeyError(f"no such run: {run_id!r}")
    if record.run.status is RunStatus.PAUSED:
        raise ValueError("HITL run must receive an answer before resume")
    if record.run.status not in {
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.WAITING,
    }:
        raise ValueError(f"cannot resume run in status {record.run.status!r}")

    run = record.run
    if run.status is not RunStatus.RUNNING:
        run = transition_run(run, RunStatus.RUNNING)
    record = await traversal._checkpoint(  # noqa: SLF001
        record,
        store=store,
        run=run,
        resume_at=None,
    )
    return await _walk(
        record,
        store=store,
        node_resolver=node_resolver,
        runtime=runtime or PythonExecutionRuntime(),
    )


async def _walk(
    record: DurableRunRecord,
    *,
    store: DurableRunStore,
    node_resolver: NodeResolver,
    runtime: ExecutionRuntime,
    max_steps: int = 256,
) -> DurableRunRecord:
    """Execute persisted frontiers through Attempts, then fold Graph semantics."""

    graph = record.run.graph.materialize()
    execution_store = DurableRunExecutionStore(store, run_id=record.run_id)
    execution_service = AttemptExecutionService(store=execution_store, runtime=runtime)
    steps = 0

    while record.graph_state.active_node_ids and steps < max_steps:
        steps += 1
        frontier = record.graph_state.active_node_ids
        unknown = next(
            (node_id for node_id in frontier if traversal._node_spec(graph, node_id) is None),  # noqa: SLF001
            None,
        )
        if unknown is not None:
            return await traversal._mark_failed(  # noqa: SLF001
                record,
                error_code="UnknownNode",
                error_message=f"node_id={unknown!r} not present in Graph",
                store=store,
            )

        record, node_runs = await traversal._ensure_frontier_node_runs(  # noqa: SLF001
            record,
            frontier,
            store=store,
        )
        items = await _execute_frontier(
            record,
            graph,
            frontier,
            node_runs,
            node_resolver=node_resolver,
            execution_service=execution_service,
        )

        # Attempt creation/running/terminalization advances the same durable
        # optimistic record. Reload before logical folding so Graph persistence
        # never overwrites physical execution facts from a stale checkpoint.
        latest = await store.get(record.run_id)
        if latest is None:
            raise KeyError(f"no such run: {record.run_id!r}")
        record = await traversal._fold_frontier(  # noqa: SLF001
            latest,
            graph,
            items,
            store=store,
        )
        if record.run.status is not RunStatus.RUNNING:
            return record

    return await traversal._finish_walk(  # noqa: SLF001
        record,
        store=store,
        max_steps=max_steps,
    )


async def _execute_frontier(
    record: DurableRunRecord,
    graph: Graph,
    frontier: tuple[str, ...],
    node_runs: tuple[Any, ...],
    *,
    node_resolver: NodeResolver,
    execution_service: AttemptExecutionService,
) -> tuple[Any, ...]:
    """Execute one complete frontier concurrently through canonical Attempts."""

    prepared: list[tuple[str, Any, Any, Any, Any, dict[str, Any]]] = []
    for node_id, node_run in zip(frontier, node_runs, strict=True):
        spec = traversal._node_spec(graph, node_id)  # noqa: SLF001
        assert spec is not None
        ctx = traversal._build_ctx(record, node_id)  # noqa: SLF001
        node = node_resolver(node_id, graph)
        inputs = traversal._resolve_inputs(graph, record, node_run, spec)  # noqa: SLF001
        prepared.append((node_id, spec, node_run, ctx, node, inputs))

    async def execute_one(
        node_id: str,
        spec: Any,
        node_run: Any,
        ctx: Any,
        node: Any,
        inputs: dict[str, Any],
    ) -> Any:
        raw_result: NodeResult | None = None

        async def executor(work_item: Any, execution_context: Any) -> NodeResult:
            nonlocal raw_result
            raw_result = await node.run(work_item, execution_context)
            return raw_result

        await execution_service.execute(
            node_run.node_run_id,
            inputs,
            ctx,
            executor=executor,
            executor_id=str(getattr(node, "kind", None) or spec.node_type or node_id),
            reconcile_logical=False,
        )
        if raw_result is None:
            raise RuntimeError(f"node {node_id!r} completed without a NodeResult")
        return traversal._FrontierItem(  # noqa: SLF001
            node_id,
            spec,
            node_run,
            ctx,
            raw_result,
        )

    return tuple(
        await asyncio.gather(
            *(
                execute_one(node_id, spec, node_run, ctx, node, inputs)
                for node_id, spec, node_run, ctx, node, inputs in prepared
            )
        )
    )


__all__ = ["NodeResolver", "resume_durable_graph", "run_durable_graph"]
