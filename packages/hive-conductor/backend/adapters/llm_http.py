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
        base = base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        self._base = base
        self._key = api_key
        self._variant = variant

    async def complete(self, req: ChatCompletionRequest) -> dict[str, Any]:
        model = req.model
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            payload: dict[str, Any] = {
                "model": model,
                "messages": req.messages,
                "temperature": req.temperature,
                "stream": False,
            }
            if req.max_tokens is not None:
                payload["max_tokens"] = req.max_tokens
            if req.tools:
                payload["tools"] = req.tools
            r2 = await client.post(f"{self._base}/chat/completions", headers=headers, json=payload)
            r2.raise_for_status()
            return r2.json()

    async def stream_complete(self, req: "ChatCompletionRequest"):
        """Stream tokens from the LLM. Yields dicts: {type:'token',content} or {type:'tool_calls',calls:[...]}."""
        import json as _json
        model = req.model or self._model
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "model": model, "messages": req.messages, "temperature": req.temperature, "stream": True,
        }
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
        if req.tools:
            payload["tools"] = req.tools

        tool_calls: dict[int, dict[str, Any]] = {}  # index → {id, name, arguments}

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self._base}/chat/completions", headers=headers, json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})

                        # Content tokens
                        if delta.get("content"):
                            yield {"type": "token", "content": delta["content"]}

                        # Tool call accumulation
                        if delta.get("tool_calls"):
                            for tc_delta in delta["tool_calls"]:
                                idx = tc_delta.get("index", 0)
                                if idx not in tool_calls:
                                    tool_calls[idx] = {"id": tc_delta.get("id", ""), "name": "", "arguments": ""}
                                if tc_delta.get("id"):
                                    tool_calls[idx]["id"] = tc_delta["id"]
                                fn = tc_delta.get("function", {})
                                if fn.get("name"):
                                    tool_calls[idx]["name"] = fn["name"]
                                if fn.get("arguments"):
                                    tool_calls[idx]["arguments"] += fn["arguments"]
                    except _json.JSONDecodeError:
                        continue

        # After stream ends, yield accumulated tool calls if any
        if tool_calls:
            calls = [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}} for tc in sorted(tool_calls.values(), key=lambda x: x.get("id", ""))]
            yield {"type": "tool_calls", "calls": calls}
