"""Sandbox selector — picks the strongest available backend that satisfies policy.

Fail-closed: if no backend meets the minimum tier, refuses with a clear error.
No silent downgrade.
"""

from __future__ import annotations

import logging
from typing import Any

from maistro.sandbox.policy import _TIER_ORDER, IsolationTier, WorkloadPolicy, tier_satisfies
from maistro.sandbox.protocol import SandboxConfig, SandboxProtocol

logger = logging.getLogger("maistro.sandbox.selector")


class NoSuitableBackendError(Exception):
    """Raised when no registered backend meets the workload's minimum isolation."""


class SandboxSelector:
    """Registry of sandbox backends. Selects the best one for a given policy."""

    def __init__(self) -> None:
        self._backends: dict[IsolationTier, SandboxProtocol] = {}

    def register(self, tier: IsolationTier, backend: SandboxProtocol) -> None:
        """Register a backend at a given isolation tier."""
        self._backends[tier] = backend
        logger.info("sandbox_backend_registered tier=%s backend=%s", tier, type(backend).__name__)

    @property
    def available_tiers(self) -> list[IsolationTier]:
        """Registered tiers, strongest first."""
        return [t for t in _TIER_ORDER if t in self._backends]

    @property
    def strongest_tier(self) -> IsolationTier | None:
        tiers = self.available_tiers
        return tiers[0] if tiers else None

    def select(self, policy: WorkloadPolicy) -> tuple[IsolationTier, SandboxProtocol]:
        """Select the strongest available backend that satisfies the policy.

        Returns (tier, backend). Raises NoSuitableBackendError if nothing qualifies.
        """
        for tier in _TIER_ORDER:
            if tier not in self._backends:
                continue
            if tier_satisfies(tier, policy.min_tier):
                return tier, self._backends[tier]

        available = ", ".join(self.available_tiers) or "none"
        raise NoSuitableBackendError(
            f"Workload requires min_tier={policy.min_tier!r} ({policy.reason}). "
            f"Available: {available}. No backend qualifies — execution refused."
        )

    def build_config(self, policy: WorkloadPolicy, **overrides: Any) -> SandboxConfig:
        """Build a SandboxConfig from a policy."""
        return SandboxConfig(
            image_ref=overrides.get("image_ref", "maistro-builders:latest"),
            workspace_path=overrides.get("workspace_path", "/workspace"),
            memory_mb=overrides.get("memory_mb", policy.max_memory_mb),
            cpu_cores=overrides.get("cpu_cores", 1.0),
            pids_limit=overrides.get("pids_limit", 256),
            disk_mb=overrides.get("disk_mb", 2048),
            timeout_s=overrides.get("timeout_s", policy.max_timeout_s),
            lifetime_s=overrides.get("lifetime_s", 3600),
            network=overrides.get("network", policy.network_allowed),
            writable_paths=overrides.get("writable_paths", []),
            env=overrides.get("env", {}),
            min_isolation=policy.min_tier,
        )
