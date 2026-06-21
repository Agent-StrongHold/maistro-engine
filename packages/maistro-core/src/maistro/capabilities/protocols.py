"""Capability provider protocol — base metadata + health for any slot implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from maistro.capabilities.types import ProviderHealth
from maistro.types.config import AgentConfig


@runtime_checkable
class CapabilityProvider(Protocol):
    """A swappable implementation that fills a capability slot.

    Concrete providers ALSO implement the slot-specific protocol
    (e.g. InfraMonitor), which adds the slot's domain methods.
    """

    @property
    def name(self) -> str: ...

    @property
    def slot(self) -> str: ...

    @property
    def trust_tier(self) -> str: ...

    def requires(self) -> tuple[str, ...]:
        """Env vars / service ids this provider needs to be usable."""
        ...

    async def healthcheck(self) -> ProviderHealth: ...


@runtime_checkable
class HarnessRunner(CapabilityProvider, Protocol):
    """Adapter over a foreign agent harness's session/process API."""

    async def start_session(self, agent_spec: AgentConfig, *, workdir: str) -> str:
        """Start or attach to a harness session and return its session id."""
        ...

    async def send(self, session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Send one turn to the harness and return the normalized response envelope."""
        ...

    def stream(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """Stream incremental harness events for a session."""
        ...

    async def stop(self, session_id: str) -> None:
        """Terminate the underlying process/session."""
        ...
