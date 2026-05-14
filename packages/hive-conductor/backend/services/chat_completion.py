from __future__ import annotations

import contextlib
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


async def run_chat_completion(req: ChatCompletionRequest) -> dict[str, Any]:
    """Orchestrate telemetry + LLM port (protocol-agnostic entry used by HTTP routes)."""
    req = _effective_request(req)
    llm = build_llm_port()
    tel = build_telemetry()
    model = req.model
    with tel.generation(
        name="hive-chat-completion",
        model=model,
        input=req.messages,
        metadata={"source": "hive-conductor"},
    ) as span:
        try:
            out = await llm.complete(req)
            if span is not None:
                with contextlib.suppress(Exception):
                    span.update(output=out)
            tel.flush()
            return out
        except Exception as exc:
            if span is not None:
                with contextlib.suppress(Exception):
                    span.update(level="ERROR", status_message=str(exc))
            tel.flush()
            raise
