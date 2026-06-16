"""Ollama provider for Evolve and RSI patch generation.

Calls a locally running Ollama instance via its OpenAI-compatible chat API.
No auth required. Model must already be pulled (`ollama pull <model>`).
"""

from __future__ import annotations

import json
from typing import Any


class OllamaProvider:
    """Async llm_call adapter backed by a local Ollama instance.

    Compatible with ToolLoopPatchProvider and EvolvingToolLoopPatchProvider.
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 300.0,
        temperature: float = 0.2,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature

    async def __call__(
        self,
        prompt_or_messages: str | list[dict[str, Any]],
        **_: Any,
    ) -> str:
        import httpx

        messages: list[dict[str, Any]]
        if isinstance(prompt_or_messages, str):
            messages = [{"role": "user", "content": prompt_or_messages}]
        else:
            messages = prompt_or_messages

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                response = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                )
            except httpx.ConnectError as exc:
                raise RuntimeError(
                    f"Cannot reach Ollama at {self._base_url}. "
                    "Is `ollama serve` running?"
                ) from exc

        if response.status_code != 200:
            raise RuntimeError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:500]}"
            )

        data: dict[str, Any] = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected Ollama response shape: {json.dumps(data)[:500]}"
            ) from exc
