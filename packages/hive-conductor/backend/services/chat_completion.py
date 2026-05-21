from __future__ import annotations

import json
import os
from typing import Any

from adapters.llm_http import HttpOpenAIProtocolLLM, StubLLMPort
from adapters.telemetry_langfuse import LangfuseTelemetry
from adapters.telemetry_noop import NoopTelemetry
from models.schemas import ChatCompletionRequest
from protocols.llm import LLMPort
from protocols.telemetry import TelemetryPort

from config import get_settings


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


async def run_chat_completion(req: ChatCompletionRequest, return_actions: bool = False, skip_summary: bool = False, _llm: LLMPort | None = None, _model: str | None = None) -> dict[str, Any]:  # noqa: C901
    req = _effective_request(req)
    llm = _llm or build_llm_port()
    model = _model or req.model


    from services.ha_tools import execute_ha_tool, fetch_devices, get_tool_definitions, ha_available

    tools = get_tool_definitions() if ha_available() else []
    messages = list(req.messages)

    browser_agent_url = os.environ.get("BROWSER_AGENT_URL", "http://localhost:8200")
    browser_agent_key = os.environ.get("BROWSER_AGENT_KEY", "sk-conductor-agent-2026")
    browser_tool = {
        "type": "function",
        "function": {
            "name": "browser_task",
            "description": "Run a browser automation task using Playwright with vision AI. Can navigate websites, click buttons, fill forms, extract data, take screenshots, and interact with any web page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Natural language description of what to do in the browser (e.g. 'Go to example.com and find the pricing')"},
                    "url": {"type": "string", "description": "Starting URL (optional)"},
                    "max_steps": {"type": "integer", "description": "Max steps for the agent (default 25, max 50)"},
                },
                "required": ["task"],
            },
        },
    }
    tools.append(browser_tool)

    executed_actions: list[dict[str, Any]] = []

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
            if return_actions:
                out["actions"] = executed_actions
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
                executed_actions.append({"tool": name, "args": args, "result": result})
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
                executed_actions.append({"tool": name, "args": args, "result": result})
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
            elif name == "browser_task":
                import httpx as _hcx
                task_desc = args.get("task", "")
                if not task_desc:
                    result = {"error": "task is required"}
                else:
                    try:
                        async with _hcx.AsyncClient(timeout=120.0) as _bc:
                            r = await _bc.post(
                                f"{browser_agent_url}/task/browse",
                                headers={"Authorization": f"Bearer {browser_agent_key}", "Content-Type": "application/json"},
                                json={"task": task_desc, "url": args.get("url"), "max_steps": min(int(args.get("max_steps", 25)), 50), "use_vision": True},
                            )
                            if r.status_code == 200:
                                result = r.json()
                            else:
                                result = {"error": f"browser agent returned {r.status_code}: {r.text[:500]}"}
                    except Exception as _be:
                        result = {"error": f"browser agent failed: {_be}"}
            else:
                result = {"error": f"unknown tool: {name}"}
            if name != "ha_control" and name != "ha_announce":
                executed_actions.append({"tool": name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(result),
            })

        if skip_summary and executed_actions:
            break

    if skip_summary and executed_actions:
        parts = []
        for a in executed_actions:
            tool = a.get("tool", "")
            result = a.get("result", {})
            args = a.get("args", {})
            if result.get("success"):
                if tool == "ha_control":
                    entity = args.get("entity_id", "").split(".")[-1].replace("_", " ")
                    action = args.get("action", "").replace("_", " ")
                    if action == "set percentage":
                        action = "set speed on"
                    elif action == "turn on":
                        action = "turned on"
                    elif action == "turn off":
                        action = "turned off"
                    elif action == "toggle":
                        action = "toggled"
                    parts.append(f"{action} {entity}")
                elif tool == "browser_task":
                    parts.append("browsed the web")
                else:
                    parts.append(f"executed {tool}")
            else:
                parts.append(f"failed: {result.get('error', 'unknown')}")
        reply = "; ".join(parts) if parts else "done"
        from uuid import uuid4
        final_out = {
            "id": str(uuid4()),
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": reply}}],
        }
        if return_actions:
            final_out["actions"] = executed_actions
        return final_out

    final_req = ChatCompletionRequest(messages=messages, model=model, temperature=req.temperature)
    final_out = await llm.complete(final_req)
    if return_actions:
        final_out["actions"] = executed_actions
    return final_out
