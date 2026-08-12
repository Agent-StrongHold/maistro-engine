"""Canonical MAIstro execution runtime.

Product entry points should create or recover a workspace-owned Run through
this package, then let specialized adapters perform the execution mechanics.
"""

from .runtime import ExecutionRuntime, GraphExecutionResult
from .types import ExecutionContext, RunContext, RunKind, RunState, WorkspaceRef

__all__ = [
    "ExecutionContext",
    "ExecutionRuntime",
    "GraphExecutionResult",
    "RunContext",
    "RunKind",
    "RunState",
    "WorkspaceRef",
]
