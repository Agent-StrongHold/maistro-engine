"""Durable canonical Graph execution state.

The canonical :class:`maistro.runs.model.Run` owns lifecycle and scope.
:class:`maistro.graph.execution_state.GraphExecutionState` owns only graph
traversal facts. This package persists the two together with chronological
canonical NodeRuns and physical Attempts so execution can resume after process
loss without inventing a parallel execution repository.
"""

from __future__ import annotations

from maistro.runs.model import RunStatus

from .execution_store import DurableAttemptExecutionStore
from .executor import (
    NodeResolver,
    resume_durable_graph,
    run_durable_graph,
)
from .protocol import DurableRunStore
from .stores import InMemoryDurableRunStore, SqliteDurableRunStore
from .types import DurableRunRecord

__all__ = [
    "DurableAttemptExecutionStore",
    "DurableRunRecord",
    "DurableRunStore",
    "InMemoryDurableRunStore",
    "NodeResolver",
    "RunStatus",
    "SqliteDurableRunStore",
    "resume_durable_graph",
    "run_durable_graph",
]
