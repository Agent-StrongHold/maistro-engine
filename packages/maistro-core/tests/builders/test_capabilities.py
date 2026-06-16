"""Builders capability posture tests."""

from maistro.builders.capabilities import (
    SECURE_BUILDERS_CAPABILITIES,
    ApprovalMode,
    CapabilityState,
    capability_counts,
)


def test_secure_profile_preserves_core_coding_capabilities() -> None:
    states = {capability.name: capability.state for capability in SECURE_BUILDERS_CAPABILITIES}
    assert states["workspace_read_write"] is CapabilityState.AVAILABLE
    assert states["terminal_and_preinstalled_tools"] is CapabilityState.AVAILABLE
    assert states["git_local"] is CapabilityState.AVAILABLE
    assert states["durable_resume"] is CapabilityState.AVAILABLE
    assert states["model_inference"] is CapabilityState.AVAILABLE


def test_external_capabilities_require_brokers_not_ambient_access() -> None:
    states = {capability.name: capability.state for capability in SECURE_BUILDERS_CAPABILITIES}
    assert states["dependency_fetch"] is CapabilityState.BROKER_REQUIRED
    assert states["research_and_docs"] is CapabilityState.BROKER_REQUIRED
    assert states["private_repositories"] is CapabilityState.BROKER_REQUIRED
    assert states["mcp_and_external_tools"] is CapabilityState.BROKER_REQUIRED
    assert states["browser_automation"] is CapabilityState.BROKER_REQUIRED


def test_dangerous_controller_capabilities_remain_prohibited() -> None:
    states = {capability.name: capability.state for capability in SECURE_BUILDERS_CAPABILITIES}
    assert states["host_filesystem"] is CapabilityState.PROHIBITED
    assert states["host_runtime_socket"] is CapabilityState.PROHIBITED
    assert states["direct_push_or_merge"] is CapabilityState.PROHIBITED
    assert sum(capability_counts().values()) == len(SECURE_BUILDERS_CAPABILITIES)


def test_normal_coding_is_autonomous_and_boundary_crossings_use_leases() -> None:
    approvals = {
        capability.name: capability.approval for capability in SECURE_BUILDERS_CAPABILITIES
    }
    assert approvals["workspace_read_write"] is ApprovalMode.AUTONOMOUS
    assert approvals["terminal_and_preinstalled_tools"] is ApprovalMode.AUTONOMOUS
    assert approvals["git_local"] is ApprovalMode.AUTONOMOUS
    assert approvals["dependency_fetch"] is ApprovalMode.SESSION_LEASE
    assert approvals["research_and_docs"] is ApprovalMode.SESSION_LEASE
    assert approvals["direct_push_or_merge"] is ApprovalMode.PER_ACTION


def test_evolve_and_rsi_are_autonomous_until_promotion() -> None:
    capabilities = {
        capability.name: capability for capability in SECURE_BUILDERS_CAPABILITIES
    }
    assert capabilities["evolve_benchmark_evaluation"].approval is ApprovalMode.AUTONOMOUS
    assert capabilities["rsi_candidate_generation"].approval is ApprovalMode.AUTONOMOUS
    assert capabilities["rsi_candidate_promotion"].approval is ApprovalMode.PER_ACTION
