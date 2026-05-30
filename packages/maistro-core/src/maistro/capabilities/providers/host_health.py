"""Providers backed by the host-health API (:8150) — monitor + action (SPEC-187)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from maistro.capabilities.slots.approval import ApprovalRequest
from maistro.capabilities.slots.infra import (
    ActionResult,
    ActionTier,
    InfraHealth,
    ResourceHealth,
    tier_for,
)
from maistro.capabilities.types import ProviderHealth

if TYPE_CHECKING:
    from maistro.capabilities.http import AsyncHttp
    from maistro.capabilities.slots.approval import Approval

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


_ALLOWED = (
    "restart_container", "restart_stack", "restart_service", "vm_control",
    "docker_logs", "docker_prune", "ollama_list", "ollama_pull", "snapraid_status",
)


class HostHealthAction:
    """infra_action provider: POST /action/{name}, tier-gated through approval."""

    def __init__(
        self,
        http: AsyncHttp,
        *,
        autonomy: Literal["approve_all", "auto_safe", "detect_only"] = "auto_safe",
        approval: Approval | None = None,
    ) -> None:
        self._http = http
        self._autonomy = autonomy
        self._approval = approval

    @property
    def name(self) -> str:
        return "host_health"

    @property
    def slot(self) -> str:
        return "infra_action"

    @property
    def trust_tier(self) -> str:
        return "t0"

    def requires(self) -> tuple[str, ...]:
        return ("HOST_HEALTH_URL", "HOST_HEALTH_TOKEN")

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(healthy=True)

    def allowed_actions(self) -> tuple[str, ...]:
        return _ALLOWED

    async def act(self, action: str, params: dict[str, Any]) -> ActionResult:
        if action not in _ALLOWED:
            return ActionResult(ok=False, detail=f"action '{action}' not in allowlist")

        tier = tier_for(action, params)

        if self._autonomy == "detect_only":
            return ActionResult(ok=False, detail="autonomy=detect_only: no actions executed")

        needs_approval = tier is ActionTier.DESTRUCTIVE or (
            tier is ActionTier.REVERSIBLE and self._autonomy != "auto_safe"
        )
        if needs_approval:
            if self._approval is None:
                return ActionResult(
                    ok=False, blocked_pending_approval=True,
                    detail="approval required but no approval provider",
                )
            decision = await self._approval.request(
                ApprovalRequest(action=action, params=params, tier=tier.value,
                                requester="infra_action", rationale="")
            )
            if not decision.approved:
                return ActionResult(ok=False, blocked_pending_approval=True, detail="approval denied")

        return await self._execute(action, params)

    async def _execute(self, action: str, params: dict[str, Any]) -> ActionResult:
        try:
            data = await self._http.post_json(f"/action/{action}", params)
        except Exception as exc:
            return ActionResult(ok=False, detail=str(exc))
        ok = str(data.get("status", "")).lower() != "error"
        return ActionResult(ok=ok, detail=str(data.get("detail", "")))
