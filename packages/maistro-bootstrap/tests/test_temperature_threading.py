"""SPEC-070126-9d37 AC-2: temperature threading into the gateway request.

A competing genome's temperature must reach the provider. LiteLLMCallable sends
`temperature` in the chat-completions body iff it is set; a None temperature
never adds the key (provider default), so the no-temperature path is unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest

import maistro_bootstrap.builders.responses_callable as rc
from maistro_bootstrap.builders.responses_callable import LiteLLMCallable


class _FakeResp:
    status_code = 200
    text = ""

    def json(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }


def _capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv("LITELLM_URL", "http://gw:4000")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, json: dict[str, Any], headers: Any, timeout: Any) -> _FakeResp:
        captured.update(json)
        return _FakeResp()

    monkeypatch.setattr(rc.httpx, "post", fake_post)
    return captured


@pytest.mark.ac("SPEC-070126-9d37/AC-2")
def test_temperature_present_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture(monkeypatch)
    LiteLLMCallable(model="m", temperature=0.25)([{"role": "user", "content": "hi"}])
    assert captured["temperature"] == 0.25


@pytest.mark.ac("SPEC-070126-9d37/AC-2")
def test_temperature_absent_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture(monkeypatch)
    LiteLLMCallable(model="m")([{"role": "user", "content": "hi"}])
    assert "temperature" not in captured


def test_temperature_is_stored_for_forwarding() -> None:
    assert LiteLLMCallable(model="m", temperature=0.7).temperature == 0.7
    assert LiteLLMCallable(model="m").temperature is None
