"""Langfuse tracing integration for agent calls."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

import structlog

logger = structlog.get_logger()

P = ParamSpec("P")
T = TypeVar("T")

# Lazy Langfuse client — initialized on first use
_langfuse: Any | None = None
_langfuse_checked = False


def get_langfuse() -> Any | None:
    """Get or create Langfuse client. Returns None if not configured."""
    global _langfuse, _langfuse_checked
    if _langfuse_checked:
        return _langfuse

    _langfuse_checked = True
    try:
        import os
        # Only initialize if keys are actually configured
        if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
            return None
        from langfuse import Langfuse
        _langfuse = Langfuse()
        # Verify it actually works by checking the attribute exists
        if not hasattr(_langfuse, "trace"):
            _langfuse = None
        return _langfuse
    except Exception:
        logger.warning("langfuse_not_configured")
        _langfuse = None
        return None


def trace_agent(name: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to trace an agent function with Langfuse."""

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            langfuse = get_langfuse()

            if langfuse is None:
                return await fn(*args, **kwargs)  # type: ignore[misc]

            try:
                trace = langfuse.trace(name=name)
                span = trace.span(name=f"{name}.run")
            except Exception:
                # If tracing setup fails, run without tracing
                return await fn(*args, **kwargs)  # type: ignore[misc]

            try:
                result = await fn(*args, **kwargs)  # type: ignore[misc]
                span.end(output=str(result)[:500])
                return result
            except Exception as exc:
                span.end(output=f"error: {exc}", level="ERROR")
                raise
            finally:
                # Non-blocking flush — run in thread to avoid blocking the event loop
                try:
                    asyncio.get_running_loop().run_in_executor(None, langfuse.flush)
                except Exception:
                    pass

        return wrapper  # type: ignore[return-value]

    return decorator
