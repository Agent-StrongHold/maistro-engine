"""Durable checkpoint bridges for non-advancing Graph state changes."""

from __future__ import annotations

from maistro.graph.traversal_commit import TraversalCheckpoint, graph_state_hash

from . import executor as traversal
from .protocol import DurableRunStore
from .types import DurableRunRecord


def _active_source_node_run_ids(record: DurableRunRecord) -> tuple[str, ...] | None:
    source_ids: list[str] = []
    for node_id in record.graph_state.active_node_ids:
        source = next(
            (node_run for node_run in reversed(record.node_runs) if node_run.node_id == node_id),
            None,
        )
        if source is None:
            return None
        source_ids.append(source.node_run_id)
    return tuple(source_ids)


async def checkpoint_nonadvancing_state(
    record: DurableRunRecord,
    *,
    store: DurableRunStore,
) -> DurableRunRecord:
    """Persist a checkpoint when durable Graph state changed without advancement.

    HITL answers mutate Graph metadata and logical visit state without routing.
    Capturing that state before resumed execution gives the next TraversalCommit
    a content-addressed bridge from the previous advancing commit.
    """
    if not record.graph_state.active_node_ids:
        return record
    state_hash = graph_state_hash(record.graph_state)
    latest = record.latest_traversal_checkpoint
    if latest is not None and latest.state_hash == state_hash:
        return record
    source_ids = _active_source_node_run_ids(record)
    if source_ids is None:
        return record
    checkpoint = TraversalCheckpoint.from_state(
        graph_snapshot_hash=record.run.graph.content_hash,
        state=record.graph_state,
        ordered_source_node_run_ids=source_ids,
        checkpoint_sequence=len(record.traversal_checkpoints) + 1,
    )
    return await traversal._checkpoint(
        record,
        store=store,
        traversal_checkpoints=(*record.traversal_checkpoints, checkpoint),
    )


__all__ = ["checkpoint_nonadvancing_state"]
