"""Async-safe propagation of the canonical execution context.

Capabilities often execute several layers below an adapter boundary. A
ContextVar keeps run/workspace lineage available through async call stacks
without adding a runtime parameter to every existing capability protocol.
Explicit context arguments remain appropriate at process/service boundaries.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator

from .types import ExecutionContext

_CURRENT_EXECUTION: ContextVar[ExecutionContext | None] = ContextVar(
    "maistro_execution_context",
    default=None,
)


def current_execution_context(*, required: bool = False) -> ExecutionContext | None:
    """Return the context bound to the current async execution scope."""
    context = _CURRENT_EXECUTION.get()
    if required and context is None:
        raise RuntimeError("no MAIstro execution context is bound")
    return context


@contextmanager
def bind_execution_context(context: ExecutionContext) -> Iterator[ExecutionContext]:
    """Bind context for this call stack and restore the prior scope on exit."""
    token = _CURRENT_EXECUTION.set(context)
    try:
        yield context
    finally:
        _CURRENT_EXECUTION.reset(token)


__all__ = ["bind_execution_context", "current_execution_context"]
