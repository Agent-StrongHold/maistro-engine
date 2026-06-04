"""OpenAI Responses API callable for the builder agent loop.

Routes through the LiteLLM proxy (localhost:4000) by default, which provides
access to all configured providers (Mistral, Gemini, Cloudflare, Cerebras,
Groq, SambaNova, DeepSeek, Cohere, Together, OpenRouter, Zhipu, etc.).

Falls back to direct OpenAI if no proxy is detected.
"""

from __future__ import annotations

import os
from typing import Any

from maistro_bootstrap.builders.actions import SUPPORTED_ACTIONS

DEFAULT_LITELLM_URL = "http://localhost:4000/v1"
DEFAULT_LITELLM_KEY_ENV = "LITELLM_MASTER_KEY"


def _detect_base_url() -> str:
    if os.environ.get("OPENAI_BASE_URL"):
        return os.environ["OPENAI_BASE_URL"]
    if os.environ.get("LITELLM_BASE_URL"):
        return os.environ["LITELLM_BASE_URL"]
    return DEFAULT_LITELLM_URL


def _detect_api_key() -> str:
    for env_var in (
        DEFAULT_LITELLM_KEY_ENV,
        "LITELLM_MASTER_KEY",
        "OPENAI_API_KEY",
    ):
        value = os.environ.get(env_var)
        if value:
            return value
    return "sk-no-key-set"


def _builder_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "builder_action",
            "description": (
                "Execute a builder action. Available actions: "
                + ", ".join(sorted(SUPPORTED_ACTIONS))
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": sorted(SUPPORTED_ACTIONS),
                        "description": "The builder action to execute",
                    },
                    "args": {
                        "type": "object",
                        "description": "Action arguments.",
                        "properties": {
                            "path": {"type": "string"},
                            "query": {"type": "string"},
                            "content": {"type": "string"},
                            "argv": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "timeout": {"type": "number"},
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "acceptance_criteria": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "card_id": {"type": "string"},
                            "body": {"type": "string"},
                            "agent": {"type": "string"},
                            "question": {"type": "string"},
                            "owner": {"type": "string"},
                        },
                    },
                },
                "required": ["action"],
            },
        }
    ]


class ResponsesAPICallable:
    """Stateful LLM callable routing through LiteLLM proxy.

    Defaults to http://localhost:4000/v1 (the LiteLLM proxy).
    Uses OpenAI Chat Completions API with native function calling,
    which LiteLLM proxies to the correct provider.
    """

    def __init__(
        self,
        *,
        max_output_tokens: int = 2048,
        temperature: float = 0.2,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._api_key = api_key or _detect_api_key()
        self._base_url = base_url or _detect_base_url()
        self._previous_response_id: str | None = None

    @property
    def previous_response_id(self) -> str | None:
        return self._previous_response_id

    def reset_conversation(self) -> None:
        self._previous_response_id = None

    async def create(
        self,
        model: str,
        instructions: str,
        input_text: str,
    ) -> dict[str, Any]:
        """Create a chat completion with native tool definitions.

        Returns:
            dict with keys:
                - tool_calls: list of parsed tool call dicts {name, arguments}
                - text_output: any non-tool-call text content
                - tokens: total tokens used
                - response_id: response ID for stateful continuation
        """
        from openai import AsyncOpenAI
        from openai.types.chat import (
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
        )

        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

        messages: list[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam] = []
        if instructions:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=instructions))
        messages.append(ChatCompletionUserMessageParam(role="user", content=input_text))

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[{"type": "function", "function": t} for t in self._builder_functions()],  # type: ignore[typeddict-item]
            max_tokens=self._max_output_tokens,
            temperature=self._temperature,
        )

        choice = response.choices[0]
        tool_calls_out: list[dict[str, Any]] = []
        text_parts: list[str] = []
        tokens = response.usage.total_tokens if response.usage else 0

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                func = getattr(tc, "function", None)
                if func is None:
                    continue
                tool_calls_out.append(
                    {
                        "name": func.name,
                        "arguments": func.arguments,
                    }
                )

        if choice.message.content:
            text_parts.append(choice.message.content)

        return {
            "tool_calls": tool_calls_out,
            "text_output": "\n".join(text_parts),
            "tokens": tokens,
            "response_id": response.id,
        }

    def _builder_functions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "builder_action",
                "description": (
                    "Execute a builder action. Available actions: "
                    + ", ".join(sorted(SUPPORTED_ACTIONS))
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": sorted(SUPPORTED_ACTIONS),
                            "description": "The builder action to execute",
                        },
                        "args": {
                            "type": "object",
                            "description": "Action arguments.",
                            "properties": {
                                "path": {"type": "string"},
                                "query": {"type": "string"},
                                "content": {"type": "string"},
                                "argv": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "timeout": {"type": "number"},
                                "title": {"type": "string"},
                                "summary": {"type": "string"},
                                "acceptance_criteria": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "card_id": {"type": "string"},
                                "body": {"type": "string"},
                                "agent": {"type": "string"},
                                "question": {"type": "string"},
                                "owner": {"type": "string"},
                            },
                        },
                    },
                    "required": ["action"],
                },
            }
        ]

    async def __call__(self, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Backward-compatible interface for TurnRunner's _call_llm."""
        instructions = ""
        input_parts: list[str] = []
        for msg in messages:
            if msg["role"] == "system":
                instructions = msg["content"]
            else:
                input_parts.append(msg["content"])

        result = await self.create(model, instructions, "\n\n".join(input_parts))

        if result["tool_calls"]:
            import json

            call = result["tool_calls"][0]
            parsed_args = json.loads(call["arguments"])
            content = json.dumps(
                {
                    "action": parsed_args.get("action", ""),
                    "args": parsed_args.get("args", {}),
                }
            )
            return {"content": content, "tokens": result["tokens"]}

        return {"content": result["text_output"], "tokens": result["tokens"]}
