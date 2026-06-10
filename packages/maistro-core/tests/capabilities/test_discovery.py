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
    assert reg.active_name("search") is None


def test_discover_skips_unknown_slot_gracefully():
    reg = CapabilityRegistry()  # no slots defined
    n = discover_into(reg, entry_points=[_FakeEP("plugin_search", _factory)])
    assert n == 0
