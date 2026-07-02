"""LiteLLM-gateway callable for the builders agent loop.

Reads at call time (never baked in):
  - LITELLM_URL / LITELLM_BASE_URL / LITELLM_PROXY_URL — gateway base URL
  - LITELLM_MASTER_KEY / LITELLM_PROXY_KEY          — bearer key
  - MAISTRO_BUILDERS_MODEL / DEFAULT_MODEL           — default model alias

The gateway exposes an OpenAI-compatible /v1/chat/completions endpoint, so
every LiteLLM-supported provider (Anthropic, OpenAI, Groq, Mistral, Ollama,
Azure, Bedrock, …) is reachable by changing the model alias.

`maistro builders` runs on the bare host (a `uv tool install`, not a
container), so none of the above are set by default — they only live in the
engine checkout's .env, used by docker-compose. `_ensure_env_loaded()` fills
that gap once per process: find the engine root (MAISTRO_REPO_ROOT env var,
then an upward walk from CWD), load its .env for any of the above keys that
aren't already real env vars, and rewrite the Docker-internal `litellm`
hostname to 127.0.0.1 since that's not reachable from the host. Already-set
env vars are never overridden — this only fills gaps.

Falls back to a stub response when the gateway is not configured so the TUI
can still start in dev mode without a running proxy.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_ENV_KEYS = (
    "LITELLM_URL",
    "LITELLM_BASE_URL",
    "LITELLM_PROXY_URL",
    "LITELLM_MASTER_KEY",
    "LITELLM_PROXY_KEY",
    "MAISTRO_BUILDERS_MODEL",
    "DEFAULT_MODEL",
)

_env_loaded = False


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def _ensure_env_loaded() -> None:
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True

    # Never reach outside the test process during a test run — tests rely on
    # "no env vars set" meaning "gateway not configured" (stub response), and
    # silently picking up a real .env from a nearby engine-root checkout would
    # break that isolation. PYTEST_CURRENT_TEST is set by pytest itself for
    # every test, so this needs no coordination with any test suite's conftest.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    # Don't early-return just because a URL is exported: a user may have
    # LITELLM_URL in their shell but keep the key/model only in the engine .env.
    # We still parse .env below and fill *only* the keys that aren't already set
    # (the `not os.environ.get(key)` guard), so an exported value is never
    # overridden — this just stops a lone URL from starving the key/model.
    from maistro_bootstrap.repo_root import find_maistro_engine_root

    # find_maistro_engine_root() already checks MAISTRO_REPO_ROOT first,
    # then walks upward from cwd.
    root = find_maistro_engine_root()
    if root is None:
        return

    env_file = root / ".env"
    if not env_file.is_file():
        return

    values = _parse_env_file(env_file)
    for key in _ENV_KEYS:
        if key in values and not os.environ.get(key):
            os.environ[key] = values[key]

    # Docker Compose's internal service name — unreachable from the host.
    for key in ("LITELLM_URL", "LITELLM_BASE_URL", "LITELLM_PROXY_URL"):
        val = os.environ.get(key, "")
        if "://litellm:" in val:
            os.environ[key] = val.replace("://litellm:", "://127.0.0.1:")


def _base_url() -> str:
    _ensure_env_loaded()
    return (
        os.environ.get("LITELLM_URL")
        or os.environ.get("LITELLM_BASE_URL")
        or os.environ.get("LITELLM_PROXY_URL")
        or ""
    ).rstrip("/")


def _api_key() -> str:
    _ensure_env_loaded()
    return os.environ.get("LITELLM_MASTER_KEY") or os.environ.get("LITELLM_PROXY_KEY") or ""


def _default_model() -> str:
    # Must load .env before reading these — ResponsesAPICallable.__init__ calls
    # this at construction time, which is *before* the first _base_url() call, so
    # without this a fresh-terminal process (where MAISTRO_BUILDERS_MODEL/
    # DEFAULT_MODEL live only in .env, not the shell) would bake in the stale
    # fallback alias and 400 on the first turn.
    _ensure_env_loaded()
    return (
        os.environ.get("MAISTRO_BUILDERS_MODEL")
        or os.environ.get("DEFAULT_MODEL")
        or "claude-sonnet-4-6"
    )


def _tool_result_to_text(content: Any) -> str:
    """Flatten a tool_result's content into a plain string.

    The agent loop passes tool output as a str, but Anthropic also allows a list
    of content blocks — handle both so the OpenAI `tool` message always carries a
    string body.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", "") or str(block.get("content", "")))
            else:
                parts.append(str(block))
        return "".join(parts)
    return "" if content is None else str(content)


def _split_content_blocks(
    content: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Split an Anthropic content-block list into (tool_calls, tool_results, text).

    tool_use blocks become OpenAI ``tool_calls`` entries; tool_result blocks
    become ``{"role": "tool", ...}`` messages; text (and anything unrecognised)
    is accumulated as plain string parts.
    """
    import json

    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            text_parts.append(str(block))
            continue
        btype = block.get("type")
        if btype == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id", "tc_0"),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                }
            )
        elif btype == "tool_result":
            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id", ""),
                    "content": _tool_result_to_text(block.get("content", "")),
                }
            )
        elif btype == "text":
            text_parts.append(block.get("text", ""))
        else:
            text_parts.append(str(block))
    return tool_calls, tool_results, text_parts


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate Anthropic-style tool blocks into OpenAI chat-completion shape.

    The agent loop keeps history in Anthropic form — an assistant turn's content
    is a list of ``{"type": "tool_use", ...}`` blocks, and tool outputs come back
    as a user message whose content is a list of ``{"type": "tool_result", ...}``
    blocks. LiteLLM's ``/v1/chat/completions`` is OpenAI-shaped and rejects those
    (``invalid content type=tool_result``), so on the *request* side we convert:
      - assistant ``tool_use`` blocks -> an assistant message with ``tool_calls``
      - user ``tool_result`` blocks   -> one ``{"role": "tool", ...}`` message each
    Plain string-content messages pass through untouched, so the common
    (no-tool) path is unaffected.
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            out.append(msg)
            continue

        tool_calls, tool_results, text_parts = _split_content_blocks(content)

        if tool_results:
            out.extend(tool_results)
            leftover = "".join(text_parts).strip()
            if leftover:
                out.append({"role": "user", "content": leftover})
        elif tool_calls:
            out.append(
                {
                    "role": msg.get("role", "assistant"),
                    "content": "".join(text_parts),
                    "tool_calls": tool_calls,
                }
            )
        else:
            out.append({"role": msg.get("role", "user"), "content": "".join(text_parts)})
    return out


class LiteLLMCallable:
    """Synchronous OpenAI-compatible callable backed by the LiteLLM proxy.

    Supports tool definitions in OpenAI function-calling format so the agent
    loop can dispatch read_file / write_file / run_tests / etc. through the
    gateway's tool-use flow without being tied to a single provider SDK.
    """

    def __init__(
        self, model: str | None = None, timeout: float = 120.0, temperature: float | None = None
    ) -> None:
        self.model = model or _default_model()
        self.timeout = timeout
        # A competing genome's sampling temperature; None = provider default.
        self.temperature = temperature

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
            "messages": _to_openai_messages(messages),
            "max_tokens": max_tokens,
        }
        # Only send temperature when set, so competing genome configs vary while
        # the default (no-temperature) path stays byte-identical to before.
        if self.temperature is not None:
            body["temperature"] = self.temperature
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
