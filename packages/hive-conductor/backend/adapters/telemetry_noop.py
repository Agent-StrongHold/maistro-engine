from __future__ import annotations

from contextlib import nullcontext
from typing import Any


class NoopTelemetry:
    def generation(
        self,
        *,
        name: str,
        model: str,
        input: Any,
        metadata: dict[str, Any] | None = None,
    ):
        return nullcontext(None)

    def flush(self) -> None:
        return None
