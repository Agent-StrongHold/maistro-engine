"""Tests for sandbox selector — fail-closed, tier ordering, policy enforcement."""

import pytest

from maistro.sandbox.backends.fake import FakeSandboxBackend
from maistro.sandbox.policy import (
    BENCHMARK_EVAL,
    DEV_ONLY,
    TRUSTED_TOOL,
    UNTRUSTED_CODE,
    tier_satisfies,
)
from maistro.sandbox.selector import NoSuitableBackendError, SandboxSelector


class TestTierSatisfies:
    def test_vm_satisfies_vm(self):
        assert tier_satisfies("vm", "vm") is True

    def test_vm_satisfies_container(self):
        assert tier_satisfies("vm", "container") is True

    def test_container_does_not_satisfy_vm(self):
        assert tier_satisfies("container", "vm") is False

    def test_fake_satisfies_fake(self):
        assert tier_satisfies("fake", "fake") is True

    def test_fake_does_not_satisfy_anything_real(self):
        assert tier_satisfies("fake", "container") is False
        assert tier_satisfies("fake", "vm") is False


class TestSelectorFailClosed:
    def test_empty_registry_refuses_any_workload(self):
        sel = SandboxSelector()
        with pytest.raises(NoSuitableBackendError):
            sel.select(UNTRUSTED_CODE)

    def test_fake_backend_refuses_untrusted_code(self):
        sel = SandboxSelector()
        sel.register("fake", FakeSandboxBackend())
        with pytest.raises(NoSuitableBackendError, match="min_tier='vm'"):
            sel.select(UNTRUSTED_CODE)

    def test_fake_backend_refuses_benchmark_eval(self):
        sel = SandboxSelector()
        sel.register("fake", FakeSandboxBackend())
        with pytest.raises(NoSuitableBackendError):
            sel.select(BENCHMARK_EVAL)

    def test_container_backend_refuses_vm_requirement(self):
        sel = SandboxSelector()
        sel.register("container", FakeSandboxBackend())
        with pytest.raises(NoSuitableBackendError):
            sel.select(UNTRUSTED_CODE)


class TestSelectorSelection:
    def test_fake_backend_accepts_dev_only(self):
        sel = SandboxSelector()
        sel.register("fake", FakeSandboxBackend())
        tier, _ = sel.select(DEV_ONLY)
        assert tier == "fake"

    def test_vm_backend_accepts_untrusted_code(self):
        sel = SandboxSelector()
        fake_vm = FakeSandboxBackend()
        sel.register("vm", fake_vm)
        tier, backend = sel.select(UNTRUSTED_CODE)
        assert tier == "vm"
        assert backend is fake_vm

    def test_strongest_available_is_chosen(self):
        sel = SandboxSelector()
        sel.register("container", FakeSandboxBackend())
        sel.register("vm", FakeSandboxBackend())
        # For a TRUSTED_TOOL (min_tier=container), the VM is still chosen (strongest)
        tier, _ = sel.select(TRUSTED_TOOL)
        assert tier == "vm"

    def test_container_satisfies_trusted_tool(self):
        sel = SandboxSelector()
        sel.register("container", FakeSandboxBackend())
        tier, _ = sel.select(TRUSTED_TOOL)
        assert tier == "container"

    def test_available_tiers_ordered_strongest_first(self):
        sel = SandboxSelector()
        sel.register("fake", FakeSandboxBackend())
        sel.register("vm", FakeSandboxBackend())
        sel.register("container", FakeSandboxBackend())
        assert sel.available_tiers == ["vm", "container", "fake"]


class TestNoSilentDowngrade:
    """The core security property: no workload ever silently runs at a weaker tier."""

    def test_no_downgrade_from_vm_to_container(self):
        sel = SandboxSelector()
        sel.register("container", FakeSandboxBackend())
        sel.register("bubblewrap", FakeSandboxBackend())
        # UNTRUSTED_CODE requires vm — having container+bubblewrap is NOT enough
        with pytest.raises(NoSuitableBackendError):
            sel.select(UNTRUSTED_CODE)

    def test_explicit_error_message_names_the_gap(self):
        sel = SandboxSelector()
        sel.register("container", FakeSandboxBackend())
        with pytest.raises(NoSuitableBackendError, match="requires min_tier='vm'"):
            sel.select(UNTRUSTED_CODE)
