"""Tests for ResponsesAPICallable and module-level helpers in responses_callable.py.

Dead-code note — _builder_tools() vs _builder_functions():
  _builder_tools() is a module-level function that returns tool dicts in a
  Responses-API-compatible shape (objects with a top-level "type" key).
  ResponsesAPICallable._builder_functions() is an instance method that returns
  bare function dicts (without a "type" wrapper) and is the one actually used
  by create() when building the tools list for the chat-completions call.

  A grep of the full codebase confirms that _builder_tools() is referenced only
  inside responses_callable.py — defined once and called once in __init__ to
  populate self._tools.  self._tools is assigned but never read anywhere in the
  class; create() and __call__() both call self._builder_functions() directly.
  No other module imports or calls _builder_tools().

  Conclusion: _builder_tools() is DEAD CODE.  It builds self._tools on every
  instantiation, but that attribute is never consumed by any code path.
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any

import pytest

from maistro_bootstrap.builders import responses_callable as rc
from maistro_bootstrap.builders.actions import SUPPORTED_ACTIONS
from maistro_bootstrap.builders.responses_callable import (
    DEFAULT_LITELLM_URL,
    ResponsesAPICallable,
    _builder_tools,
    _detect_api_key,
    _detect_base_url,
)

# ---------------------------------------------------------------------------
# _detect_base_url()
# ---------------------------------------------------------------------------


class TestDetectBaseUrl:
    def test_returns_openai_base_url_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        assert _detect_base_url() == "https://api.openai.com/v1"

    def test_returns_litellm_base_url_when_openai_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm-host:4000/v1")
        assert _detect_base_url() == "http://litellm-host:4000/v1"

    def test_openai_base_url_takes_precedence_over_litellm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://openai-override/v1")
        monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm-host:4000/v1")
        assert _detect_base_url() == "https://openai-override/v1"

    def test_returns_default_litellm_url_when_no_env_vars_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        assert _detect_base_url() == DEFAULT_LITELLM_URL

    def test_default_litellm_url_constant_value(self) -> None:
        assert DEFAULT_LITELLM_URL == "http://localhost:4000/v1"


# Backwards-compatible flat tests for the same function
def test_detect_base_url_prefers_openai_then_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example/v1")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://litellm.example/v1")
    assert rc._detect_base_url() == "https://openai.example/v1"

    monkeypatch.delenv("OPENAI_BASE_URL")
    assert rc._detect_base_url() == "https://litellm.example/v1"

    monkeypatch.delenv("LITELLM_BASE_URL")
    assert rc._detect_base_url() == rc.DEFAULT_LITELLM_URL


# ---------------------------------------------------------------------------
# _detect_api_key()
# ---------------------------------------------------------------------------


class TestDetectApiKey:
    def test_returns_litellm_master_key_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-secret")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert _detect_api_key() == "sk-master-secret"

    def test_returns_openai_api_key_when_litellm_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-key")
        assert _detect_api_key() == "sk-openai-key"

    def test_litellm_master_key_takes_precedence_over_openai_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-master-wins")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-loses")
        assert _detect_api_key() == "sk-master-wins"

    def test_returns_placeholder_when_no_key_env_vars_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert _detect_api_key() == "sk-no-key-set"


# Backwards-compatible flat test for the same function
def test_detect_api_key_prefers_litellm_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert rc._detect_api_key() == "sk-no-key-set"

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert rc._detect_api_key() == "sk-openai"

    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-litellm")
    assert rc._detect_api_key() == "sk-litellm"


# ---------------------------------------------------------------------------
# _builder_tools()  — module-level function (dead code, see module docstring)
# ---------------------------------------------------------------------------


class TestBuilderToolsFunction:
    def test_returns_a_list(self) -> None:
        result = _builder_tools()
        assert isinstance(result, list)

    def test_list_is_non_empty(self) -> None:
        assert len(_builder_tools()) > 0

    def test_each_entry_has_type_function(self) -> None:
        for tool in _builder_tools():
            assert tool.get("type") == "function", (
                f"Expected type='function', got {tool.get('type')!r}"
            )

    def test_builder_action_tool_is_present(self) -> None:
        names = [t.get("name") for t in _builder_tools()]
        assert "builder_action" in names

    def test_action_enum_matches_supported_actions(self) -> None:
        tools = _builder_tools()
        builder_tool = next(t for t in tools if t.get("name") == "builder_action")
        enum_values = builder_tool["parameters"]["properties"]["action"]["enum"]
        assert set(enum_values) == set(SUPPORTED_ACTIONS)

    def test_action_is_required_parameter(self) -> None:
        tools = _builder_tools()
        builder_tool = next(t for t in tools if t.get("name") == "builder_action")
        assert "action" in builder_tool["parameters"]["required"]


# ---------------------------------------------------------------------------
# ResponsesAPICallable.__init__()
# ---------------------------------------------------------------------------


class TestResponsesAPICallableInit:
    def test_stores_explicit_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        callable_ = ResponsesAPICallable(api_key="sk-explicit", base_url="http://x/v1")
        assert callable_._api_key == "sk-explicit"

    def test_stores_explicit_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        callable_ = ResponsesAPICallable(api_key="k", base_url="http://custom-host/v1")
        assert callable_._base_url == "http://custom-host/v1"

    def test_detects_api_key_from_env_when_not_supplied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-from-env")
        callable_ = ResponsesAPICallable()
        assert callable_._api_key == "sk-from-env"

    def test_detects_base_url_from_env_when_not_supplied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "http://env-url/v1")
        callable_ = ResponsesAPICallable()
        assert callable_._base_url == "http://env-url/v1"

    def test_defaults_to_placeholder_key_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        callable_ = ResponsesAPICallable()
        assert callable_._api_key == "sk-no-key-set"

    def test_defaults_to_litellm_proxy_url_when_no_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        callable_ = ResponsesAPICallable()
        assert callable_._base_url == DEFAULT_LITELLM_URL

    def test_previous_response_id_starts_as_none(self) -> None:
        callable_ = ResponsesAPICallable(api_key="k", base_url="http://x/v1")
        assert callable_._previous_response_id is None

    def test_builder_functions_non_empty_at_runtime(self) -> None:
        # _builder_functions() is the live instance method used by create/call.
        callable_ = ResponsesAPICallable(api_key="k", base_url="http://x/v1")
        tools = callable_._builder_functions()
        assert isinstance(tools, list)
        assert len(tools) > 0


# ---------------------------------------------------------------------------
# ResponsesAPICallable.previous_response_id property
# ---------------------------------------------------------------------------


class TestPreviousResponseIdProperty:
    def test_returns_none_initially(self) -> None:
        callable_ = ResponsesAPICallable(api_key="k", base_url="http://x/v1")
        assert callable_.previous_response_id is None

    def test_reflects_internal_value_after_set(self) -> None:
        callable_ = ResponsesAPICallable(api_key="k", base_url="http://x/v1")
        callable_._previous_response_id = "resp-abc123"
        assert callable_.previous_response_id == "resp-abc123"


# ---------------------------------------------------------------------------
# ResponsesAPICallable.reset_conversation()
# ---------------------------------------------------------------------------


class TestResetConversation:
    def test_clears_previous_response_id(self) -> None:
        callable_ = ResponsesAPICallable(api_key="k", base_url="http://x/v1")
        callable_._previous_response_id = "resp-to-clear"
        callable_.reset_conversation()
        assert callable_.previous_response_id is None

    def test_idempotent_when_already_none(self) -> None:
        callable_ = ResponsesAPICallable(api_key="k", base_url="http://x/v1")
        callable_.reset_conversation()
        assert callable_.previous_response_id is None


# Backwards-compatible flat test for the same function
def test_reset_conversation_clears_previous_response_id() -> None:
    callable_ = rc.ResponsesAPICallable(api_key="key", base_url="http://proxy")
    callable_._previous_response_id = "resp_123"
    callable_.reset_conversation()
    assert callable_.previous_response_id is None


# ---------------------------------------------------------------------------
# _builder_functions() instance method
# ---------------------------------------------------------------------------


def test_builder_function_schema_lists_supported_actions() -> None:
    callable_ = rc.ResponsesAPICallable(api_key="key", base_url="http://proxy")

    functions = callable_._builder_functions()

    assert functions[0]["name"] == "builder_action"
    action_enum = functions[0]["parameters"]["properties"]["action"]["enum"]
    assert action_enum == sorted(rc.SUPPORTED_ACTIONS)
    assert "run_command" in action_enum


# ---------------------------------------------------------------------------
# ResponsesAPICallable.__call__() — via fake create()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_converts_first_tool_call_to_json_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callable_ = rc.ResponsesAPICallable(api_key="key", base_url="http://proxy")

    async def fake_create(model: str, instructions: str, input_text: str) -> dict[str, Any]:
        assert model == "maistro-tier-2"
        assert instructions == "system prompt"
        assert "user prompt" in input_text
        return {
            "tool_calls": [
                {
                    "name": "builder_action",
                    "arguments": json.dumps({"action": "read_file", "args": {"path": "README.md"}}),
                }
            ],
            "text_output": "",
            "tokens": 17,
            "response_id": "resp_1",
        }

    monkeypatch.setattr(callable_, "create", fake_create)

    result = await callable_(
        "maistro-tier-2",
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ],
    )

    assert json.loads(result["content"]) == {
        "action": "read_file",
        "args": {"path": "README.md"},
    }
    assert result["tokens"] == 17


@pytest.mark.asyncio
async def test_call_returns_text_output_when_no_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    callable_ = rc.ResponsesAPICallable(api_key="key", base_url="http://proxy")

    async def fake_create(model: str, instructions: str, input_text: str) -> dict[str, Any]:
        return {
            "tool_calls": [],
            "text_output": '{"action": "summarize", "args": {}}',
            "tokens": 5,
            "response_id": "resp_2",
        }

    monkeypatch.setattr(callable_, "create", fake_create)

    result = await callable_("model", [{"role": "user", "content": "prompt"}])

    assert result == {"content": '{"action": "summarize", "args": {}}', "tokens": 5}


@pytest.mark.asyncio
async def test_call_returns_dict_with_content_and_tokens_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callable_ = rc.ResponsesAPICallable(api_key="key", base_url="http://proxy")

    async def fake_create(model: str, instructions: str, input_text: str) -> dict[str, Any]:
        return {"tool_calls": [], "text_output": "hi", "tokens": 1, "response_id": "r"}

    monkeypatch.setattr(callable_, "create", fake_create)
    result = await callable_("m", [{"role": "user", "content": "hi"}])
    assert "content" in result
    assert "tokens" in result


@pytest.mark.asyncio
async def test_call_passes_model_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    callable_ = rc.ResponsesAPICallable(api_key="key", base_url="http://proxy")
    seen: dict[str, Any] = {}

    async def fake_create(model: str, instructions: str, input_text: str) -> dict[str, Any]:
        seen["model"] = model
        return {"tool_calls": [], "text_output": "", "tokens": 0, "response_id": "r"}

    monkeypatch.setattr(callable_, "create", fake_create)
    await callable_("mistral-7b", [{"role": "user", "content": "x"}])
    assert seen["model"] == "mistral-7b"


@pytest.mark.asyncio
async def test_call_joins_multiple_user_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    callable_ = rc.ResponsesAPICallable(api_key="key", base_url="http://proxy")
    seen: dict[str, Any] = {}

    async def fake_create(model: str, instructions: str, input_text: str) -> dict[str, Any]:
        seen["input_text"] = input_text
        return {"tool_calls": [], "text_output": "", "tokens": 0, "response_id": "r"}

    monkeypatch.setattr(callable_, "create", fake_create)
    await callable_(
        "m",
        [
            {"role": "user", "content": "Part one."},
            {"role": "user", "content": "Part two."},
        ],
    )
    assert "Part one." in seen["input_text"]
    assert "Part two." in seen["input_text"]


# ---------------------------------------------------------------------------
# ResponsesAPICallable.create() — via fake OpenAI module
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_adapts_openai_chat_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeUsage:
        total_tokens = 23

    class FakeFunction:
        name = "builder_action"
        arguments = '{"action": "search", "args": {"query": "needle"}}'

    class FakeToolCall:
        function = FakeFunction()

    class FakeMessage:
        def __init__(self) -> None:
            self.tool_calls = [FakeToolCall()]
            self.content = "ignored text"

    class FakeChoice:
        def __init__(self) -> None:
            self.message = FakeMessage()

    class FakeResponse:
        def __init__(self) -> None:
            self.id = "resp_fake"
            self.usage = FakeUsage()
            self.choices = [FakeChoice()]

    class FakeCompletions:
        async def create(self, **kwargs: Any) -> FakeResponse:
            captured.update(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            self.chat = FakeChat()

    class ChatCompletionSystemMessageParam(dict[str, str]):
        pass

    class ChatCompletionUserMessageParam(dict[str, str]):
        pass

    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI  # type: ignore[attr-defined]
    fake_types = types.ModuleType("openai.types")
    fake_chat = types.ModuleType("openai.types.chat")
    fake_chat.ChatCompletionSystemMessageParam = ChatCompletionSystemMessageParam  # type: ignore[attr-defined]
    fake_chat.ChatCompletionUserMessageParam = ChatCompletionUserMessageParam  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setitem(sys.modules, "openai.types", fake_types)
    monkeypatch.setitem(sys.modules, "openai.types.chat", fake_chat)

    callable_ = rc.ResponsesAPICallable(
        api_key="sk-test",
        base_url="http://proxy/v1",
        max_output_tokens=99,
        temperature=0.4,
    )
    result = await callable_.create("maistro-tier-2", "instructions", "input")

    assert captured["api_key"] == "sk-test"
    assert captured["base_url"] == "http://proxy/v1"
    assert captured["model"] == "maistro-tier-2"
    assert captured["max_tokens"] == 99
    assert captured["temperature"] == 0.4
    assert captured["messages"] == [
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": "input"},
    ]
    assert captured["tools"][0]["type"] == "function"
    assert result == {
        "tool_calls": [
            {
                "name": "builder_action",
                "arguments": '{"action": "search", "args": {"query": "needle"}}',
            }
        ],
        "text_output": "ignored text",
        "tokens": 23,
        "response_id": "resp_fake",
    }


@pytest.mark.asyncio
async def test_create_omits_system_message_when_instructions_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeUsage:
        total_tokens = 5

    class FakeMessage:
        def __init__(self) -> None:
            self.tool_calls = []
            self.content = "ok"

    class FakeChoice:
        def __init__(self) -> None:
            self.message = FakeMessage()

    class FakeResponse:
        def __init__(self) -> None:
            self.id = "r"
            self.usage = FakeUsage()
            self.choices = [FakeChoice()]

    class FakeCompletions:
        async def create(self, **kwargs: Any) -> FakeResponse:
            captured.update(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            self.chat = FakeChat()

    class ChatCompletionSystemMessageParam(dict[str, str]):
        pass

    class ChatCompletionUserMessageParam(dict[str, str]):
        pass

    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI  # type: ignore[attr-defined]
    fake_types = types.ModuleType("openai.types")
    fake_chat_mod = types.ModuleType("openai.types.chat")
    fake_chat_mod.ChatCompletionSystemMessageParam = ChatCompletionSystemMessageParam  # type: ignore[attr-defined]
    fake_chat_mod.ChatCompletionUserMessageParam = ChatCompletionUserMessageParam  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setitem(sys.modules, "openai.types", fake_types)
    monkeypatch.setitem(sys.modules, "openai.types.chat", fake_chat_mod)

    callable_ = rc.ResponsesAPICallable(api_key="sk-test", base_url="http://proxy/v1")
    await callable_.create("gpt-4o", "", "User-only message.")

    roles = [m["role"] for m in captured["messages"]]
    assert "system" not in roles
    assert "user" in roles


@pytest.mark.asyncio
async def test_create_returns_zero_tokens_when_usage_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMessage:
        def __init__(self) -> None:
            self.tool_calls = []
            self.content = "ok"

    class FakeChoice:
        def __init__(self) -> None:
            self.message = FakeMessage()

    class FakeResponse:
        def __init__(self) -> None:
            self.id = "r"
            self.usage = None
            self.choices = [FakeChoice()]

    class FakeCompletions:
        async def create(self, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            self.chat = FakeChat()

    class ChatCompletionSystemMessageParam(dict[str, str]):
        pass

    class ChatCompletionUserMessageParam(dict[str, str]):
        pass

    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI  # type: ignore[attr-defined]
    fake_types = types.ModuleType("openai.types")
    fake_chat_mod = types.ModuleType("openai.types.chat")
    fake_chat_mod.ChatCompletionSystemMessageParam = ChatCompletionSystemMessageParam  # type: ignore[attr-defined]
    fake_chat_mod.ChatCompletionUserMessageParam = ChatCompletionUserMessageParam  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setitem(sys.modules, "openai.types", fake_types)
    monkeypatch.setitem(sys.modules, "openai.types.chat", fake_chat_mod)

    callable_ = rc.ResponsesAPICallable(api_key="sk-test", base_url="http://proxy/v1")
    result = await callable_.create("gpt-4o", "", "No usage.")
    assert result["tokens"] == 0
