"""Durable DAG executor.

Two public entrypoints:

  :func:`run_durable_dag(dag, inputs, store, *, ...)` — start a NEW run from
  the DAG entry node. Persists a checkpoint after every node. If a node
  pauses (wait or HITL), the run is checkpointed as paused and the function
  returns; the caller (scheduler / API) is responsible for poking
  :func:`resume_durable_dag` later.

  :func:`resume_durable_dag(run_id, store, *, ...)` — pick up a paused run
  and walk forward until the next pause or completion.

Both functions accept a `node_resolver` callable: `(node_id, dag_snapshot)
→ Node` so test code can inject mocks. In production the resolver pulls
the configured `kind` from the catalog (`maistro.graph.nodes.get_node`)
and instantiates it.

The DAG snapshot is a plain dict with the same shape as Hive's `DAGFile`
JSON: `{nodes:[{id, kind, config}], edges:[{from_node, to_node, condition?}],
entry_node}`. We don't rely on a particular `GraphConfig` Pydantic shape so
the executor stays decoupled from the legacy engineering substrate.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from ..conditions import MISSING, evaluate_predicate
from ..nodes.base import BaseNode, NodeContext, NodeResult
from .protocol import DurableRunStore
from .types import DurableNodeRecord, DurableRunRecord, NodePhase, RunStatus

NodeResolver = Callable[[str, dict[str, Any]], BaseNode[Any, Any]]
"""Given (node_id, dag_snapshot) return an instantiated node ready to run."""

# Node kinds that can descend into a spawned sub-graph -- `synth_depth`
# increments for whatever runs next after one of these completes, not for
# the spawning node's own invocation. Kept in sync with `agent_synth_dag.py`
# and `agent_spawn_harness.py`'s registered `kind` ClassVars.
_DEPTH_INCREMENTING_KINDS = frozenset({"agent.synth_dag", "agent.spawn_harness"})
_PREDICATE_NAMESPACE_ALIASES = {
    "plan": "plan",
    "planner": "plan",
    "code": "code",
    "coder": "code",
    "review": "review",
    "reviewer": "review",
}


# --- Entrypoint: start a new run ------------------------------------------


async def run_durable_dag(
    dag: dict[str, Any],
    *,
    store: DurableRunStore,
    node_resolver: NodeResolver,
    inputs: dict[str, Any] | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
) -> DurableRunRecord:
    """Create a fresh durable run and walk it to its first pause / completion.

    Returns the post-walk :class:`DurableRunRecord`. Status will be one of
    completed / failed / paused_wait / paused_hitl.
    """
    rid = run_id or uuid.uuid4().hex[:12]
    now = datetime.now(UTC)

    record = DurableRunRecord(
        run_id=rid,
        dag_id=str(dag.get("id") or dag.get("name") or "anonymous"),
        dag_snapshot=dag,
        inputs=inputs or {},
        status=RunStatus.RUNNING,
        current_node_id=_entry_node(dag),
        node_records=[],
        blackboard_snapshot={
            "task_objective": str(dag.get("name") or ""),
            "metadata": {},
            "node_annotations": {},
        },
        hitl_answers={},
        user_id=user_id,
        project_id=project_id,
        started_at=now,
        last_step_at=now,
        version=1,
    )
    await store.create(record)
    return await _walk(record, store=store, node_resolver=node_resolver)


# --- Entrypoint: resume a paused run --------------------------------------


async def resume_durable_dag(
    run_id: str,
    *,
    store: DurableRunStore,
    node_resolver: NodeResolver,
) -> DurableRunRecord:
    """Resume a paused run. Caller (scheduler or HITL-answer endpoint)
    is responsible for first marking the run RUNNING — :meth:`submit_hitl_answer`
    does this; the wait-scheduler should call store.update() to flip the
    status before invoking resume.
    """
    record = await store.get(run_id)
    if record is None:
        raise KeyError(f"no such run: {run_id!r}")
    if record.status not in (RunStatus.RUNNING, RunStatus.PAUSED_WAIT, RunStatus.PAUSED_HITL):
        raise ValueError(f"cannot resume run in status {record.status!r}")

    # Flip back to RUNNING for the walk.
    if record.status != RunStatus.RUNNING:
        record = record.model_copy(
            update={
                "status": RunStatus.RUNNING,
                "version": record.version + 1,
                "last_step_at": datetime.now(UTC),
            }
        )
        record = await store.update(record)

    return await _walk(record, store=store, node_resolver=node_resolver)


# --- Internal: BFS-ish walk -----------------------------------------------


async def _walk(
    record: DurableRunRecord,
    *,
    store: DurableRunStore,
    node_resolver: NodeResolver,
    max_steps: int = 256,
) -> DurableRunRecord:
    """Drive the run forward until pause / failure / completion."""
    dag = record.dag_snapshot
    steps = 0

    while record.current_node_id and steps < max_steps:
        steps += 1
        node_id = record.current_node_id
        spec = _node_spec(dag, node_id)
        if spec is None:
            return await _mark_failed(
                record,
                error_code="UnknownNode",
                error_message=f"node_id={node_id!r} not present in DAG",
                store=store,
            )

        node = node_resolver(node_id, dag)
        node_record = _existing_or_new_record(record, node_id, kind=spec.get("kind", ""))
        node_record = node_record.model_copy(
            update={
                "phase": NodePhase.RUNNING,
                "started_at": node_record.started_at or datetime.now(UTC),
                "attempts": node_record.attempts + 1,
            }
        )
        record = _patch_node_record(record, node_record)

        # Build the per-step inputs: for the FIRST node we use record.inputs;
        # for downstream nodes we pass the prior node's output. (More complex
        # input mapping is a Phase 6 enhancement — the optimizer will pick
        # which upstream output flows where.)
        node_inputs = _resolve_inputs(record, node_id, spec)
        ctx = _build_ctx(record, node_id)

        result = await node.run(node_inputs, ctx)

        # Lift in-place blackboard mutations back into the durable snapshot
        # BEFORE checkpointing. This is how dashboard.append_section's
        # `metadata['dashboard:<id>']` accumulator + compliance.block's
        # `metadata['halt_requested']` survive across steps.
        record = _lift_blackboard(record, ctx)

        if result.status == "paused":
            return await _checkpoint_pause(record, node_id, node_record, result, store=store)

        if not result.success:
            return await _checkpoint_failure(record, node_id, node_record, result, store=store)

        # Success → store the result, advance to next node.
        record = await _checkpoint_success(record, node_id, node_record, result, store=store)

        # Honor halt requests from negative-signal nodes (compliance.block,
        # risk.veto). Check AFTER the lift so halt_requested is visible.
        meta = record.blackboard_snapshot.get("metadata", {}) or {}
        if meta.get("halt_requested"):
            reason = meta.get("halt_reason") or "halt_requested"
            return await _mark_failed(
                record,
                error_code="HaltRequested",
                error_message=reason,
                store=store,
            )

        record = _maybe_increment_synth_depth(record, spec, result)

        next_id = _next_node(dag, node_id, result, record)
        record = record.model_copy(
            update={
                "current_node_id": next_id,
                "version": record.version + 1,
                "last_step_at": datetime.now(UTC),
            }
        )
        record = await store.update(record)

    return await _finish_walk(record, store=store, max_steps=max_steps)


async def _finish_walk(
    record: DurableRunRecord,
    *,
    store: DurableRunStore,
    max_steps: int,
) -> DurableRunRecord:
    """Record the terminal status for a walk that left its loop.

    There are two ways out of that loop and they are not the same outcome.
    Falling out because `current_node_id` is empty means the graph ran to its
    end. Falling out because `steps` hit `max_steps` means it did NOT — the run
    still has a live node and a partial blackboard. Both used to fall through
    to `_mark_completed`, so a cycling or over-long DAG was persisted as a
    success with partial results. That is worse than a failure record:
    downstream consumers trust COMPLETED.

    Split out of `_walk` rather than inlined so the added branch does not push
    that function over the radon complexity ratchet — the gate flagged exactly
    that, which is the gate doing its job.
    """
    if record.current_node_id:
        return await _mark_failed(
            record,
            error_code="StepBudgetExhausted",
            error_message=(
                f"run exceeded max_steps={max_steps} with node "
                f"{record.current_node_id!r} still pending; the graph may cycle"
            ),
            store=store,
        )

    return await _mark_completed(record, store=store)


# --- Helpers --------------------------------------------------------------


def _entry_node(dag: dict[str, Any]) -> str:
    """Pick the entry node from a DAG snapshot."""
    entry = dag.get("entry_node") or dag.get("entry")
    if entry:
        return str(entry)
    nodes = dag.get("nodes") or []
    if not nodes:
        raise ValueError("DAG has no nodes")
    # First node by document order.
    first = nodes[0]
    return str(first.get("id") or first)


def _node_spec(dag: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for n in dag.get("nodes", []):
        if str(n.get("id")) == node_id:
            return dict(n)
    return None


def _value_at_path(value: object, path: str) -> object:
    """Resolve a dotted path through either Pydantic or mapping payloads."""
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


def _predicate_namespace(dag: dict[str, Any], node_id: str) -> str | None:
    """Map legacy planner/coder/reviewer node identity to predicate namespaces."""
    spec = _node_spec(dag, node_id) or {}
    for value in (spec.get("role"), spec.get("agent_role"), spec.get("id"), spec.get("kind")):
        token = str(value or "").lower().rsplit(".", 1)[-1]
        namespace = _PREDICATE_NAMESPACE_ALIASES.get(token)
        if namespace is not None:
            return namespace
    return None


def _completed_predicate_state(
    dag: dict[str, Any], record: DurableRunRecord | None
) -> dict[str, object]:
    """Rebuild canonical predicate namespaces from completed checkpoints."""
    state: dict[str, object] = {}
    if record is None:
        return state
    for node_record in record.node_records:
        if node_record.phase != NodePhase.COMPLETED:
            continue
        if node_record.output is None:
            continue
        namespace = _predicate_namespace(dag, node_record.node_id)
        if namespace is not None:
            state[namespace] = node_record.output
    return state


def _merge_current_predicate_state(
    state: dict[str, object],
    dag: dict[str, Any],
    current_id: str,
    result: NodeResult,
) -> dict[str, object]:
    """Overlay the current result onto the reconstructed predicate state."""
    output = result.output
    dumped = output.model_dump() if isinstance(output, BaseModel) else output
    if isinstance(dumped, dict):
        for namespace in ("plan", "code", "review"):
            value = dumped.get(namespace, MISSING)
            if value is not MISSING:
                state[namespace] = value

    namespace = _predicate_namespace(dag, current_id)
    if namespace is not None and output is not None:
        state[namespace] = output
    return state


def _predicate_state(
    dag: dict[str, Any],
    current_id: str,
    result: NodeResult,
    record: DurableRunRecord | None,
) -> dict[str, object]:
    """Reconstruct GraphRun's plan/code/review slots from durable checkpoints."""
    state = _completed_predicate_state(dag, record)
    return _merge_current_predicate_state(state, dag, current_id, result)


