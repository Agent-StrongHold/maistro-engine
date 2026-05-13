from __future__ import annotations

import os
from contextlib import nullcontext
from typing import Any


def _keys_present() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def _sync_langfuse_base_url() -> None:
    if os.getenv("LANGFUSE_BASE_URL"):
        return
    host = os.getenv("LANGFUSE_HOST")
    if host:
        os.environ["LANGFUSE_BASE_URL"] = host.rstrip("/")


class LangfuseTelemetry:
    """Langfuse Python SDK 3.9+ (``get_client``) behind :class:`protocols.telemetry.TelemetryPort`."""

    def generation(
        self,
        *,
        name: str,
        model: str,
        input: Any,
        metadata: dict[str, Any] | None = None,
    ):
        if not _keys_present():
            return nullcontext(None)
        try:
            from langfuse import get_client
        except ImportError:
            return nullcontext(None)
        _sync_langfuse_base_url()
        return get_client().start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=input,
            metadata=metadata or {},
        )

    def flush(self) -> None:
        if not _keys_present():
            return
        try:
            from langfuse import get_client

            get_client().flush()
        except Exception:
            pass
