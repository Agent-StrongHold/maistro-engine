"""Capability framework: slots, providers, registry, discovery (SPEC-184)."""

from __future__ import annotations

from maistro.capabilities.discovery import discover_into
from maistro.capabilities.protocols import CapabilityProvider
from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.types import (
    FallbackPolicy,
    ProviderHealth,
    SlotSpec,
    Unavailable,
)

__all__ = [
    "CapabilityProvider",
    "CapabilityRegistry",
    "FallbackPolicy",
    "ProviderHealth",
    "SlotSpec",
    "Unavailable",
    "discover_into",
]
