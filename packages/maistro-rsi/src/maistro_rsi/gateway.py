"""Gateway-backed ``llm_call`` for real benchmark evaluation.

`maistro_evolve`'s benchmark runners score a genome by calling an async
``llm_call(messages, *, temperature, max_tokens) -> str`` against a model — but
only when one is supplied. Given ``llm_call=None`` they fall back to a heuristic
(near-noise) score. `RsiCycle` used to pass nothing, so its "real benchmarks"
were never actually real. This module builds the missing callable: a thin async
client for the LiteLLM gateway (OpenAI-compatible ``/v1/chat/completions``), so
every provider the gateway exposes is reachable by model alias.

Kept dependency-free (httpx only, already a maistro-rsi dep) and reads the
gateway URL/key from the environment at call time, so it never bakes in config
and picks up whatever the caller has loaded (e.g. from the engine .env).
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

import httpx

# What the evolve benchmark runners expect: given a chat-message list (and
# optional sampling params), return the model's text response.
LlmCall = Callable[..., Awaitable[str]]


def _gateway_base() -> str:
    return (
        os.environ.get("LITELLM_URL")
        or os.environ.get("LITELLM_BASE_URL")
        or os.environ.get("LITELLM_PROXY_URL")
        or ""
    ).rstrip("/")


def _gateway_key() -> str:
    return os.environ.get("LITELLM_MASTER_KEY") or os.environ.get("LITELLM_PROXY_KEY") or ""


def make_gateway_llm_call(model: str, *, timeout: float = 60.0) -> LlmCall:
    """Return an async ``llm_call`` that routes to ``model`` via the gateway.

    The URL/key are resolved on each call (not captured here), so the callable
    keeps working if the environment is populated after it's constructed.
    """

    async def llm_call(
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        base = _gateway_base()
        if not base:
            raise RuntimeError(
                "LiteLLM gateway not configured — set LITELLM_URL (+ LITELLM_MASTER_KEY). "
                "Benchmark scoring needs a live gateway to be real."
            )
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers={"Authorization": f"Bearer {_gateway_key()}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"].get("content") or ""

    return llm_call
