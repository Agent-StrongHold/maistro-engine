"""Capability framework: slots, providers, registry, discovery (SPEC-184)."""

from __future__ import annotations

from maistro.capabilities.bootstrap import default_capability_registry
from maistro.capabilities.discovery import discover_into
from maistro.capabilities.http import AsyncHttp
from maistro.capabilities.http_client import HttpxAsyncHttp
from maistro.capabilities.protocols import CapabilityProvider
from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.types import (
    FallbackPolicy,
    ProviderHealth,
    SlotSpec,
    Unavailable,
)

__all__ = [
    "AsyncHttp",
    "CapabilityProvider",
    "CapabilityRegistry",
    "FallbackPolicy",
    "HttpxAsyncHttp",
    "ProviderHealth",
    "SlotSpec",
    "Unavailable",
    "default_capability_registry",
    "discover_into",
]
