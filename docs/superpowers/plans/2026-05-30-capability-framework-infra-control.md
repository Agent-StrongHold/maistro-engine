# Capability Framework + Infra Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build SPEC-184's capability-slot/provider framework (Part A) and SPEC-187's infra monitor/action/approval slots over the live host-health API (Part B), so mAIstro can monitor and safely control the server.

**Architecture:** A new `maistro-core` subsystem (`maistro/capabilities/`) defines *slots* (typed seams), *providers* (swappable implementations), and a thread-safe `CapabilityRegistry` that tracks installed/active/enabled state and resolves the live provider with baseline/safe_noop/hard_required fallback. Part B adds three slots (`infra_monitor`, `infra_action`, `approval`) and providers that call the already-running host-health API (`:8150`); destructive actions gate through the `approval` slot ("auto for safe, approve risky").

**Tech Stack:** Python 3.13, `mypy --strict`, pytest + pytest-asyncio, frozen dataclasses, `typing.Protocol` (runtime_checkable), `httpx` (async), `threading.RLock`. Package: `maistro-core` (`packages/maistro-core/src/maistro/`).

---

## File Structure

**Part A — framework (`packages/maistro-core/src/maistro/capabilities/`):**
- `types.py` — `FallbackPolicy` enum, `ProviderHealth`, `SlotSpec`, `Unavailable` result.
- `protocols.py` — `CapabilityProvider` protocol.
- `registry.py` — `CapabilityRegistry` (register/activate/enable/resolve/validate_boot).
- `discovery.py` — entry-point discovery (`maistro.capabilities` group).
- `__init__.py` — public exports.
- Tests: `packages/maistro-core/tests/capabilities/test_{registry,resolve,discovery}.py`

**Part B — infra (`packages/maistro-core/src/maistro/capabilities/`):**
- `slots/infra.py` — `InfraHealth`, `ResourceHealth`, `ActionTier`, `tier_for()`, slot protocols `InfraMonitor`/`InfraAction`.
- `slots/approval.py` — `ApprovalRequest`, `ApprovalDecision`, `Approval` protocol, `ApprovalGate`.
- `providers/host_health.py` — `HostHealthMonitor`, `HostHealthAction`.
- `providers/approval_inbox.py` — `InboxApproval` (baseline).
- `http.py` — `AsyncHttp` protocol (injectable; thin httpx default) for testable HTTP.
- Tests: `packages/maistro-core/tests/capabilities/test_{infra_tier,inbox_approval,host_health_monitor,host_health_action,infra_e2e}.py`

**Commands** (run from repo root `/root/github/maistro-engine`, env via `uv`):
- Single test: `uv run pytest packages/maistro-core/tests/capabilities/test_registry.py -v`
- Subsystem: `uv run pytest packages/maistro-core/tests/capabilities -v`
- Types: `uv run mypy packages/maistro-core/src/maistro/capabilities`
- Lint: `uv run ruff check packages/maistro-core/src/maistro/capabilities`

---

# Part A — Capability Framework (SPEC-184 core)

### Task 1: Capability types

**Files:**
- Create: `packages/maistro-core/src/maistro/capabilities/__init__.py` (empty for now)
- Create: `packages/maistro-core/src/maistro/capabilities/types.py`
- Test: `packages/maistro-core/tests/capabilities/test_types.py` (+ `__init__.py` in that dir)

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_types.py
from __future__ import annotations

from maistro.capabilities.types import FallbackPolicy, ProviderHealth, SlotSpec, Unavailable


def test_slotspec_baseline_requires_provider_name():
    spec = SlotSpec(name="web_search", fallback_policy=FallbackPolicy.BASELINE, baseline_provider="ddg")
    assert spec.baseline_provider == "ddg"


def test_unavailable_is_typed_result():
    u = Unavailable(slot="smart_home", reason="no provider enabled")
    assert u.slot == "smart_home"
    assert "no provider" in u.reason


def test_provider_health_defaults():
    assert ProviderHealth(healthy=True).detail == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'maistro.capabilities'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/maistro-core/src/maistro/capabilities/types.py
