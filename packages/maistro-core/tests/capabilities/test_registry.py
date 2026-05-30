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
    assert registry.active_name("web_search") is None


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
