from __future__ import annotations

from typing import Any

from maistro.capabilities.providers.host_health import HostHealthMonitor


class FakeHttp:
    def __init__(self, payload: dict[str, Any] | None, raise_exc: bool = False) -> None:
        self._payload, self._raise = payload, raise_exc

    async def get_json(self, path: str) -> dict[str, Any]:
        if self._raise:
            raise ConnectionError("unreachable")
        assert path == "/full"
        return self._payload or {}

    async def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return {}


async def test_snapshot_maps_sections():
    http = FakeHttp({
        "timestamp": "2026-05-30T00:00:00Z",
        "gpu": {"ok": True},
        "storage": {"ok": True},
        "docker": {"unhealthy": []},
        "vms": [],
        "services": {},
    })
    mon = HostHealthMonitor(http=http)
    health = await mon.snapshot()
    assert set(health.resources) == {"gpu", "storage", "docker", "vms", "services"}
    assert health.ts == "2026-05-30T00:00:00Z"


async def test_snapshot_unreachable_marks_down_not_raises():
    mon = HostHealthMonitor(http=FakeHttp(None, raise_exc=True))
    health = await mon.snapshot()
    assert all(r.status == "down" for r in health.resources.values())
