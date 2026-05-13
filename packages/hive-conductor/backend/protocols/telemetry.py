from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol


class TelemetryPort(Protocol):
    """Trace / observe model calls without importing a specific vendor in route handlers."""

    def generation(
        self,
        *,
        name: str,
        model: str,
        input: Any,
        metadata: dict[str, Any] | None = None,
    ) -> AbstractContextManager[Any]:
        """Context manager yielding an object with optional ``.update(...)`` (Langfuse-style)."""
        ...

    def flush(self) -> None:
        """Best-effort flush for short-lived workers."""
        ...
