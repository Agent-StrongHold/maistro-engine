from __future__ import annotations

import os
from contextlib import nullcontext
from typing import Any


def _keys_present() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


class LangfuseTelemetry:
    def __init__(self) -> None:
        self._enabled = _keys_present()
        self._base_url = os.environ.get("LANGFUSE_PUBLIC_KEY", "")

    def trace(self, **kwargs: Any) -> Any:
        if not self._enabled:
            return nullcontext()
        return nullcontext()

    def generation(self, **kwargs: Any) -> Any:
        if not self._enabled:
            return nullcontext()
        return nullcontext()
