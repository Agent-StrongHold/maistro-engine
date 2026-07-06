"""/v1/harness API: inbound harness-session routes (SPEC-208 §5)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import routes.harness as harness_mod
from services.engine import get_engine

from maistro.capabilities import HarnessSessionManager
from maistro.capabilities.slots.harness_runner import SLOT_NAME
from maistro.capabilities.types import ProviderHealth
from maistro.security._types import WardenVerdict


class _FakeHarness:
    def __init__(self, *, healthy: bool = True) -> None:
        self._healthy = healthy

    @property
    def name(self) -> str:
        return "fake"

    @property
    def slot(self) -> str:
        return SLOT_NAME

    @property
    def trust_tier(self) -> str:
        return "t2"

    def requires(self) -> tuple[str, ...]:
        return ()

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(healthy=self._healthy)

    async def start_session(self, agent_spec: Any, *, workdir: str) -> str:
        return "sess-http"

    async def send(self, session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"role": "assistant", "content": "pong", "actions": []}

    async def stream(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "token", "text": "hi"}

    async def stop(self, session_id: str) -> None:
        return None


class _StubWarden:
    def __init__(self, block_on: str | None = None) -> None:
        self.block_on = block_on

    async def scan(self, content: str, boundary: str) -> WardenVerdict:
        if self.block_on is not None and self.block_on in content:
            return WardenVerdict(clean=False, blocked=True, flags=("injection",))
        return WardenVerdict(clean=True)


def _install_harness(*, warden: Any, healthy: bool = True, enabled: bool = True) -> None:
    reg = get_engine().capabilities
    reg.register(_FakeHarness(healthy=healthy))
    reg.activate(SLOT_NAME, "fake")
    reg.set_enabled(SLOT_NAME, enabled)
    harness_mod._manager = HarnessSessionManager(reg, warden=warden)


def test_start_returns_503_when_no_active_harness(authed_client):
    reg = get_engine().capabilities
    reg.set_enabled(SLOT_NAME, False)  # force SAFE_NOOP fallback
    harness_mod._manager = HarnessSessionManager(reg, warden=_StubWarden())
    try:
        r = authed_client.post("/v1/harness/sessions", json={"description": "x"})
        assert r.status_code == 503
    finally:
        reg.set_enabled(SLOT_NAME, True)


def test_full_session_lifecycle(authed_client):
    _install_harness(warden=_StubWarden(block_on="EVIL"))

    r = authed_client.post("/v1/harness/sessions", json={"description": "do it", "role": "coder"})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    assert sid == "sess-http"

    r = authed_client.post(
        f"/v1/harness/sessions/{sid}/send",
        json={"messages": [{"role": "user", "content": "ping"}]},
    )
    assert r.status_code == 200 and r.json()["content"] == "pong"

    # Warden refuses a malicious payload → 400.
    r = authed_client.post(
        f"/v1/harness/sessions/{sid}/send",
        json={"messages": [{"role": "user", "content": "do EVIL"}]},
    )
    assert r.status_code == 400 and "warden" in r.json()["detail"]

    # SSE stream yields the harness event then closes.
    r = authed_client.get(f"/v1/harness/sessions/{sid}/stream")
    assert r.status_code == 200 and "hi" in r.text

    r = authed_client.delete(f"/v1/harness/sessions/{sid}")
    assert r.status_code == 200 and r.json()["stopped"] is True


def test_send_unknown_session_returns_404(authed_client):
    _install_harness(warden=_StubWarden())
    r = authed_client.post("/v1/harness/sessions/ghost/send", json={"messages": []})
    assert r.status_code == 404