"""Capability framework types: fallback policy, health, slot spec, unavailable result."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FallbackPolicy(str, Enum):
    """What a slot does when no enabled+healthy provider resolves."""

    BASELINE = "baseline"          # a core-only baseline provider fills the slot
    SAFE_NOOP = "safe_noop"        # return a typed Unavailable; never raise
    HARD_REQUIRED = "hard_required"  # boot fails if unfilled


@dataclass(frozen=True)
class ProviderHealth:
    """Result of a provider healthcheck."""

    healthy: bool
    detail: str = ""


@dataclass(frozen=True)
class SlotSpec:
    """Static declaration of a capability slot."""

    name: str
    fallback_policy: FallbackPolicy
    baseline_provider: str | None = None  # provider name; required when policy is BASELINE


@dataclass(frozen=True)
class Unavailable:
    """Typed 'capability unavailable' result for SAFE_NOOP slots."""

    slot: str
    reason: str = "capability unavailable"
```

Create empty `packages/maistro-core/src/maistro/capabilities/__init__.py` and `packages/maistro-core/tests/capabilities/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_types.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/ packages/maistro-core/tests/capabilities/
git commit -m "feat(capabilities): slot/provider framework types"
```

---

### Task 2: CapabilityProvider protocol

**Files:**
- Create: `packages/maistro-core/src/maistro/capabilities/protocols.py`
- Test: `packages/maistro-core/tests/capabilities/test_protocols.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_protocols.py
from __future__ import annotations

from maistro.capabilities.protocols import CapabilityProvider
from maistro.capabilities.types import ProviderHealth


class _FakeProvider:
    name = "fake"
    slot = "web_search"
    trust_tier = "t0"

    def requires(self) -> tuple[str, ...]:
        return ()

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(healthy=True)


def test_fake_provider_satisfies_protocol():
    assert isinstance(_FakeProvider(), CapabilityProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_protocols.py -v`
Expected: FAIL — `ModuleNotFoundError` (no `protocols` module).

- [ ] **Step 3: Write minimal implementation**

```python
# packages/maistro-core/src/maistro/capabilities/protocols.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_protocols.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/protocols.py packages/maistro-core/tests/capabilities/test_protocols.py
git commit -m "feat(capabilities): CapabilityProvider protocol"
```

---

### Task 3: CapabilityRegistry — register / activate / enable

**Files:**
- Create: `packages/maistro-core/src/maistro/capabilities/registry.py`
- Test: `packages/maistro-core/tests/capabilities/test_registry.py`

A small in-test fake provider is reused across registry tests — define it in the test file.

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_registry.py
from __future__ import annotations

import pytest

from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.types import FallbackPolicy, ProviderHealth, SlotSpec


class FakeProvider:
    def __init__(self, name: str, slot: str, *, healthy: bool = True, tier: str = "t0") -> None:
        self._name, self._slot, self._healthy, self._tier = name, slot, healthy, tier

    @property
    def name(self) -> str:
        return self._name

    @property
    def slot(self) -> str:
        return self._slot

    @property
    def trust_tier(self) -> str:
        return self._tier

    def requires(self) -> tuple[str, ...]:
        return ()

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(healthy=self._healthy)


@pytest.fixture()
def registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.define(SlotSpec(name="web_search", fallback_policy=FallbackPolicy.SAFE_NOOP))
    return reg


def test_register_is_installed_but_inactive(registry: CapabilityRegistry):
    registry.register(FakeProvider("tavily", "web_search"))
    assert "tavily" in registry.installed("web_search")
    assert registry.active_name("web_search") is None  # discovery never auto-activates


def test_activate_sets_active(registry: CapabilityRegistry):
    registry.register(FakeProvider("tavily", "web_search"))
    registry.activate("web_search", "tavily")
    assert registry.active_name("web_search") == "tavily"


def test_activate_unknown_provider_raises(registry: CapabilityRegistry):
    with pytest.raises(KeyError):
        registry.activate("web_search", "nope")


def test_register_to_undefined_slot_raises(registry: CapabilityRegistry):
    with pytest.raises(KeyError):
        registry.register(FakeProvider("x", "no_such_slot"))


def test_enabled_defaults_true_and_toggles(registry: CapabilityRegistry):
    assert registry.is_enabled("web_search") is True
    registry.set_enabled("web_search", False)
    assert registry.is_enabled("web_search") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError` (no `registry` module).

- [ ] **Step 3: Write minimal implementation**

```python
# packages/maistro-core/src/maistro/capabilities/registry.py
"""Capability registry: defines slots, registers providers (installed/inactive),
activates/enables them, and resolves the live provider with fallback. Thread-safe."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maistro.capabilities.types import FallbackPolicy, SlotSpec

if TYPE_CHECKING:
    from maistro.capabilities.protocols import CapabilityProvider

logger = logging.getLogger("maistro.capabilities.registry")


@dataclass
class _SlotState:
    spec: SlotSpec
    providers: dict[str, "CapabilityProvider"] = field(default_factory=dict)
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

    def register(self, provider: "CapabilityProvider") -> None:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_registry.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/registry.py packages/maistro-core/tests/capabilities/test_registry.py
