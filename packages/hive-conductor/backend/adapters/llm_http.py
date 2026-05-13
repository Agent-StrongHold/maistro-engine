from __future__ import annotations

from typing import Any, Literal

import httpx

from models.schemas import ChatCompletionRequest


def stub_completion(req: ChatCompletionRequest) -> dict[str, Any]:
    from uuid import uuid4

    return {
        "id": str(uuid4()),
        "model": req.model,
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "(stub) Set LITELLM_API_BASE (…/v1) and LITELLM_API_KEY to call your gateway "
                        "through the LLMPort adapter."
                    ),
                }
            }
        ],
    }


def _normalize_to_chat_completions(body: dict[str, Any]) -> dict[str, Any]:
    if "choices" in body:
        return body
    parts: list[str] = []
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") in ("output_text", "input_text") and "text" in c:
                    parts.append(str(c["text"]))
                elif isinstance(c.get("text"), str):
                    parts.append(c["text"])
    text = "".join(parts).strip() or "(gateway returned /responses JSON without extractable text)"
    return {
        "id": str(body.get("id", "")),
        "model": str(body.get("model", "")),
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "_hive_protocol": "responses",
    }


class StubLLMPort:
    async def complete(self, req: ChatCompletionRequest) -> dict[str, Any]:
        return stub_completion(req)


class HttpOpenAIProtocolLLM:
    """HTTP adapter: try OpenAI **Responses** (`POST …/v1/responses`) when useful, else **chat.completions**."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        variant: Literal["auto", "responses", "chat_completions"],
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._variant = variant

    async def complete(self, req: ChatCompletionRequest) -> dict[str, Any]:
        model = req.model
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            if self._variant in ("auto", "responses"):
                r = await client.post(
                    f"{self._base}/responses",
                    headers=headers,
                    json={"model": model, "input": req.messages},
                )
                if r.is_success:
                    return _normalize_to_chat_completions(r.json())
                if self._variant == "responses":
                    r.raise_for_status()

            payload: dict[str, Any] = {
                "model": model,
                "messages": req.messages,
                "temperature": req.temperature,
                "stream": False,
            }
            if req.max_tokens is not None:
                payload["max_tokens"] = req.max_tokens
            r2 = await client.post(f"{self._base}/chat/completions", headers=headers, json=payload)
            r2.raise_for_status()
            return r2.json()
