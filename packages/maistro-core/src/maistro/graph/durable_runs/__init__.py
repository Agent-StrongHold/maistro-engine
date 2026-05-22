"""Durable DAG run state — persists across process restarts.

This is the *execution* state layer (vs. `hive-conductor/services/dag_run_store.py`
which is the observability/SSE layer). A durable run survives crashes and
container restarts; the executor can be torn down and rebuilt at any point
between checkpoints.

State machine:

    pending ─► running ─► completed
                  │
                  ├──► paused_wait ──► (resume_at fires) ──► running
                  ├──► paused_hitl ──► (user answers) ─────► running
                  ├──► failed
                  └──► cancelled

Checkpoints land at:
 - run creation                        (status: pending → running)
 - after each node completes successfully (record NodeResult + advance pointer)
 - just before a node pauses             (status → paused_wait / paused_hitl)
 - on failure                            (status → failed)
 - on completion                         (status → completed)

The executor (:func:`run_durable_dag`) is idempotent across resume — calling
it on a paused run picks up where it left off.
"""

from __future__ import annotations

from .executor import resume_durable_dag, run_durable_dag
from .protocol import DurableRunStore
from .stores import InMemoryDurableRunStore, SqliteDurableRunStore
from .types import (
    DurableNodeRecord,
    DurableRunRecord,
    NodePhase,
    RunStatus,
)

__all__ = [
    "DurableNodeRecord",
    "DurableRunRecord",
    "DurableRunStore",
    "InMemoryDurableRunStore",
    "NodePhase",
    "RunStatus",
    "SqliteDurableRunStore",
    "resume_durable_dag",
    "run_durable_dag",
]
