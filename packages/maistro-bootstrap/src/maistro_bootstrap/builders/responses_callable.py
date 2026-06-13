"""LiteLLM-gateway callable for the builders agent loop.

Reads at call time (never baked in):
  - LITELLM_URL / LITELLM_BASE_URL / LITELLM_PROXY_URL — gateway base URL
  - LITELLM_MASTER_KEY / LITELLM_PROXY_KEY          — bearer key
  - MAISTRO_BUILDERS_MODEL / DEFAULT_MODEL           — default model alias

The gateway exposes an OpenAI-compatible /v1/chat/completions endpoint, so
every LiteLLM-supported provider (Anthropic, OpenAI, Groq, Mistral, Ollama,
Azure, Bedrock, …) is reachable by changing the model alias.

Falls back to a stub response when the gateway is not configured so the TUI
can still start in dev mode without a running proxy.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return (
        os.environ.get("LITELLM_URL")
        or os.environ.get("LITELLM_BASE_URL")
        or os.environ.get("LITELLM_PROXY_URL")
        or ""
    ).rstrip("/")


def _api_key() -> str:
    return os.environ.get("LITELLM_MASTER_KEY") or os.environ.get("LITELLM_PROXY_KEY") or ""


def _default_model() -> str:
    return (
        os.environ.get("MAISTRO_BUILDERS_MODEL")
        or os.environ.get("DEFAULT_MODEL")
        or "claude-sonnet-4-6"
    )


class LiteLLMCallable:
    """Synchronous OpenAI-compatible callable backed by the LiteLLM proxy.

    Supports tool definitions in OpenAI function-calling format so the agent
    loop can dispatch read_file / write_file / run_tests / etc. through the
    gateway's tool-use flow without being tied to a single provider SDK.
    """

    def __init__(self, model: str | None = None, timeout: float = 120.0) -> None:
        self.model = model or _default_model()
        self.timeout = timeout

    def _is_configured(self) -> bool:
        return bool(_base_url() and _api_key())

    def __call__(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        if not self._is_configured():
            logger.warning("LiteLLM gateway not configured — returning stub response")
            return {
                "content": (
                    "(LiteLLM not configured — set LITELLM_URL + LITELLM_MASTER_KEY. "
                    "54+ models available once connected.)"
                ),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            # LiteLLM forwards OpenAI-format tool definitions to every provider
            # that supports function-calling (Anthropic, OpenAI, Mistral, …).
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                    },
                }
                for t in tools
            ]
            body["tool_choice"] = "auto"

        resp = httpx.post(
            f"{_base_url()}/v1/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {_api_key()}"},
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"LiteLLM gateway {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]
        content = msg.get("content") or ""
        stop_reason = choice.get("finish_reason", "end_turn")

        # Normalise tool_calls into the same block-list shape the agent loop expects.
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            blocks: list[dict[str, Any]] = []
            for tc in tool_calls:
                fn = tc.get("function", {})
                import json

                try:
                    inp = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    inp = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", "tc_0"),
                        "name": fn.get("name", ""),
                        "input": inp,
                    }
                )
            content = blocks
            stop_reason = "tool_use"

        usage = data.get("usage", {})
        return {
            "content": content,
            "stop_reason": stop_reason,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
        }


# Backwards-compat alias — the TUI imported this name.
ResponsesAPICallable = LiteLLMCallable
