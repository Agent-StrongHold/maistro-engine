from __future__ import annotations

import json
import os
from typing import Any

from adapters.llm_http import HttpOpenAIProtocolLLM, StubLLMPort
from adapters.telemetry_langfuse import LangfuseTelemetry
from adapters.telemetry_noop import NoopTelemetry
from config import get_settings
from models.schemas import ChatCompletionRequest
from protocols.llm import LLMPort
from protocols.telemetry import TelemetryPort


def _get_secret(name: str, env_fallback: str | None = None) -> str | None:
    try:
        from services.foundation import get_foundation

        f = get_foundation()
        if f.vault_available and f.vault is not None:
            return f.vault.use(name, lambda v: v)
    except (RuntimeError, Exception):
        pass
    import os

    return os.environ.get(env_fallback or name)


def build_llm_port() -> LLMPort:
    s = get_settings()
    base = (s.litellm_api_base or "").strip()
    key = s.litellm_api_key.get_secret_value() if s.litellm_api_key else None
    if not key:
        key = _get_secret("litellm_api_key", "LITELLM_MASTER_KEY")
    if not base:
        base = _get_secret("litellm_api_base", "LITELLM_API_BASE")
    if not base or not key:
        return StubLLMPort()
    return HttpOpenAIProtocolLLM(
        base_url=base,
        api_key=key,
        variant=s.llm_http_variant,
    )


def build_telemetry() -> TelemetryPort:
    import os

    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        return LangfuseTelemetry()
    return NoopTelemetry()


def _effective_request(req: ChatCompletionRequest) -> ChatCompletionRequest:
    s = get_settings()
    return req.model_copy(update={"model": req.model or s.chat_default_model})


async def run_chat_completion(req: ChatCompletionRequest) -> dict[str, Any]:  # noqa: C901
    req = _effective_request(req)
    llm = build_llm_port()
    model = req.model


    from services.ha_tools import execute_ha_tool, fetch_devices, get_tool_definitions, ha_available

    tools = get_tool_definitions() if ha_available() else []
    messages = list(req.messages)

    if tools:
        devices = await fetch_devices()
        if devices:
            device_summary = "; ".join(f"{d['entity_id']} ({d['name']}, {d['state']})" for d in devices[:40])
            system_msg = {"role": "system", "content": f"You control a smart home via Home Assistant. Available devices: {device_summary}. When the user asks to control a device, call the ha_control function with the exact entity_id. For fan speed, use set_percentage. For delays, use wait. Be concise. Execute all steps automatically — do not ask for confirmation."}
            if not any(m.get("role") == "system" for m in messages):
                messages.insert(0, system_msg)

    for _ in range(5):
        tool_req = ChatCompletionRequest(
            messages=messages,
            model=model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            tools=tools if tools else None,
        )
        out = await llm.complete(tool_req)

        choice = (out.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls")

        if not tool_calls:
            return out

        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args_str = fn.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}
            if name == "ha_control":
                result = await execute_ha_tool(args)
            elif name == "ha_announce":
                from services.ha_tools import ha_available
                if ha_available():
                    import httpx as _httpx
                    msg_text = args.get("message", "")
                    target = args.get("target", "")
                    try:
                        async with _httpx.AsyncClient(timeout=10.0) as _c:
                            r = await _c.post(
                                "http://10.10.42.174:8123/api/services/notify/alexa_media",
                                headers={"Authorization": f"Bearer {os.environ.get('HA_TOKEN', '')}", "Content-Type": "application/json"},
                                json={"message": msg_text, "target": f"media_player.{target}", "data": {"type": "announce"}},
                            )
                            r.raise_for_status()
                            result = {"success": True, "message": msg_text, "target": target}
                    except Exception as _e:
                        result = {"error": f"Alexa announcement failed (is alexa_media_player configured?): {_e}"}
                else:
                    result = {"error": "HA not available"}
            elif name == "ha_confirm":
                from services.ha_tools import send_confirm
                result = await send_confirm(
                    message=args.get("message", "Confirm?"),
                    target=args.get("target", "blake"),
                    timeout_seconds=min(max(int(args.get("timeout_seconds", 120)), 10), 600),
                )
            elif name == "wait":
                import asyncio
                seconds = min(max(int(args.get("seconds", 1)), 1), 300)
                await asyncio.sleep(seconds)
                result = {"waited": seconds}
            else:
                result = {"error": f"unknown tool: {name}"}
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(result),
            })

    final_req = ChatCompletionRequest(messages=messages, model=model, temperature=req.temperature)
    return await llm.complete(final_req)
