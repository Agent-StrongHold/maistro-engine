"""Durable execution for canonical Graph + Run + GraphExecutionState."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

from maistro.graph.conditions import MISSING, evaluate_predicate
from maistro.graph.definitions import Graph
from maistro.graph.definitions import Node as GraphNode
from maistro.graph.execution_state import (
    GraphEdgeDecision,
    GraphExecutionState,
    thaw_json_value,
)
from maistro.graph.nodes.base import BaseNode, NodeContext, NodeResult
from maistro.runs.lifecycle import transition_node_run, transition_run
from maistro.runs.model import (
    TERMINAL_RUN_STATUSES,
    GraphSnapshot,
    NodeRun,
    Run,
    RunStatus,
)

from .protocol import DurableRunStore
from .types import DurableRunRecord

NodeResolver = Callable[[str, Graph], BaseNode[Any, Any]]

_DEPTH_INCREMENTING_KINDS = frozenset({"agent.synth_dag", "agent.spawn_harness"})
_PREDICATE_NAMESPACE_ALIASES = {
    "plan": "plan",
    "planner": "plan",
    "code": "code",
    "coder": "code",
    "review": "review",
    "reviewer": "review",
}


def _replace_state(
    state: GraphExecutionState,
    **updates: object,
) -> GraphExecutionState:
    """Return a validated graph state with selected fields replaced."""
    values = state.model_dump(mode="json")
    values.update({key: thaw_json_value(value) for key, value in updates.items()})
    return GraphExecutionState.model_validate(values)


def _replace_record(
    record: DurableRunRecord,
    **updates: object,
) -> DurableRunRecord:
    """Return a validated durable record with selected fields replaced."""
    values = record.model_dump(mode="json")
    values.update({key: thaw_json_value(value) for key, value in updates.items()})
    return DurableRunRecord.model_validate(values)


async def _checkpoint(
    record: DurableRunRecord,
    *,
    store: DurableRunStore,
    **updates: object,
) -> DurableRunRecord:
    """Persist one optimistic-concurrency checkpoint with a bumped version."""
    return await store.update(
        _replace_record(
            record,
            version=record.version + 1,
            **updates,
        )
    )


def _new_run(
    graph: Graph,
    *,
    run_id: str | None,
    actor_principal_id: str | None,
) -> Run:
    """Create a canonical running Run for a durable Graph execution."""
    values: dict[str, object] = {
        "workspace_id": graph.workspace_id,
        "project_id": graph.project_id,
        "graph": GraphSnapshot.from_graph(graph.model_copy(deep=True)),
        "actor_principal_id": actor_principal_id,
        "provenance": {"executor": "durable_graph"},
    }
    if run_id is not None:
        values["run_id"] = run_id
    run = Run.model_validate(values)
    run = transition_run(run, RunStatus.QUEUED)
    return transition_run(run, RunStatus.RUNNING)


async def run_durable_graph(
    graph: Graph,
    *,
    store: DurableRunStore,
    node_resolver: NodeResolver,
    inputs: dict[str, Any] | None = None,
    actor_principal_id: str | None = None,
    run_id: str | None = None,
) -> DurableRunRecord:
    """Create and execute one durable canonical Graph run."""

    run = _new_run(
        graph,
        run_id=run_id,
        actor_principal_id=actor_principal_id,
    )
    state = GraphExecutionState(
        run_id=run.run_id,
        active_node_ids=(_entry_node(graph),),
        blackboard_snapshot={
            "task_objective": graph.name,
            "metadata": {},
            "node_annotations": {},
        },
        metadata={
            "initial_inputs": dict(inputs or {}),
            "hitl_answers": {},
        },
    )
    record = DurableRunRecord(run=run, graph_state=state, version=1)
    await store.create(record)
    return await _walk(record, store=store, node_resolver=node_resolver)


async def resume_durable_graph(
    run_id: str,
    *,
    store: DurableRunStore,
    node_resolver: NodeResolver,
) -> DurableRunRecord:
    """Resume a queued or waiting canonical durable Graph run."""

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

    node_runs = list(record.node_runs)
    active_id = record.active_node_id
    if active_id is not None:
        index = _latest_nonterminal_node_run_index(record, active_id)
        if index is not None:
            node_run = node_runs[index]
            if node_run.status in {RunStatus.QUEUED, RunStatus.WAITING}:
                node_runs[index] = transition_node_run(node_run, RunStatus.RUNNING)

    record = await _checkpoint(
        record,
        store=store,
        run=run,
        node_runs=tuple(node_runs),
        resume_at=None,
    )
    return await _walk(record, store=store, node_resolver=node_resolver)


async def _walk(
    record: DurableRunRecord,
    *,
    store: DurableRunStore,
    node_resolver: NodeResolver,
    max_steps: int = 256,
) -> DurableRunRecord:
    """Walk the persisted single-node frontier until pause or terminal state."""

    graph = record.run.graph.materialize()
    steps = 0

    while record.active_node_id is not None and steps < max_steps:
        steps += 1
        node_id = record.active_node_id
        spec = _node_spec(graph, node_id)
        if spec is None:
            return await _mark_failed(
                record,
                error_code="UnknownNode",
                error_message=f"node_id={node_id!r} not present in Graph",
                store=store,
            )

        record, node_run = await _ensure_running_node_run(
            record,
            node_id,
            store=store,
        )
        node = node_resolver(node_id, graph)
        node_inputs = _resolve_inputs(record, node_run, spec)
        ctx = _build_ctx(record, node_id)

        result = await node.run(node_inputs, ctx)
        record = _lift_blackboard(record, ctx)

        if result.status == "paused":
            return await _checkpoint_pause(record, node_run, result, store=store)
        if not result.success:
            return await _checkpoint_failure(record, node_run, result, store=store)

        record = await _checkpoint_success(record, node_run, result, store=store)

        metadata = record.graph_state.blackboard_snapshot.get("metadata", {})
        if isinstance(metadata, Mapping) and metadata.get("halt_requested"):
            reason = str(metadata.get("halt_reason") or "halt_requested")
            return await _mark_failed(
                record,
                error_code="HaltRequested",
                error_message=reason,
                store=store,
            )

        record = _maybe_increment_synth_depth(record, spec, result)
        next_id, decisions = _next_node(
            graph,
            node_id,
            node_run.node_run_id,
            result,
            record,
        )
        state = _replace_state(
            record.graph_state,
            active_node_ids=(next_id,) if next_id is not None else (),
            edge_decisions=(*record.graph_state.edge_decisions, *decisions),
        )
        record = await _checkpoint(record, store=store, graph_state=state)

    return await _finish_walk(record, store=store, max_steps=max_steps)


async def _finish_walk(
    record: DurableRunRecord,
    *,
    store: DurableRunStore,
    max_steps: int,
) -> DurableRunRecord:
    """Complete an exhausted walk or fail it when a live frontier remains."""
    if record.active_node_id is not None:
        return await _mark_failed(
            record,
            error_code="StepBudgetExhausted",
            error_message=(
                f"run exceeded max_steps={max_steps} with node "
                f"{record.active_node_id!r} still pending; the graph may cycle"
            ),
            store=store,
        )
    return await _mark_completed(record, store=store)


def _entry_node(graph: Graph) -> str:
    """Select the explicit Graph entry or derive the first root node."""
    explicit = graph.metadata.get("entry_node") or graph.metadata.get("entry")
    if explicit:
        node_id = str(explicit)
        if _node_spec(graph, node_id) is None:
            raise ValueError(f"Graph entry node {node_id!r} does not exist")
        return node_id
    if not graph.nodes:
        raise ValueError("Graph has no nodes")
    incoming = {edge.to_node for edge in graph.edges}
    roots = [node.node_id for node in graph.nodes if node.node_id not in incoming]
    return roots[0] if roots else graph.nodes[0].node_id


def _node_spec(graph: Graph, node_id: str) -> GraphNode | None:
    """Return the canonical node definition for a node id when present."""
    return next((node for node in graph.nodes if node.node_id == node_id), None)


def _latest_nonterminal_node_run_index(
    record: DurableRunRecord,
    node_id: str,
) -> int | None:
    """Find the newest unfinished NodeRun for a canonical Graph node."""
    for index in range(len(record.node_runs) - 1, -1, -1):
        node_run = record.node_runs[index]
        if node_run.node_id == node_id and node_run.status not in TERMINAL_RUN_STATUSES:
            return index
    return None


async def _ensure_running_node_run(
    record: DurableRunRecord,
    node_id: str,
    *,
    store: DurableRunStore,
) -> tuple[DurableRunRecord, NodeRun]:
    """Resume or create the canonical running NodeRun for the active node."""
    node_runs = list(record.node_runs)
    existing_index = _latest_nonterminal_node_run_index(record, node_id)
    if existing_index is not None:
        node_run = node_runs[existing_index]
        if node_run.status in {RunStatus.QUEUED, RunStatus.WAITING}:
            node_run = transition_node_run(node_run, RunStatus.RUNNING)
        elif node_run.status is RunStatus.PAUSED:
            raise ValueError("paused NodeRun must receive HITL input before execution")
        node_runs[existing_index] = node_run
        if tuple(node_runs) != record.node_runs:
            record = await _checkpoint(record, store=store, node_runs=tuple(node_runs))
        return record, node_run

    node_run = NodeRun(
        run_id=record.run_id,
        node_id=node_id,
        ordinal=len(node_runs) + 1,
    )
    node_run = transition_node_run(node_run, RunStatus.QUEUED)
    node_run = transition_node_run(node_run, RunStatus.RUNNING)
    node_runs.append(node_run)

    visit_counts = dict(record.graph_state.visit_counts)
    visit_counts[node_id] = visit_counts.get(node_id, 0) + 1
    state = _replace_state(record.graph_state, visit_counts=visit_counts)
    record = await _checkpoint(
        record,
        store=store,
        graph_state=state,
        node_runs=tuple(node_runs),
    )
    return record, node_run


def _value_at_path(value: object, path: str) -> object:
    """Resolve a dotted predicate path through Pydantic or mapping values."""
    for part in path.split("."):
        if isinstance(value, BaseModel):
            value = getattr(value, part, MISSING)
        elif isinstance(value, dict):
            value = value.get(part, MISSING)
        else:
            return MISSING
        if value is MISSING:
            return value
    return value


def _predicate_namespace(graph: Graph, node_id: str) -> str | None:
    """Map planner, coder, and reviewer node identities to predicate slots."""
    spec = _node_spec(graph, node_id)
    if spec is None:
        return None
    for value in (
        spec.metadata.get("role"),
        spec.metadata.get("agent_role"),
        spec.node_id,
        spec.node_type,
    ):
        token = str(value or "").lower().rsplit(".", 1)[-1]
        namespace = _PREDICATE_NAMESPACE_ALIASES.get(token)
        if namespace is not None:
            return namespace
    return None


def _completed_predicate_state(
    graph: Graph,
    record: DurableRunRecord | None,
) -> dict[str, object]:
    """Rebuild predicate namespaces from completed canonical NodeRuns."""
    state: dict[str, object] = {}
    if record is None:
        return state
    for node_run in record.node_runs:
        if node_run.status is not RunStatus.COMPLETED or node_run.result is None:
            continue
        namespace = _predicate_namespace(graph, node_run.node_id)
        if namespace is not None:
            state[namespace] = node_run.result
    return state


def _merge_current_predicate_state(
    state: dict[str, object],
    graph: Graph,
    current_id: str,
    result: NodeResult,
) -> dict[str, object]:
    """Overlay the current node result onto reconstructed predicate state."""
    output = result.output
    dumped = output.model_dump() if isinstance(output, BaseModel) else output
    if isinstance(dumped, dict):
        for slot in ("plan", "code", "review"):
            value = dumped.get(slot, MISSING)
            if value is not MISSING:
                state[slot] = value

    namespace = _predicate_namespace(graph, current_id)
    if namespace is not None and output is not None:
        state[namespace] = output
    return state


def _predicate_state(
    graph: Graph,
    current_id: str,
    result: NodeResult,
    record: DurableRunRecord | None,
) -> dict[str, object]:
    """Build the canonical routing predicate state for the current edge."""
    state = _completed_predicate_state(graph, record)
    return _merge_current_predicate_state(state, graph, current_id, result)


def _result_value(
    result: NodeResult,
    path: str,
    *,
    predicate_state: dict[str, object] | None = None,
) -> object:
    """Resolve a predicate path against accumulated state or current output."""
    parts = path.split(".", 1)
    if len(parts) == 2 and predicate_state is not None:
        namespace, remainder = parts
        if namespace in predicate_state:
            return _value_at_path(predicate_state[namespace], remainder)
    return _value_at_path(result.output, path)


def _result_matches_condition(
    condition: str,
    result: NodeResult,
    *,
    predicate_state: dict[str, object] | None = None,
) -> bool:
    """Evaluate one canonical edge predicate against durable execution state."""
    return evaluate_predicate(
        condition,
        lambda path: _result_value(
            result,
            path,
            predicate_state=predicate_state,
        ),
    )


def _next_node(
    graph: Graph,
    current_id: str,
    source_node_run_id: str,
    result: NodeResult,
    record: DurableRunRecord | None = None,
) -> tuple[str | None, tuple[GraphEdgeDecision, ...]]:
    """Select one outgoing edge while recording immutable routing facts."""

    predicate_state = _predicate_state(graph, current_id, result, record)
    decisions: list[GraphEdgeDecision] = []
    for edge in graph.edges:
        if edge.from_node != current_id:
            continue
        selected = edge.condition is None or _result_matches_condition(
            edge.condition,
            result,
            predicate_state=predicate_state,
        )
        decisions.append(
            GraphEdgeDecision(
                edge_id=edge.edge_id,
                source_node_id=current_id,
                source_node_run_id=source_node_run_id,
                target_node_id=edge.to_node,
                selected=selected,
                cycle=record.graph_state.cycle if record is not None else 0,
                condition=edge.condition,
            )
        )
        if selected:
            return edge.to_node, tuple(decisions)
    return None, tuple(decisions)


def _initial_inputs(record: DurableRunRecord) -> dict[str, Any]:
    """Return the immutable initial input mapping captured in graph metadata."""
    value = record.graph_state.metadata.get("initial_inputs", {})
    return dict(value) if isinstance(value, Mapping) else {}


def _resolve_inputs(
    record: DurableRunRecord,
    current: NodeRun,
    spec: GraphNode,
) -> dict[str, Any]:
    """Combine node defaults with the latest upstream result or run inputs."""
    static_inputs = {**spec.parameters, **spec.inputs}
    upstream_output: dict[str, Any] | None = None
    for node_run in reversed(record.node_runs):
        if node_run.node_run_id == current.node_run_id:
            continue
        if node_run.status is RunStatus.COMPLETED and isinstance(node_run.result, dict):
            upstream_output = dict(node_run.result)
            break
    if upstream_output is not None:
        return {**static_inputs, **upstream_output}
    return {**static_inputs, **_initial_inputs(record)}


def _lift_blackboard(record: DurableRunRecord, ctx: NodeContext) -> DurableRunRecord:
    """Lift in-place blackboard mutations into persisted graph execution state."""
    blackboard = ctx.blackboard
    if blackboard is None or not hasattr(blackboard, "metadata"):
        return record
    snapshot = dict(record.graph_state.blackboard_snapshot)
    snapshot["metadata"] = dict(getattr(blackboard, "metadata", {}) or {})
    annotations = getattr(blackboard, "node_annotations", None)
    if annotations is not None:
        snapshot["node_annotations"] = dict(annotations or {})
    state = _replace_state(record.graph_state, blackboard_snapshot=snapshot)
    return _replace_record(record, graph_state=state)


def _actually_spawned(kind: str, result: NodeResult) -> bool:
    """Return whether a spawn-capable node actually dispatched child work."""
    if kind == "agent.synth_dag":
        output = result.output
        return bool(getattr(output, "success", True)) or bool(getattr(output, "dispatched", False))
    return True


def _maybe_increment_synth_depth(
    record: DurableRunRecord,
    spec: GraphNode,
    result: NodeResult,
) -> DurableRunRecord:
    """Advance synthesis depth after a node actually spawns a child graph."""
    if spec.node_type not in _DEPTH_INCREMENTING_KINDS or not _actually_spawned(
        spec.node_type, result
    ):
        return record
    snapshot = dict(record.graph_state.blackboard_snapshot)
    metadata = dict(snapshot.get("metadata") or {})
    metadata["synth_depth"] = int(metadata.get("synth_depth", 0)) + 1
    snapshot["metadata"] = metadata
    state = _replace_state(record.graph_state, blackboard_snapshot=snapshot)
    return _replace_record(record, graph_state=state)


def _build_ctx(record: DurableRunRecord, node_id: str) -> NodeContext:
    """Reconstruct NodeContext from canonical run and persisted graph state."""
    from maistro.graph.types import GraphBlackboard

    snapshot = record.graph_state.blackboard_snapshot
    try:
        blackboard = GraphBlackboard(
            task_objective=str(snapshot.get("task_objective") or ""),
            workspace=str(snapshot.get("workspace") or ""),
            metadata=dict(snapshot.get("metadata") or {}),
            node_annotations=dict(snapshot.get("node_annotations") or {}),
        )
    except Exception:
        blackboard = None

    try:
        synth_depth = dict(snapshot.get("metadata") or {}).get("synth_depth", 0)
    except (TypeError, ValueError):
        synth_depth = 0

    return NodeContext(
        run_id=record.run_id,
        dag_id=record.run.graph.graph_id,
        node_id=node_id,
        user_id=record.run.actor_principal_id,
        project_id=record.run.project_id,
        blackboard=blackboard,
        metadata={
            "hitl_answers": dict(record.hitl_answers),
            "synth_depth": synth_depth,
        },
    )


def _replace_node_run(record: DurableRunRecord, updated: NodeRun) -> DurableRunRecord:
    """Replace one canonical NodeRun in a durable checkpoint by identity."""
    node_runs = list(record.node_runs)
    for index, node_run in enumerate(node_runs):
        if node_run.node_run_id == updated.node_run_id:
            node_runs[index] = updated
            return _replace_record(record, node_runs=tuple(node_runs))
    raise KeyError(updated.node_run_id)


def _result_output(result: NodeResult) -> object | None:
    """Convert a node output to a JSON-compatible canonical Run result."""
    output = result.output
    if isinstance(output, BaseModel):
        return output.model_dump(mode="json")
    return output


def _clear_pause_metadata(state: GraphExecutionState) -> GraphExecutionState:
    """Remove persisted pause metadata after execution resumes or completes."""
    metadata = dict(state.metadata)
    metadata.pop("pause", None)
    return _replace_state(state, metadata=metadata)


async def _checkpoint_success(
    record: DurableRunRecord,
    node_run: NodeRun,
    result: NodeResult,
    *,
    store: DurableRunStore,
) -> DurableRunRecord:
    """Persist successful NodeRun terminalization and clear pause state."""
    completed = transition_node_run(
        node_run,
        RunStatus.COMPLETED,
        result=_result_output(result),
    )
    record = _replace_node_run(record, completed)
    state = _clear_pause_metadata(record.graph_state)
    return await _checkpoint(
        record,
        store=store,
        graph_state=state,
        resume_at=None,
    )


async def _checkpoint_pause(
    record: DurableRunRecord,
    node_run: NodeRun,
    result: NodeResult,
    *,
    store: DurableRunStore,
) -> DurableRunRecord:
    """Persist a wait or HITL pause on both Run and NodeRun lifecycle state."""
    paused_reason = str((result.metadata or {}).get("paused_reason") or "")
    human = paused_reason in {
        "awaiting_human_answer",
        "awaiting_human_approval",
    }
    target = RunStatus.PAUSED if human else RunStatus.WAITING
    paused_node = transition_node_run(node_run, target)
    run = transition_run(record.run, target)

    metadata = dict(record.graph_state.metadata)
    metadata["pause"] = {
        "node_id": node_run.node_id,
        "kind": "hitl" if human else "wait",
        "metadata": dict(result.metadata or {}),
    }
    state = _replace_state(record.graph_state, metadata=metadata)
    record = _replace_node_run(record, paused_node)
    return await _checkpoint(
        record,
        store=store,
        run=run,
        graph_state=state,
        resume_at=result.resume_at,
    )


async def _checkpoint_failure(
    record: DurableRunRecord,
    node_run: NodeRun,
    result: NodeResult,
    *,
    store: DurableRunStore,
) -> DurableRunRecord:
    """Persist matching NodeRun and Run failure terminalization."""
    message = result.error_message or f"node {node_run.node_id} failed"
    error = f"{result.error_code or 'NodeFailure'}: {message}"[:512]
    failed_node = transition_node_run(node_run, RunStatus.FAILED, error=error)
    record = _replace_node_run(record, failed_node)
    run = transition_run(record.run, RunStatus.FAILED, error=error)
    return await _checkpoint(record, store=store, run=run)


async def _mark_completed(
    record: DurableRunRecord,
    *,
    store: DurableRunStore,
) -> DurableRunRecord:
    """Terminalize the canonical Run with its most recent completed result."""
    result = next(
        (
            node_run.result
            for node_run in reversed(record.node_runs)
            if node_run.status is RunStatus.COMPLETED
        ),
        None,
    )
    run = transition_run(record.run, RunStatus.COMPLETED, result=result)
    state = _replace_state(record.graph_state, active_node_ids=())
    return await _checkpoint(
        record,
        store=store,
        run=run,
        graph_state=state,
        resume_at=None,
    )


def _running_run(run: Run) -> Run:
    """Normalize resumable lifecycle states to RUNNING before failure."""
    if run.status is RunStatus.RUNNING:
        return run
    if run.status is RunStatus.PAUSED:
        run = transition_run(run, RunStatus.QUEUED)
    if run.status is RunStatus.CREATED:
        run = transition_run(run, RunStatus.QUEUED)
    if run.status in {RunStatus.QUEUED, RunStatus.WAITING}:
        return transition_run(run, RunStatus.RUNNING)
    return run


async def _mark_failed(
    record: DurableRunRecord,
    *,
    error_code: str,
    error_message: str,
    store: DurableRunStore,
) -> DurableRunRecord:
    """Terminalize the canonical Run as failed with a bounded error string."""
    run = _running_run(record.run)
    error = f"{error_code}: {error_message}"[:512]
    if run.status is not RunStatus.RUNNING:
        raise ValueError(f"cannot fail run in status {run.status!r}")
    run = transition_run(run, RunStatus.FAILED, error=error)
    return await _checkpoint(record, store=store, run=run)


__all__ = ["NodeResolver", "resume_durable_graph", "run_durable_graph"]
