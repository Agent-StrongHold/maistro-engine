"""Capability registry: defines slots, registers providers (installed/inactive),
activates/enables them, and resolves the live provider with fallback. Thread-safe."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maistro.capabilities.types import SlotSpec

if TYPE_CHECKING:
    from maistro.capabilities.protocols import CapabilityProvider

logger = logging.getLogger("maistro.capabilities.registry")


@dataclass
class _SlotState:
    spec: SlotSpec
    providers: dict[str, CapabilityProvider] = field(default_factory=dict)
    active: str | None = None
    enabled: bool = True


class CapabilityRegistry:
    """Holds slot definitions + provider state. Thread-safe via reentrant lock."""

    def __init__(self) -> None:
        self._slots: dict[str, _SlotState] = {}
        self._lock = threading.RLock()

    def define(self, spec: SlotSpec) -> None:
        with self._lock:
            self._slots[spec.name] = _SlotState(spec=spec)
        logger.debug("Defined slot: %s (%s)", spec.name, spec.fallback_policy)

    def _slot(self, slot: str) -> _SlotState:
        state = self._slots.get(slot)
        if state is None:
            raise KeyError(f"Unknown slot '{slot}'")
        return state

    def register(self, provider: CapabilityProvider) -> None:
        """Register a provider as INSTALLED but INACTIVE (never auto-activates)."""
        with self._lock:
            state = self._slot(provider.slot)
            state.providers[provider.name] = provider
        logger.debug("Registered provider %s -> slot %s (inactive)", provider.name, provider.slot)

    def activate(self, slot: str, provider_name: str) -> None:
        with self._lock:
            state = self._slot(slot)
            if provider_name not in state.providers:
                raise KeyError(f"Provider '{provider_name}' not installed for slot '{slot}'")
            state.active = provider_name
        logger.info("Activated %s for slot %s", provider_name, slot)

    def set_enabled(self, slot: str, enabled: bool) -> None:
        with self._lock:
            self._slot(slot).enabled = enabled

    def is_enabled(self, slot: str) -> bool:
        return self._slot(slot).enabled

    def installed(self, slot: str) -> list[str]:
        return list(self._slot(slot).providers.keys())

    def active_name(self, slot: str) -> str | None:
        return self._slot(slot).active
