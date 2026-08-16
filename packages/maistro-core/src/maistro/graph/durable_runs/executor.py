"""Compatibility surface for canonical durable Graph execution.

The implementation lives in :mod:`frontier_executor`, where the durable
executor operates on the full ``GraphExecutionState.active_node_ids`` frontier.
This module preserves the established import surface while the repository
converges on that implementation.
"""

from __future__ import annotations

from .frontier_executor import (
    NodeResolver,
    _actually_spawned,
    _build_ctx,
    _checkpoint,
    _checkpoint_failure,
    _checkpoint_pause,
    _checkpoint_success,
    _clear_pause_metadata,
    _completed_predicate_state,
    _dedupe,
    _edge_parallel,
    _ensure_frontier_node_runs,
    _ensure_running_node_run,
    _entry_node,
    _finish_walk,
    _initial_inputs,
    _lift_blackboard,
    _mark_completed,
    _mark_failed,
    _maybe_increment_synth_depth,
    _merge_current_predicate_state,
    _new_run,
    _next_node,
    _next_nodes,
    _node_spec,
    _predicate_namespace,
    _predicate_state,
    _replace_node_run,
    _replace_record,
    _replace_state,
    _result_matches_condition,
    _result_output,
    _result_value,
    _running_run,
    _value_at_path,
    _walk,
    resume_durable_graph,
    run_durable_graph,
)

__all__ = ["NodeResolver", "resume_durable_graph", "run_durable_graph"]
