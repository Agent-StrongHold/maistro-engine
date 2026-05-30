from __future__ import annotations

import pytest

from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.tests_fakes import FakeProvider
from maistro.capabilities.types import FallbackPolicy, SlotSpec


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
    assert await reg.resolve("search") is None


async def test_active_healthy_resolves(reg: CapabilityRegistry):
    reg.register(FakeProvider("tavily", "search"))
    reg.activate("search", "tavily")
    chosen = await reg.resolve("search")
    assert chosen is not None and chosen.name == "tavily"


async def test_unhealthy_active_falls_through_to_baseline(reg: CapabilityRegistry):
    reg.register(FakeProvider("ha_push", "approval", healthy=False))
    reg.register(FakeProvider("inbox", "approval"))
    reg.activate("approval", "ha_push")
    chosen = await reg.resolve("approval")
    assert chosen is not None and chosen.name == "inbox"


async def test_safe_noop_no_provider_returns_none(reg: CapabilityRegistry):
    assert await reg.resolve("search") is None


def test_validate_boot_raises_when_hard_required_unfilled(reg: CapabilityRegistry):
    with pytest.raises(RuntimeError, match="llm"):
        reg.validate_boot()
