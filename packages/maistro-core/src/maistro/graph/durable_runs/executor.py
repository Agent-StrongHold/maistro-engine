"""Compatibility surface for canonical durable Graph execution.

The implementation lives in :mod:`frontier_executor`, where the durable
executor operates on the full ``GraphExecutionState.active_node_ids`` frontier.
This module preserves the established import surface while the repository
converges on that implementation.
"""

from __future__ import annotations

from . import frontier_executor as _impl

NodeResolver = _impl.NodeResolver
resume_durable_graph = _impl.resume_durable_graph
run_durable_graph = _impl.run_durable_graph

# Private helpers are intentionally preserved because the focused durable-run
# contract and mutation suites exercise them directly.
_actually_spawned = _impl._actually_spawned
_build_ctx = _impl._build_ctx
_checkpoint = _impl._checkpoint
_checkpoint_failure = _impl._checkpoint_failure
_checkpoint_pause = _impl._checkpoint_pause
_checkpoint_success = _impl._checkpoint_success
_clear_pause_metadata = _impl._clear_pause_metadata
_completed_predicate_state = _impl._completed_predicate_state
_dedupe = _impl._dedupe
_edge_parallel = _impl._edge_parallel
_ensure_frontier_node_runs = _impl._ensure_frontier_node_runs
_ensure_running_node_run = _impl._ensure_running_node_run
_entry_node = _impl._entry_node
_finish_walk = _impl._finish_walk
_initial_inputs = _impl._initial_inputs
_lift_blackboard = _impl._lift_blackboard
_mark_completed = _impl._mark_completed
_mark_failed = _impl._mark_failed
_maybe_increment_synth_depth = _impl._maybe_increment_synth_depth
_merge_current_predicate_state = _impl._merge_current_predicate_state
_new_run = _impl._new_run
_next_node = _impl._next_node
_next_nodes = _impl._next_nodes
_node_spec = _impl._node_spec
_predicate_namespace = _impl._predicate_namespace
_predicate_state = _impl._predicate_state
_replace_node_run = _impl._replace_node_run
_replace_record = _impl._replace_record
_replace_state = _impl._replace_state
_result_matches_condition = _impl._result_matches_condition
_result_output = _impl._result_output
_result_value = _impl._result_value
_running_run = _impl._running_run
_value_at_path = _impl._value_at_path
_walk = _impl._walk

__all__ = ["NodeResolver", "resume_durable_graph", "run_durable_graph"]
