"""Capability framework: slots, providers, registry, discovery (SPEC-184)."""

from __future__ import annotations

from maistro.capabilities.bootstrap import default_capability_registry
from maistro.capabilities.discovery import discover_into
from maistro.capabilities.http import AsyncHttp
from maistro.capabilities.http_client import HttpxAsyncHttp
from maistro.capabilities.protocols import CapabilityProvider, HarnessRunner
from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.slots.harness import (
    HARNESS_RUNNER_SLOT,
    GuardedHarnessRunner,
    resolve_harness_runner,
)
from maistro.capabilities.types import (
    FallbackPolicy,
    ProviderHealth,
    SlotSpec,
    Unavailable,
)

__all__ = [
    "HARNESS_RUNNER_SLOT",
    "AsyncHttp",
    "CapabilityProvider",
    "CapabilityRegistry",
    "FallbackPolicy",
    "GuardedHarnessRunner",
    "HarnessRunner",
    "HttpxAsyncHttp",
    "ProviderHealth",
    "SlotSpec",
    "Unavailable",
    "default_capability_registry",
    "discover_into",
    "resolve_harness_runner",
]