git commit -m "feat(capabilities): registry define/register/activate/enable"
```

---

### Task 4: Resolution + fallback policy

**Files:**
- Modify: `packages/maistro-core/src/maistro/capabilities/registry.py` (add `resolve`, `validate_boot`)
- Test: `packages/maistro-core/tests/capabilities/test_resolve.py`

Resolution contract: `async resolve(slot)` returns the `CapabilityProvider` to use, or `None` when the slot should apply its fallback. Rules: disabled → fallback; else active (or first by trust tier); healthcheck; unhealthy → fallback. Fallback = baseline provider if policy is `BASELINE` and present, else `None`. `validate_boot()` raises if a `HARD_REQUIRED` slot resolves to `None`.

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_resolve.py
from __future__ import annotations

import pytest

from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.types import FallbackPolicy, SlotSpec
from maistro.capabilities.tests_fakes import FakeProvider  # shared fake, created in Step 3


@pytest.fixture()
def reg() -> CapabilityRegistry:
    r = CapabilityRegistry()
    r.define(SlotSpec(name="search", fallback_policy=FallbackPolicy.SAFE_NOOP))
    r.define(
        SlotSpec(name="approval", fallback_policy=FallbackPolicy.BASELINE, baseline_provider="inbox")
    )
    r.define(SlotSpec(name="llm", fallback_policy=FallbackPolicy.HARD_REQUIRED))
    return r


async def test_disabled_slot_resolves_to_fallback_none(reg: CapabilityRegistry):
    reg.register(FakeProvider("tavily", "search"))
    reg.activate("search", "tavily")
    reg.set_enabled("search", False)
    assert await reg.resolve("search") is None  # SAFE_NOOP → None


async def test_active_healthy_resolves(reg: CapabilityRegistry):
    reg.register(FakeProvider("tavily", "search"))
    reg.activate("search", "tavily")
    chosen = await reg.resolve("search")
    assert chosen is not None and chosen.name == "tavily"


async def test_unhealthy_active_falls_through_to_baseline(reg: CapabilityRegistry):
    reg.register(FakeProvider("ha_push", "approval", healthy=False))
    reg.register(FakeProvider("inbox", "approval"))  # baseline
    reg.activate("approval", "ha_push")
    chosen = await reg.resolve("approval")
    assert chosen is not None and chosen.name == "inbox"  # fell back to baseline


async def test_safe_noop_no_provider_returns_none(reg: CapabilityRegistry):
    assert await reg.resolve("search") is None


def test_validate_boot_raises_when_hard_required_unfilled(reg: CapabilityRegistry):
    with pytest.raises(RuntimeError, match="llm"):
        reg.validate_boot()
```

