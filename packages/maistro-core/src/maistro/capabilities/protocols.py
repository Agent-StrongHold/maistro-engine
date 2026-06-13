"""Capability provider protocol — base metadata + health for any slot implementation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from maistro.capabilities.types import ProviderHealth


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
