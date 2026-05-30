"""Providers backed by the host-health API (:8150) — monitor + action (SPEC-187)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from maistro.capabilities.slots.infra import InfraHealth, ResourceHealth
from maistro.capabilities.types import ProviderHealth

if TYPE_CHECKING:
    from maistro.capabilities.http import AsyncHttp

logger = logging.getLogger("maistro.capabilities.host_health")

_SECTIONS = ("gpu", "storage", "docker", "vms", "services")


class HostHealthMonitor:
    """infra_monitor provider: GET /full -> normalized InfraHealth."""

    def __init__(self, http: AsyncHttp) -> None:
        self._http = http

    @property
    def name(self) -> str:
        return "host_health"

    @property
    def slot(self) -> str:
        return "infra_monitor"

    @property
    def trust_tier(self) -> str:
        return "t0"

    def requires(self) -> tuple[str, ...]:
        return ("HOST_HEALTH_URL", "HOST_HEALTH_TOKEN")

    async def healthcheck(self) -> ProviderHealth:
        try:
            await self._http.get_json("/health")
            return ProviderHealth(healthy=True)
        except Exception as exc:
            return ProviderHealth(healthy=False, detail=str(exc))

    async def snapshot(self) -> InfraHealth:
        try:
            data = await self._http.get_json("/full")
        except Exception as exc:
            logger.warning("host-health /full unreachable: %s", exc)
            return InfraHealth(
                ts="",
                resources={s: ResourceHealth(status="down", detail={}) for s in _SECTIONS},
            )
        return InfraHealth(
            ts=str(data.get("timestamp", "")),
            resources={
                s: ResourceHealth(status="ok", detail=_as_dict(data.get(s)))
                for s in _SECTIONS
            },
        )


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {"value": value}
