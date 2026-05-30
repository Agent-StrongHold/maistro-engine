"""infra_monitor + infra_action slot types and protocols (SPEC-187)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from maistro.capabilities.protocols import CapabilityProvider


class ActionTier(StrEnum):
    READ = "read"
    REVERSIBLE = "reversible"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ResourceHealth:
    status: str  # "ok" | "degraded" | "down"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InfraHealth:
    ts: str
    resources: dict[str, ResourceHealth] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    detail: str = ""
    blocked_pending_approval: bool = False


@runtime_checkable
class InfraMonitor(CapabilityProvider, Protocol):
    async def snapshot(self) -> InfraHealth: ...


@runtime_checkable
class InfraAction(CapabilityProvider, Protocol):
    def allowed_actions(self) -> tuple[str, ...]: ...
    async def act(self, action: str, params: dict[str, Any]) -> ActionResult: ...