def _result_value(
    result: NodeResult,
    path: str,
    *,
    predicate_state: dict[str, object] | None = None,
) -> object:
    """Resolve a canonical predicate path against durable execution state."""
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
    """Evaluate the canonical graph predicate dialect against durable state."""
    return evaluate_predicate(
        condition,
        lambda path: _result_value(result, path, predicate_state=predicate_state),
    )


def _next_node(
    dag: dict[str, Any],
    current_id: str,
    result: NodeResult,
    record: DurableRunRecord | None = None,
) -> str | None:
    """Pick the first outgoing edge whose canonical predicate is satisfied.

    Durable execution still has a single-node frontier; parallel fan-out is a
    separate convergence target. Within that constraint, edge selection uses
    the same predicate dialect and document-order precedence as GraphRun.
    """
    predicate_state = _predicate_state(dag, current_id, result, record)
    edges = dag.get("edges") or []
    outgoing = [e for e in edges if str(e.get("from_node") or e.get("from_role")) == current_id]
    for edge in outgoing:
        target = edge.get("to_node") or edge.get("to_role")
        if not target:
            continue
        condition = edge.get("condition")
        if condition and not _result_matches_condition(
            str(condition), result, predicate_state=predicate_state
        ):
            continue
        return str(target)
    return None


def _resolve_inputs(
    record: DurableRunRecord,
    node_id: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Build the inputs dict for the given node.

    Merge order (later wins):
      1. spec.inputs / spec.config — DAG-author-supplied defaults (used when
         no upstream provides the key).
      2. record.inputs — the run's initial inputs (entry-node case).
      3. Last completed node's output — flows forward as the default for the
         next node's matching input keys. Pydantic on the receiving node will
         drop any keys it doesn't recognize (extra='ignore'), so over-broad
         outputs don't break narrow inputs.

    Upstream output WINS over static so a node placed downstream of a
    transform gets the transformed value, not the original spec.input. A
    DAG author who needs the original static value to win can use an
    `input_map` (Phase 6 enhancement; not present in this v1 executor).
    """
    static_inputs = spec.get("inputs") or spec.get("config") or {}
    # Walk records in reverse to find the most recent COMPLETED upstream
    # output. We skip the current node (whose record was added with
    # phase=RUNNING before input resolution) and any earlier paused / failed
    # records.
    upstream_output: dict[str, Any] | None = None
    for nr in reversed(record.node_records):
        if nr.node_id == node_id:
            continue
        if nr.phase == NodePhase.COMPLETED and nr.output:
            upstream_output = nr.output
            break

    if upstream_output is not None:
        return {**static_inputs, **upstream_output}
    return {**static_inputs, **record.inputs}


def _lift_blackboard(record: DurableRunRecord, ctx: NodeContext) -> DurableRunRecord:
    """Persist blackboard.metadata + node_annotations mutations the node
    made in-place. Without this, every step rebuilds a fresh blackboard
    from the snapshot, so cross-step accumulators (dashboard sections,
    halt_requested, node_annotations) get lost."""
    bb = ctx.blackboard
    if bb is None or not hasattr(bb, "metadata"):
        return record
    new_snapshot = dict(record.blackboard_snapshot or {})
    new_snapshot["metadata"] = dict(getattr(bb, "metadata", {}) or {})
    annotations = getattr(bb, "node_annotations", None)
    if annotations is not None:
        new_snapshot["node_annotations"] = dict(annotations or {})
    return record.model_copy(update={"blackboard_snapshot": new_snapshot})


def _actually_spawned(kind: str, result: NodeResult) -> bool:
    """Did this node actually dispatch/execute a child graph, or just decline to?

    `agent.synth_dag` encodes a depth-cap or security-review refusal as
    `SynthDagOut(success=False, ...)` inside an otherwise-successful
    `NodeResult` (the executor sees a normal completion; only the node's own
    output says nothing was spawned) -- that refusal must not burn a depth
    level for the next node, or a workflow that tries an alternate synth
    after a blocked one hits the cap prematurely. But `success=False` also
    covers a *different* case: synthesis was approved and the sub-graph WAS
    dispatched via `run_graph`, and only the sub-graph's own execution
    failed -- that's a real spawn attempt and must still burn a depth level
    (otherwise a chained retry after a failed child bypasses the recursion
    budget). `SynthDagOut.dispatched` disambiguates the two: it's True only
    on the branch that actually called `run_graph`. `agent.spawn_harness`
    never reaches this check on a fresh dispatch (that exits earlier via
    `_checkpoint_pause`); getting here for that kind always means a resumed,
    already-completed external invocation, so it counts unconditionally.
    """
    if kind == "agent.synth_dag":
        output = result.output
        return bool(getattr(output, "success", True)) or bool(getattr(output, "dispatched", False))
    return True


def _maybe_increment_synth_depth(
    record: DurableRunRecord, spec: dict[str, Any], result: NodeResult
) -> DurableRunRecord:
    """Bump `synth_depth` after a node that can spawn a sub-graph completes.

    Depth increments for whatever runs *next*, not for the spawning node's
    own invocation -- descending into the spawned sub-graph is one level
    deeper; the spawning node itself already ran at its own depth. Mirrors
    `agent_synth_dag.py`'s `can_spawn(get_role(depth, max_depth))` check,
    which reads this same counter back out via `_build_ctx`.
    """
    kind = spec.get("kind")
    if kind not in _DEPTH_INCREMENTING_KINDS or not _actually_spawned(kind, result):
        return record
    snapshot = dict(record.blackboard_snapshot or {})
    metadata = dict(snapshot.get("metadata") or {})
    metadata["synth_depth"] = int(metadata.get("synth_depth", 0)) + 1
    snapshot["metadata"] = metadata
    return record.model_copy(update={"blackboard_snapshot": snapshot})


def _build_ctx(record: DurableRunRecord, node_id: str) -> NodeContext:
    """Reconstruct the NodeContext, lifting hitl_answers + blackboard
    snapshot so HITL/wait nodes see the same state across pauses.

    `synth_depth` is surfaced into `NodeContext.metadata` (not
    `blackboard.metadata`) because that's where `agent_synth_dag.py`'s
    `can_spawn(get_role(depth, max_depth))` check reads it from — mirroring
    how `hitl_answers` also lives in this same top-level metadata dict rather
    than the blackboard's.
    """
    from ..types import GraphBlackboard

    bb_snap = record.blackboard_snapshot or {}
    try:
        blackboard = GraphBlackboard(
            task_objective=str(bb_snap.get("task_objective") or ""),
            workspace=str(bb_snap.get("workspace") or ""),
            metadata=dict(bb_snap.get("metadata") or {}),
            node_annotations=dict(bb_snap.get("node_annotations") or {}),
        )
    except Exception:
        blackboard = None

    try:
        synth_depth = dict(bb_snap.get("metadata") or {}).get("synth_depth", 0)
    except (TypeError, ValueError):
        synth_depth = 0

    return NodeContext(
        run_id=record.run_id,
        dag_id=record.dag_id,
        node_id=node_id,
        user_id=record.user_id,
        project_id=record.project_id,
        blackboard=blackboard,
        metadata={
            "hitl_answers": dict(record.hitl_answers),
            "synth_depth": synth_depth,
        },
    )


def _existing_or_new_record(
    record: DurableRunRecord, node_id: str, *, kind: str
) -> DurableNodeRecord:
    for nr in record.node_records:
        if nr.node_id == node_id:
            return nr
    return DurableNodeRecord(node_id=node_id, kind=kind)


def _patch_node_record(
    record: DurableRunRecord, node_record: DurableNodeRecord
) -> DurableRunRecord:
    records = list(record.node_records)
    for i, nr in enumerate(records):
        if nr.node_id == node_record.node_id:
            records[i] = node_record
            return record.model_copy(update={"node_records": records})
    records.append(node_record)
    return record.model_copy(update={"node_records": records})


async def _checkpoint_success(
    record: DurableRunRecord,
    node_id: str,
    node_record: DurableNodeRecord,
    result: NodeResult,
    *,
    store: DurableRunStore,
) -> DurableRunRecord:
    output = result.output
    output_dump = output.model_dump() if isinstance(output, BaseModel) else (output or None)
    new_nr = node_record.model_copy(
        update={
            "phase": NodePhase.COMPLETED,
            "output": output_dump,
            "latency_ms": result.latency_ms,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "model_used": result.model_used,
            "cost_usd": result.cost_usd,
            "finished_at": datetime.now(UTC),
        }
    )
    record = _patch_node_record(record, new_nr)
    # Lift blackboard mutations from the ctx that the node may have touched.
    # The blackboard reference is on ctx but we don't have ctx here; the node
    # mutates `blackboard.metadata` in-place. Our _build_ctx reconstructed
    # the blackboard from snapshot so we need to capture changes via the
    # node's output_dump path — for nodes that mutate the blackboard (like
    # dashboard.append_section), they ALSO return a NodeResult whose output
    # tells us what changed. For Phase 1 we re-derive the blackboard by
    # re-running the snapshot reconciliation: re-build_ctx attaches a fresh
    # blackboard each invocation, so changes are local. The dashboard.append
    # node compensates by writing to ctx.metadata when blackboard is None;
    # in Phase 6 we'll add explicit blackboard-mutation events.
    record = record.model_copy(
        update={"version": record.version + 1, "last_step_at": datetime.now(UTC)}
    )
    return await store.update(record)


async def _checkpoint_pause(
    record: DurableRunRecord,
    node_id: str,
    node_record: DurableNodeRecord,
    result: NodeResult,
    *,
    store: DurableRunStore,
) -> DurableRunRecord:
    paused_reason = (result.metadata or {}).get("paused_reason") or ""
    pause_status = (
        RunStatus.PAUSED_HITL
        if paused_reason in {"awaiting_human_answer", "awaiting_human_approval"}
        else RunStatus.PAUSED_WAIT
    )
    new_nr = node_record.model_copy(
        update={
            "phase": NodePhase.PAUSED,
            "pause_metadata": dict(result.metadata or {}),
            "resume_at": result.resume_at,
        }
    )
    record = _patch_node_record(record, new_nr)
    updated = record.model_copy(
        update={
            "status": pause_status,
            "resume_at": result.resume_at,
            "version": record.version + 1,
            "last_step_at": datetime.now(UTC),
        }
    )
    return await store.update(updated)


async def _checkpoint_failure(
    record: DurableRunRecord,
    node_id: str,
    node_record: DurableNodeRecord,
    result: NodeResult,
    *,
    store: DurableRunStore,
) -> DurableRunRecord:
    new_nr = node_record.model_copy(
        update={
            "phase": NodePhase.FAILED,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "latency_ms": result.latency_ms,
            "finished_at": datetime.now(UTC),
        }
    )
    record = _patch_node_record(record, new_nr)
    return await _mark_failed(
        record,
        error_code=result.error_code or "NodeFailure",
        error_message=result.error_message or f"node {node_id} failed",
        store=store,
    )


async def _mark_completed(record: DurableRunRecord, *, store: DurableRunStore) -> DurableRunRecord:
    now = datetime.now(UTC)
    updated = record.model_copy(
        update={
            "status": RunStatus.COMPLETED,
            "finished_at": now,
            "last_step_at": now,
            "current_node_id": None,
            "version": record.version + 1,
        }
    )
    return await store.update(updated)


async def _mark_failed(
    record: DurableRunRecord,
    *,
    error_code: str,
    error_message: str,
    store: DurableRunStore,
) -> DurableRunRecord:
    now = datetime.now(UTC)
    updated = record.model_copy(
        update={
            "status": RunStatus.FAILED,
            "error_code": error_code,
            "error_message": error_message[:512],
            "finished_at": now,
            "last_step_at": now,
            "version": record.version + 1,
        }
    )
    return await store.update(updated)