> Note: `FakeProvider` is shared via a real importable module `maistro/capabilities/tests_fakes.py`, created in Step 3 of this task. (Importing it in Step 1 before it exists is intentional — that's part of why the test fails first.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_resolve.py -v`
Expected: FAIL — `AttributeError: 'CapabilityRegistry' object has no attribute 'resolve'` (after fixing imports).

- [ ] **Step 3: Write minimal implementation**

Add a shared fake (real module):

```python
# packages/maistro-core/src/maistro/capabilities/tests_fakes.py
"""Reusable in-memory provider for capability tests."""

from __future__ import annotations

from maistro.capabilities.types import ProviderHealth


class FakeProvider:
    def __init__(self, name: str, slot: str, *, healthy: bool = True, tier: str = "t0") -> None:
        self._name, self._slot, self._healthy, self._tier = name, slot, healthy, tier

    @property
    def name(self) -> str:
        return self._name

    @property
    def slot(self) -> str:
        return self._slot

    @property
    def trust_tier(self) -> str:
        return self._tier

    def requires(self) -> tuple[str, ...]:
        return ()

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(healthy=self._healthy)
```

Append to `registry.py`:

```python
    async def resolve(self, slot: str) -> "CapabilityProvider | None":
        """Resolve the provider to use, or None to apply the slot's fallback.

        disabled → fallback; else active (or first by trust tier); healthcheck;
        unhealthy → fallback. Fallback = baseline provider (if policy BASELINE) else None.
        """
        with self._lock:
            state = self._slot(slot)
            spec = state.spec
            enabled = state.enabled
            chosen_name = state.active
            providers = dict(state.providers)

        def _baseline() -> "CapabilityProvider | None":
            if spec.fallback_policy is FallbackPolicy.BASELINE and spec.baseline_provider:
                return providers.get(spec.baseline_provider)
            return None

        if not enabled:
            return _baseline()

        if chosen_name is None:
            # no explicit active → first by trust tier (t0 < t1 < ...), excluding baseline-only
            candidates = sorted(providers.values(), key=lambda p: p.trust_tier)
            chosen = candidates[0] if candidates else None
        else:
            chosen = providers.get(chosen_name)

        if chosen is None:
            return _baseline()

        health = await chosen.healthcheck()
        if not health.healthy:
            logger.warning("Provider %s unhealthy for slot %s: %s", chosen.name, slot, health.detail)
            fb = _baseline()
            return fb if (fb is not None and fb.name != chosen.name) else None
        return chosen

    def validate_boot(self) -> None:
        """Raise if any HARD_REQUIRED slot has no provider to resolve."""
        with self._lock:
            for name, state in self._slots.items():
                if state.spec.fallback_policy is FallbackPolicy.HARD_REQUIRED and not state.providers:
                    raise RuntimeError(f"hard_required slot '{name}' has no provider")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_resolve.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/registry.py packages/maistro-core/src/maistro/capabilities/tests_fakes.py packages/maistro-core/tests/capabilities/test_resolve.py
git commit -m "feat(capabilities): provider resolution + baseline/hard_required fallback"
```

---

### Task 5: Entry-point discovery

**Files:**
- Create: `packages/maistro-core/src/maistro/capabilities/discovery.py`
- Test: `packages/maistro-core/tests/capabilities/test_discovery.py`

Discovery loads providers declared under the `maistro.capabilities` entry-point group and registers them as installed-inactive. It must accept an injectable iterable of entry points so it is testable without installing a package.

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_discovery.py
from __future__ import annotations

from maistro.capabilities.discovery import discover_into
from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.tests_fakes import FakeProvider
from maistro.capabilities.types import FallbackPolicy, SlotSpec


class _FakeEP:
    def __init__(self, name: str, obj: object) -> None:
        self.name = name
        self._obj = obj

    def load(self) -> object:
        return self._obj


def _factory():
    return FakeProvider("plugin_search", "search")


def test_discover_registers_inactive():
    reg = CapabilityRegistry()
    reg.define(SlotSpec(name="search", fallback_policy=FallbackPolicy.SAFE_NOOP))
    n = discover_into(reg, entry_points=[_FakeEP("plugin_search", _factory)])
    assert n == 1
    assert "plugin_search" in reg.installed("search")
    assert reg.active_name("search") is None  # never auto-activates


def test_discover_skips_unknown_slot_gracefully():
    reg = CapabilityRegistry()  # no slots defined
    n = discover_into(reg, entry_points=[_FakeEP("plugin_search", _factory)])
    assert n == 0  # registration failed (unknown slot) → not counted, no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_discovery.py -v`
Expected: FAIL — `ModuleNotFoundError` (no `discovery` module).

- [ ] **Step 3: Write minimal implementation**

```python
# packages/maistro-core/src/maistro/capabilities/discovery.py
"""Entry-point discovery for capability providers (group: maistro.capabilities).

A provider package declares:
    [project.entry-points."maistro.capabilities"]
    my_provider = "my_pkg:make_provider"   # a zero-arg factory returning a CapabilityProvider
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maistro.capabilities.registry import CapabilityRegistry

logger = logging.getLogger("maistro.capabilities.discovery")

GROUP = "maistro.capabilities"


def discover_into(
    registry: "CapabilityRegistry",
    *,
    entry_points: Iterable[EntryPoint] | None = None,
) -> int:
    """Load + register providers as installed-inactive. Returns count registered.

    Never raises on a single bad entry point — logs and continues. Pass
    `entry_points` to inject (tests); otherwise reads the live metadata group.
    """
    eps = entry_points if entry_points is not None else _live_entry_points()
    count = 0
    for ep in eps:
        try:
            factory = ep.load()
            provider = factory()
            registry.register(provider)
            count += 1
        except Exception as exc:  # noqa: BLE001 — discovery must be resilient
            logger.warning("Skipping capability entry point %r: %s", ep.name, exc)
    return count


def _live_entry_points() -> Iterable[EntryPoint]:
    try:
        return entry_points(group=GROUP)
    except Exception:  # noqa: BLE001
        return ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_discovery.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/discovery.py packages/maistro-core/tests/capabilities/test_discovery.py
git commit -m "feat(capabilities): entry-point provider discovery"
```

---

### Task 6: Public exports + type/lint gate for Part A

**Files:**
- Modify: `packages/maistro-core/src/maistro/capabilities/__init__.py`

- [ ] **Step 1: Write exports**

```python
# packages/maistro-core/src/maistro/capabilities/__init__.py
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
```

- [ ] **Step 2: Run the full subsystem suite + types + lint**

Run:
```bash
uv run pytest packages/maistro-core/tests/capabilities -v
uv run mypy packages/maistro-core/src/maistro/capabilities
uv run ruff check packages/maistro-core/src/maistro/capabilities
```
Expected: all tests PASS, mypy "Success: no issues", ruff "All checks passed".

- [ ] **Step 3: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/__init__.py
git commit -m "feat(capabilities): public exports; Part A framework complete"
```

---

# Part B — Infra Control / Monitor / Approval (SPEC-187)

### Task 7: Infra + approval slot types & protocols

**Files:**
- Create: `packages/maistro-core/src/maistro/capabilities/slots/__init__.py` (empty)
- Create: `packages/maistro-core/src/maistro/capabilities/slots/infra.py`
- Create: `packages/maistro-core/src/maistro/capabilities/slots/approval.py`
- Test: `packages/maistro-core/tests/capabilities/test_slot_types.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_slot_types.py
from __future__ import annotations

from maistro.capabilities.slots.approval import ApprovalDecision, ApprovalRequest
from maistro.capabilities.slots.infra import ActionTier, InfraHealth, ResourceHealth


def test_infra_health_shape():
    h = InfraHealth(
        ts="2026-05-30T00:00:00Z",
        resources={"gpu": ResourceHealth(status="ok", detail={})},
    )
    assert h.resources["gpu"].status == "ok"


def test_action_tier_values():
    assert {t.value for t in ActionTier} == {"read", "reversible", "destructive"}


def test_approval_request_and_decision():
    req = ApprovalRequest(action="restart_stack", params={"name": "traefik"}, tier="destructive",
                          requester="self_repair", rationale="traefik unhealthy")
    dec = ApprovalDecision(request_id=req.request_id, approved=True, actor="blake")
    assert dec.request_id == req.request_id and dec.approved is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_slot_types.py -v`
Expected: FAIL — `ModuleNotFoundError` (no `slots` package).

- [ ] **Step 3: Write minimal implementation**

```python
# packages/maistro-core/src/maistro/capabilities/slots/infra.py
"""infra_monitor + infra_action slot types and protocols (SPEC-187)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from maistro.capabilities.protocols import CapabilityProvider


class ActionTier(str, Enum):
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
```

```python
# packages/maistro-core/src/maistro/capabilities/slots/approval.py
"""approval slot types, protocol, and the ApprovalGate helper (SPEC-187)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from maistro.capabilities.protocols import CapabilityProvider


@dataclass(frozen=True)
class ApprovalRequest:
    action: str
    params: dict[str, Any]
    tier: str
    requester: str
    rationale: str = ""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass(frozen=True)
class ApprovalDecision:
    request_id: str
    approved: bool
    actor: str = ""


@runtime_checkable
class Approval(CapabilityProvider, Protocol):
    async def request(self, req: ApprovalRequest) -> ApprovalDecision:
        """Create a pending approval and return the decision once resolved
        (approved/denied/expired). Implementations decide how the human responds."""
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_slot_types.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/slots/
git add packages/maistro-core/tests/capabilities/test_slot_types.py
git commit -m "feat(capabilities): infra + approval slot types and protocols"
```

---

### Task 8: Blast-radius tiering

**Files:**
- Modify: `packages/maistro-core/src/maistro/capabilities/slots/infra.py` (add `tier_for`)
- Test: `packages/maistro-core/tests/capabilities/test_infra_tier.py`

Tiering mirrors the verified host-health `POST_ACTIONS` allowlist (SPEC-187 table).

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_infra_tier.py
from __future__ import annotations

import pytest

from maistro.capabilities.slots.infra import ActionTier, tier_for


@pytest.mark.parametrize(
    "action,params,expected",
    [
        ("docker_logs", {}, ActionTier.READ),
        ("ollama_list", {}, ActionTier.READ),
        ("snapraid_status", {}, ActionTier.READ),
        ("restart_container", {"name": "x"}, ActionTier.REVERSIBLE),
        ("restart_service", {"name": "ollama"}, ActionTier.REVERSIBLE),
        ("ollama_pull", {"model": "qwen"}, ActionTier.REVERSIBLE),
        ("vm_control", {"action": "start", "vmid": "102"}, ActionTier.REVERSIBLE),
        ("vm_control", {"action": "status", "vmid": "102"}, ActionTier.READ),
        ("vm_control", {"action": "stop", "vmid": "102"}, ActionTier.DESTRUCTIVE),
        ("vm_control", {"action": "reboot", "vmid": "102"}, ActionTier.DESTRUCTIVE),
        ("restart_stack", {"name": "traefik"}, ActionTier.DESTRUCTIVE),
        ("docker_prune", {}, ActionTier.DESTRUCTIVE),
    ],
)
def test_tier_for(action, params, expected):
    assert tier_for(action, params) == expected


def test_unknown_action_is_destructive_by_default():
    assert tier_for("rm_rf_everything", {}) == ActionTier.DESTRUCTIVE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_infra_tier.py -v`
Expected: FAIL — `ImportError: cannot import name 'tier_for'`.

- [ ] **Step 3: Write minimal implementation**

Append to `slots/infra.py`:

```python
_READ_ACTIONS = {"docker_logs", "ollama_list", "snapraid_status"}
_REVERSIBLE_ACTIONS = {"restart_container", "restart_service", "ollama_pull"}
_DESTRUCTIVE_ACTIONS = {"restart_stack", "docker_prune"}
_VM_READ = {"status"}
_VM_REVERSIBLE = {"start"}
_VM_DESTRUCTIVE = {"stop", "reboot"}


def tier_for(action: str, params: dict[str, Any]) -> ActionTier:
    """Classify a host action by blast radius. Unknown → DESTRUCTIVE (fail safe)."""
    if action in _READ_ACTIONS:
        return ActionTier.READ
    if action in _REVERSIBLE_ACTIONS:
        return ActionTier.REVERSIBLE
    if action in _DESTRUCTIVE_ACTIONS:
        return ActionTier.DESTRUCTIVE
    if action == "vm_control":
        vm_action = str(params.get("action", ""))
        if vm_action in _VM_READ:
            return ActionTier.READ
        if vm_action in _VM_REVERSIBLE:
            return ActionTier.REVERSIBLE
        if vm_action in _VM_DESTRUCTIVE:
            return ActionTier.DESTRUCTIVE
    return ActionTier.DESTRUCTIVE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_infra_tier.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/slots/infra.py packages/maistro-core/tests/capabilities/test_infra_tier.py
git commit -m "feat(capabilities): blast-radius action tiering"
```

---

### Task 9: Inbox approval provider (baseline)

**Files:**
- Create: `packages/maistro-core/src/maistro/capabilities/providers/__init__.py` (empty)
- Create: `packages/maistro-core/src/maistro/capabilities/providers/approval_inbox.py`
- Test: `packages/maistro-core/tests/capabilities/test_inbox_approval.py`

The baseline approval inbox: `request()` enqueues a pending item and waits (asyncio.Event) until `resolve(request_id, approved, actor)` is called by the UI/CLI/API. Needs no external service.

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_inbox_approval.py
from __future__ import annotations

import asyncio

from maistro.capabilities.providers.approval_inbox import InboxApproval
from maistro.capabilities.slots.approval import ApprovalRequest


async def test_request_blocks_until_resolved():
    inbox = InboxApproval()
    req = ApprovalRequest(action="restart_stack", params={}, tier="destructive", requester="self_repair")

    async def approve_soon():
        await asyncio.sleep(0.01)
        assert any(p.request_id == req.request_id for p in inbox.pending())
        inbox.resolve(req.request_id, approved=True, actor="blake")

    decision, _ = await asyncio.gather(inbox.request(req), approve_soon())
    assert decision.approved is True and decision.actor == "blake"
    assert inbox.pending() == []  # cleared after resolution


async def test_deny():
    inbox = InboxApproval()
    req = ApprovalRequest(action="docker_prune", params={}, tier="destructive", requester="op")
    asyncio.get_event_loop().call_soon(lambda: inbox.resolve(req.request_id, approved=False, actor="blake"))
    decision = await inbox.request(req)
    assert decision.approved is False


def test_is_capability_provider():
    from maistro.capabilities.protocols import CapabilityProvider
    assert isinstance(InboxApproval(), CapabilityProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_inbox_approval.py -v`
Expected: FAIL — `ModuleNotFoundError` (no `providers.approval_inbox`).

- [ ] **Step 3: Write minimal implementation**

```python
# packages/maistro-core/src/maistro/capabilities/providers/approval_inbox.py
"""Built-in approval inbox — the baseline `approval` provider (SPEC-184/187).

Needs no external service: request() creates a pending item and awaits an
asyncio.Event resolved by the UI/CLI/API via resolve()."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from maistro.capabilities.slots.approval import ApprovalDecision, ApprovalRequest
from maistro.capabilities.types import ProviderHealth


@dataclass
class _Pending:
    req: ApprovalRequest
    event: asyncio.Event
    decision: ApprovalDecision | None = None


class InboxApproval:
    """Baseline approval provider backed by an in-process pending queue."""

    def __init__(self) -> None:
        self._pending: dict[str, _Pending] = {}

    # --- CapabilityProvider ---
    @property
    def name(self) -> str:
        return "inbox"

    @property
    def slot(self) -> str:
        return "approval"

    @property
    def trust_tier(self) -> str:
        return "t0"

    def requires(self) -> tuple[str, ...]:
        return ()

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(healthy=True)

    # --- Approval ---
    async def request(self, req: ApprovalRequest) -> ApprovalDecision:
        pending = _Pending(req=req, event=asyncio.Event())
        self._pending[req.request_id] = pending
        await pending.event.wait()
        decision = pending.decision
        self._pending.pop(req.request_id, None)
        assert decision is not None  # set before event fired
        return decision

    # --- UI/CLI/API surface ---
    def pending(self) -> list[ApprovalRequest]:
        return [p.req for p in self._pending.values()]

    def resolve(self, request_id: str, *, approved: bool, actor: str = "") -> bool:
        pending = self._pending.get(request_id)
        if pending is None:
            return False
        pending.decision = ApprovalDecision(request_id=request_id, approved=approved, actor=actor)
        pending.event.set()
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_inbox_approval.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/providers/
git add packages/maistro-core/tests/capabilities/test_inbox_approval.py
git commit -m "feat(capabilities): baseline inbox approval provider"
```

---

### Task 10: Host-health monitor provider

**Files:**
- Create: `packages/maistro-core/src/maistro/capabilities/http.py`
- Create: `packages/maistro-core/src/maistro/capabilities/providers/host_health.py`
- Test: `packages/maistro-core/tests/capabilities/test_host_health_monitor.py`

The provider depends on an injectable `AsyncHttp` protocol (so tests use a fake; production wraps `httpx`). It maps the verified `/full` sections (`gpu, storage, docker, vms, services`) to `InfraHealth`; on transport failure it returns a `down`-marked health rather than raising (SAFE_NOOP friendliness).

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_host_health_monitor.py
from __future__ import annotations

from typing import Any

from maistro.capabilities.providers.host_health import HostHealthMonitor


class FakeHttp:
    def __init__(self, payload: dict[str, Any] | None, raise_exc: bool = False) -> None:
        self._payload, self._raise = payload, raise_exc

    async def get_json(self, path: str) -> dict[str, Any]:
        if self._raise:
            raise ConnectionError("unreachable")
        assert path == "/full"
        return self._payload or {}


async def test_snapshot_maps_sections():
    http = FakeHttp({
        "timestamp": "2026-05-30T00:00:00Z",
        "gpu": {"ok": True},
        "storage": {"ok": True},
        "docker": {"unhealthy": []},
        "vms": [],
        "services": {},
    })
    mon = HostHealthMonitor(http=http)
    health = await mon.snapshot()
    assert set(health.resources) == {"gpu", "storage", "docker", "vms", "services"}
    assert health.ts == "2026-05-30T00:00:00Z"


async def test_snapshot_unreachable_marks_down_not_raises():
    mon = HostHealthMonitor(http=FakeHttp(None, raise_exc=True))
    health = await mon.snapshot()
    assert all(r.status == "down" for r in health.resources.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_host_health_monitor.py -v`
Expected: FAIL — `ModuleNotFoundError` (no `providers.host_health`).

- [ ] **Step 3: Write minimal implementation**

```python
# packages/maistro-core/src/maistro/capabilities/http.py
"""Injectable async HTTP seam for capability providers (testable; httpx-backed default)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AsyncHttp(Protocol):
    async def get_json(self, path: str) -> dict[str, Any]: ...
    async def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...
```

```python
# packages/maistro-core/src/maistro/capabilities/providers/host_health.py
"""Providers backed by the host-health API (:8150) — monitor + action (SPEC-187)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from maistro.capabilities.slots.infra import InfraHealth, ResourceHealth
from maistro.capabilities.types import ProviderHealth

if TYPE_CHECKING:
    from maistro.capabilities.http import AsyncHttp

logger = logging.getLogger("maistro.capabilities.host_health")

_SECTIONS = ("gpu", "storage", "docker", "vms", "services")


class HostHealthMonitor:
    """infra_monitor provider: GET /full → normalized InfraHealth."""

    def __init__(self, http: "AsyncHttp") -> None:
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
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(healthy=False, detail=str(exc))

    async def snapshot(self) -> InfraHealth:
        try:
            data = await self._http.get_json("/full")
        except Exception as exc:  # noqa: BLE001
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_host_health_monitor.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/http.py packages/maistro-core/src/maistro/capabilities/providers/host_health.py packages/maistro-core/tests/capabilities/test_host_health_monitor.py
git commit -m "feat(capabilities): host-health monitor provider"
```

---

### Task 11: Host-health action provider with approval gating

**Files:**
- Modify: `packages/maistro-core/src/maistro/capabilities/providers/host_health.py` (add `HostHealthAction`)
- Test: `packages/maistro-core/tests/capabilities/test_host_health_action.py`

The action provider takes the `AsyncHttp`, an `autonomy` mode (`approve_all|auto_safe|detect_only`), and an `approval` provider. `act()`: classify tier → `read` runs; `reversible` runs iff `auto_safe` else gates; `destructive` always gates; `detect_only` never runs.

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_host_health_action.py
from __future__ import annotations

from typing import Any

from maistro.capabilities.providers.approval_inbox import InboxApproval
from maistro.capabilities.providers.host_health import HostHealthAction
from maistro.capabilities.slots.approval import ApprovalDecision, ApprovalRequest


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, path: str) -> dict[str, Any]:
        return {}

    async def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, body))
        return {"status": "ok"}


class AutoApprove(InboxApproval):
    async def request(self, req: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(request_id=req.request_id, approved=True, actor="test")


class AutoDeny(InboxApproval):
    async def request(self, req: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(request_id=req.request_id, approved=False, actor="test")


async def test_read_action_runs_without_approval():
    http = FakeHttp()
    act = HostHealthAction(http=http, autonomy="auto_safe", approval=AutoDeny())
    res = await act.act("docker_logs", {"name": "x"})
    assert res.ok and http.calls  # executed despite deny provider (read never gates)


async def test_reversible_runs_when_auto_safe():
    http = FakeHttp()
    act = HostHealthAction(http=http, autonomy="auto_safe", approval=AutoDeny())
    res = await act.act("restart_container", {"name": "x"})
    assert res.ok and http.calls


async def test_destructive_blocked_until_approved():
    http = FakeHttp()
    act = HostHealthAction(http=http, autonomy="auto_safe", approval=AutoDeny())
    res = await act.act("docker_prune", {})
    assert res.ok is False and res.blocked_pending_approval and not http.calls  # denied → no call


async def test_destructive_runs_after_approval():
    http = FakeHttp()
    act = HostHealthAction(http=http, autonomy="auto_safe", approval=AutoApprove())
    res = await act.act("restart_stack", {"name": "traefik"})
    assert res.ok and http.calls


async def test_detect_only_never_executes():
    http = FakeHttp()
    act = HostHealthAction(http=http, autonomy="detect_only", approval=AutoApprove())
    res = await act.act("restart_container", {"name": "x"})
    assert res.ok is False and not http.calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_host_health_action.py -v`
Expected: FAIL — `ImportError: cannot import name 'HostHealthAction'`.

- [ ] **Step 3: Write minimal implementation**

Append to `providers/host_health.py` (add imports `from typing import Any, Literal`; `from maistro.capabilities.slots.approval import ApprovalRequest`; `from maistro.capabilities.slots.infra import ActionResult, ActionTier, tier_for`):

```python
_ALLOWED = (
    "restart_container", "restart_stack", "restart_service", "vm_control",
    "docker_logs", "docker_prune", "ollama_list", "ollama_pull", "snapraid_status",
)


class HostHealthAction:
    """infra_action provider: POST /action/{name}, tier-gated through approval."""

    def __init__(
        self,
        http: "AsyncHttp",
        *,
        autonomy: "Literal['approve_all', 'auto_safe', 'detect_only']" = "auto_safe",
        approval: "Approval | None" = None,
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
                return ActionResult(ok=False, blocked_pending_approval=True,
                                    detail="approval required but no approval provider")
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
        except Exception as exc:  # noqa: BLE001
            return ActionResult(ok=False, detail=str(exc))
        ok = str(data.get("status", "")).lower() != "error"
        return ActionResult(ok=ok, detail=str(data.get("detail", "")))
```

Add `from maistro.capabilities.slots.approval import Approval` under `TYPE_CHECKING`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_host_health_action.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/src/maistro/capabilities/providers/host_health.py packages/maistro-core/tests/capabilities/test_host_health_action.py
git commit -m "feat(capabilities): host-health action provider with tiered approval gating"
```

---

### Task 12: End-to-end integration through the registry

**Files:**
- Test: `packages/maistro-core/tests/capabilities/test_infra_e2e.py`

Wire the slots + providers into a `CapabilityRegistry` and assert the full path: monitor read, reversible auto-runs, destructive blocks then runs after approval.

- [ ] **Step 1: Write the failing test**

```python
# packages/maistro-core/tests/capabilities/test_infra_e2e.py
from __future__ import annotations

from typing import Any

import pytest

from maistro.capabilities.providers.approval_inbox import InboxApproval
from maistro.capabilities.providers.host_health import HostHealthAction, HostHealthMonitor
from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.slots.infra import InfraAction, InfraMonitor
from maistro.capabilities.types import FallbackPolicy, SlotSpec


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_json(self, path: str) -> dict[str, Any]:
        return {"timestamp": "t", "gpu": {}, "storage": {}, "docker": {}, "vms": [], "services": {}}

    async def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(path)
        return {"status": "ok"}


@pytest.fixture()
def reg() -> CapabilityRegistry:
    r = CapabilityRegistry()
    r.define(SlotSpec(name="infra_monitor", fallback_policy=FallbackPolicy.SAFE_NOOP))
    r.define(SlotSpec(name="infra_action", fallback_policy=FallbackPolicy.SAFE_NOOP))
    r.define(SlotSpec(name="approval", fallback_policy=FallbackPolicy.BASELINE, baseline_provider="inbox"))
    return r


async def test_monitor_resolves_and_reads(reg: CapabilityRegistry):
    reg.register(HostHealthMonitor(http=FakeHttp()))
    reg.activate("infra_monitor", "host_health")
    mon = await reg.resolve("infra_monitor")
    assert isinstance(mon, InfraMonitor)
    health = await mon.snapshot()
    assert "gpu" in health.resources


async def test_reversible_auto_runs(reg: CapabilityRegistry):
    http = FakeHttp()
    reg.register(InboxApproval())
    reg.register(HostHealthAction(http=http, autonomy="auto_safe", approval=InboxApproval()))
    reg.activate("infra_action", "host_health")
    action = await reg.resolve("infra_action")
    assert isinstance(action, InfraAction)
    res = await action.act("restart_container", {"name": "x"})
    assert res.ok and http.calls


async def test_destructive_blocks_then_runs_after_inbox_approval(reg: CapabilityRegistry):
    import asyncio
    http = FakeHttp()
    inbox = InboxApproval()
    reg.register(inbox)
    reg.activate("approval", "inbox")
    reg.register(HostHealthAction(http=http, autonomy="auto_safe", approval=inbox))
    reg.activate("infra_action", "host_health")
    action = await reg.resolve("infra_action")

    async def approve_soon():
        await asyncio.sleep(0.01)
        pid = inbox.pending()[0].request_id
        inbox.resolve(pid, approved=True, actor="blake")

    res, _ = await asyncio.gather(action.act("docker_prune", {}), approve_soon())  # type: ignore[union-attr]
    assert res.ok and http.calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_infra_e2e.py -v`
Expected: FAIL initially only if wiring/signatures mismatch; otherwise it validates Tasks 7–11 compose. Fix any signature drift surfaced here.

- [ ] **Step 3: Make it pass**

No new production code expected — this is an integration test over Tasks 7–11. If it fails, the failure points to a real composition bug (e.g., a protocol method name mismatch); fix it in the relevant provider/registry file, not the test.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/maistro-core/tests/capabilities/test_infra_e2e.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/maistro-core/tests/capabilities/test_infra_e2e.py
git commit -m "test(capabilities): infra monitor/action/approval end-to-end"
```

---

### Task 13: Full gate — suite + mypy --strict + ruff

**Files:** none (verification + final commit)

- [ ] **Step 1: Run the full capabilities suite**

Run: `uv run pytest packages/maistro-core/tests/capabilities -v`
Expected: all tests PASS.

- [ ] **Step 2: mypy strict**

Run: `uv run mypy packages/maistro-core/src/maistro/capabilities`
Expected: `Success: no issues found`. Fix any typing gaps (e.g. add explicit return types, `Literal` import) until clean.

- [ ] **Step 3: ruff**

Run: `uv run ruff check packages/maistro-core/src/maistro/capabilities packages/maistro-core/tests/capabilities`
Expected: `All checks passed!`

- [ ] **Step 4: Confirm no regressions in the wider package**

Run: `uv run pytest packages/maistro-core -q`
Expected: no new failures attributable to the `capabilities` package.

- [ ] **Step 5: Final commit**

```bash
git add -A packages/maistro-core
git commit -m "chore(capabilities): green suite, mypy --strict, ruff clean — Phase 0+1 complete"
```

---

## Notes for the implementer

- **Async tests:** the repo uses `pytest-asyncio`. If a test needs an explicit marker, add `@pytest.mark.asyncio` (check `pyproject.toml [tool.pytest.ini_options]` for `asyncio_mode = "auto"`; if auto, no marker needed).
- **Not yet wired into the running app:** this plan builds and unit-tests the framework + providers in `maistro-core`. Wiring them into the `Container` (DI) and exposing `/v1/capabilities/*` + `maistro approvals` in hive-conductor, plus the httpx-backed `AsyncHttp` default pointed at `HOST_HEALTH_URL`, is the next plan (Phase 1b integration). Keep that out of scope here so this lands as a self-contained, tested unit.
- **Token from vault:** the production `AsyncHttp` must read the host-health bearer token from the SPEC-011 vault, never hardcode it (deferred to the integration plan).
```
