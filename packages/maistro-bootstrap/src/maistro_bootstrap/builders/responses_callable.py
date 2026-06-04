"""Anthropic API adapter for the builders agent loop."""

from __future__ import annotations

import os
from typing import Any


class ResponsesAPICallable:
    """Calls the Anthropic Messages API.

    Falls back to a stub if the ``anthropic`` package is not installed,
    so the TUI can still start without it — the agent just won't have
    a live LLM until the dep is present.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("MAISTRO_BUILDERS_MODEL", "claude-sonnet-4-6")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic  # type: ignore[import-not-found]

                self._client = anthropic.Anthropic()
            except ImportError as exc:
                raise ImportError(
                    "anthropic package not installed. Run: uv sync --extra builders"
                ) from exc
        return self._client

    def __call__(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        client = self._get_client()
        system = None
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                user_messages.append(m)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": user_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = client.messages.create(**kwargs)
        block = response.content[0] if response.content else None
        content = block.text if block and hasattr(block, "text") else ""
        return {
            "content": content,
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }
