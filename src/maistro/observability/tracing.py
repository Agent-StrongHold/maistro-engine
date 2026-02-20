"""Langfuse tracing integration for agent calls."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

import structlog

logger = structlog.get_logger()

P = ParamSpec("P")
T = TypeVar("T")

# Lazy Langfuse client — initialized on first use
_langfuse = None


def get_langfuse() -> Any | None:
    """Get or create Langfuse client. Returns None if not configured."""
    global _langfuse
    if _langfuse is not None:
        return _langfuse

    try:
        from langfuse import Langfuse

        _langfuse = Langfuse()
        return _langfuse
    except Exception:
        logger.warning("langfuse_not_configured")
        return None


def trace_agent(name: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to trace an agent function with Langfuse."""

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            langfuse = get_langfuse()

            if langfuse is None:
                return await fn(*args, **kwargs)  # type: ignore[misc]

            trace = langfuse.trace(name=name)
            span = trace.span(name=f"{name}.run")

            try:
                result = await fn(*args, **kwargs)  # type: ignore[misc]
                span.end(output=str(result)[:500])
                return result
            except Exception as exc:
                span.end(output=f"error: {exc}", level="ERROR")
                raise
            finally:
                langfuse.flush()

        return wrapper  # type: ignore[return-value]

    return decorator
