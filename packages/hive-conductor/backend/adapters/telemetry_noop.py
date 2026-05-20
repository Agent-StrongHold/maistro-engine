from __future__ import annotations

from contextlib import nullcontext
from typing import Any


class NoopTelemetry:
    def trace(self, **kwargs: Any) -> Any:
        return nullcontext()

    def generation(self, **kwargs: Any) -> Any:
        return nullcontext()
