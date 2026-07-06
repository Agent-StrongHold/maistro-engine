"""Capability framework: slots, providers, registry, discovery (SPEC-184)."""

from __future__ import annotations

from maistro.capabilities.bootstrap import default_capability_registry
from maistro.capabilities.discovery import discover_into
from maistro.capabilities.harness_manager import HarnessSessionManager
from maistro.capabilities.http import AsyncHttp
from maistro.capabilities.http_client import HttpxAsyncHttp
from maistro.capabilities.protocols import CapabilityProvider, HarnessRunner
from maistro.capabilities.providers.harness_safety import (
    ActionGate,
    AllowAllGate,
    SafeHarnessRunner,
)
from maistro.capabilities.providers.opencode import (
    OpencodeHarnessRunner,
    opencode_microvm_factory,
    opencode_microvm_runner,
)
from maistro.capabilities.providers.subprocess_harness import (
    SandboxExec,
    SubprocessHarnessRunner,
)
from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.slots.harness_runner import (
    SLOT_NAME as HARNESS_RUNNER_SLOT,
    GuardedHarnessRunner,
    resolve_harness_runner,
)
from maistro.capabilities.slots.harness_runner import (
    HarnessInputBlocked,
    HarnessRunner,
)
from maistro.capabilities.types import (
    FallbackPolicy,
    ProviderHealth,
    SlotSpec,
    Unavailable,
)

__all__ = [
    "HARNESS_RUNNER_SLOT",
    "ActionGate",
    "AllowAllGate",
    "AsyncHttp",
    "CapabilityProvider",
    "CapabilityRegistry",
    "FallbackPolicy",
    "HarnessInputBlocked",
    "HarnessSessionManager",
    "GuardedHarnessRunner",
    "HarnessRunner",
    "HttpxAsyncHttp",
    "OpencodeHarnessRunner",
    "ProviderHealth",
    "SafeHarnessRunner",
    "SandboxExec",
    "SlotSpec",
    "SubprocessHarnessRunner",
    "Unavailable",
    "default_capability_registry",
    "discover_into",
    "opencode_microvm_factory",
    "opencode_microvm_runner",
    "resolve_harness_runner",
]
