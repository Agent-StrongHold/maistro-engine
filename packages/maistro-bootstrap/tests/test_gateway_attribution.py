"""Gateway attribution + cache bypass in LiteLLMCallable.

Every proxy response carries LiteLLM attribution headers (which deployment
served the call, failover hops, cost, remaining headroom); the callable must
surface them so calibration can learn per-carrier truth while callers keep
addressing model groups. RSI/evolve set MAISTRO_LLM_NO_CACHE=1 so the
gateway's Redis response cache never feeds identical completions to competing
genome variants; regular work leaves it unset and caches.
"""

from __future__ import annotations

from typing import Any

import pytest

import maistro_bootstrap.builders.responses_callable as rc
from maistro_bootstrap.builders.responses_callable import LiteLLMCallable


class _FakeResp:
    status_code = 200
    text = ""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }


def _capture(
    monkeypatch: pytest.MonkeyPatch, resp_headers: dict[str, str] | None = None
) -> dict[str, Any]:
    monkeypatch.setenv("LITELLM_URL", "http://gw:4000")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, json: dict[str, Any], headers: Any, timeout: Any) -> _FakeResp:
        captured.update(json)
        return _FakeResp(resp_headers)

    monkeypatch.setattr(rc.httpx, "post", fake_post)
    return captured


def test_gateway_headers_surface_in_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture(
        monkeypatch,
        resp_headers={
            "x-litellm-model-id": "dep-abc123",
            "x-litellm-model-group": "code",
            "x-litellm-attempted-fallbacks": "1",
            "x-litellm-response-cost": "0.0021",
            "x-ratelimit-remaining-requests": "17",
        },
    )
    result = LiteLLMCallable(model="code")([{"role": "user", "content": "hi"}])
    assert result["gateway"] == {
        "model_id": "dep-abc123",
        "model_group": "code",
        "attempted_fallbacks": "1",
        "response_cost": "0.0021",
        "remaining_requests": "17",
    }


def test_gateway_key_empty_when_headers_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # A gateway that returns no attribution headers (or a non-LiteLLM endpoint)
    # must still yield the key, empty — consumers never need hasattr checks.
    _capture(monkeypatch)
    result = LiteLLMCallable(model="m")([{"role": "user", "content": "hi"}])
    assert result["gateway"] == {}


def test_no_cache_env_sends_cache_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAISTRO_LLM_NO_CACHE", "1")
    captured = _capture(monkeypatch)
    LiteLLMCallable(model="m")([{"role": "user", "content": "hi"}])
    assert captured["cache"] == {"no-cache": True, "no-store": True}


def test_cache_body_absent_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAISTRO_LLM_NO_CACHE", raising=False)
    captured = _capture(monkeypatch)
    LiteLLMCallable(model="m")([{"role": "user", "content": "hi"}])
    # Regular work must keep the byte-identical default body — cache opt-out is
    # strictly additive for RSI/evolve.
    assert "cache" not in captured


def test_explicit_no_cache_param_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAISTRO_LLM_NO_CACHE", "1")
    captured = _capture(monkeypatch)
    LiteLLMCallable(model="m", no_cache=False)([{"role": "user", "content": "hi"}])
    assert "cache" not in captured
