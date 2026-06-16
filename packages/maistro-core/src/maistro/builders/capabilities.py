"""Builders capability posture for secure interactive coding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CapabilityState(StrEnum):
    """How a Claude Code-style capability is currently delivered."""

    AVAILABLE = "available"
    BROKER_REQUIRED = "broker_required"
    PLANNED = "planned"
    PROHIBITED = "prohibited"


class ApprovalMode(StrEnum):
    """When a human/controller approval is required."""

    AUTONOMOUS = "autonomous"
    SESSION_LEASE = "session_lease"
    PER_ACTION = "per_action"
    NEVER = "never"


@dataclass(frozen=True)
class BuilderCapability:
    """One capability and its security delivery model."""

    name: str
    state: CapabilityState
    approval: ApprovalMode
    delivery: str


SECURE_BUILDERS_CAPABILITIES = (
    BuilderCapability(
        "workspace_read_write",
        CapabilityState.AVAILABLE,
        ApprovalMode.AUTONOMOUS,
        "Fresh writable workspace inside an offline VM",
    ),
    BuilderCapability(
        "terminal_and_preinstalled_tools",
        CapabilityState.AVAILABLE,
        ApprovalMode.AUTONOMOUS,
        "Arbitrary argv execution inside the offline VM; project dependencies require the broker",
    ),
    BuilderCapability(
        "git_local",
        CapabilityState.AVAILABLE,
        ApprovalMode.AUTONOMOUS,
        "Diff, branch, commit, and status inside the VM; push is prohibited",
    ),
    BuilderCapability(
        "durable_resume",
        CapabilityState.AVAILABLE,
        ApprovalMode.AUTONOMOUS,
        "Replay pinned base commit plus exported patch into a fresh offline VM",
    ),
    BuilderCapability(
        "model_inference",
        CapabilityState.AVAILABLE,
        ApprovalMode.SESSION_LEASE,
        "Controller calls the configured model gateway; model credentials never enter the VM",
    ),
    BuilderCapability(
        "dependency_fetch",
        CapabilityState.BROKER_REQUIRED,
        ApprovalMode.SESSION_LEASE,
        "Disposable allowlisted egress VM returns a scanned dependency/cache artifact",
    ),
    BuilderCapability(
        "research_and_docs",
        CapabilityState.BROKER_REQUIRED,
        ApprovalMode.SESSION_LEASE,
        "Read-only network broker returns sanitized content to the agent",
    ),
    BuilderCapability(
        "private_repositories",
        CapabilityState.BROKER_REQUIRED,
        ApprovalMode.SESSION_LEASE,
        "Short-lived clone credential is scoped to the materialization VM and then destroyed",
    ),
    BuilderCapability(
        "mcp_and_external_tools",
        CapabilityState.BROKER_REQUIRED,
        ApprovalMode.SESSION_LEASE,
        "Allowlisted controller-side tools with explicit authorization and audit records",
    ),
    BuilderCapability(
        "browser_automation",
        CapabilityState.BROKER_REQUIRED,
        ApprovalMode.SESSION_LEASE,
        "Separate browser sandbox; never the code-execution VM",
    ),
    BuilderCapability(
        "service_integration_tests",
        CapabilityState.PLANNED,
        ApprovalMode.SESSION_LEASE,
        "Per-session isolated service lab with no host or public-network reachability",
    ),
    BuilderCapability(
        "evolve_benchmark_evaluation",
        CapabilityState.PLANNED,
        ApprovalMode.AUTONOMOUS,
        "Fresh benchmark VMs evaluate pinned base/candidate artifacts; promotion is separate",
    ),
    BuilderCapability(
        "rsi_candidate_generation",
        CapabilityState.PLANNED,
        ApprovalMode.AUTONOMOUS,
        "Fresh Builder VMs generate and save candidate patches without remote mutation",
    ),
    BuilderCapability(
        "rsi_candidate_promotion",
        CapabilityState.PLANNED,
        ApprovalMode.PER_ACTION,
        "External publisher requires quarantine, trustworthy benchmark evidence, and approval",
    ),
    BuilderCapability(
        "host_filesystem",
        CapabilityState.PROHIBITED,
        ApprovalMode.NEVER,
        "No raw host paths are exposed to generated code",
    ),
    BuilderCapability(
        "host_runtime_socket",
        CapabilityState.PROHIBITED,
        ApprovalMode.NEVER,
        "No Docker, containerd, Podman, or VM-control socket is exposed",
    ),
    BuilderCapability(
        "direct_push_or_merge",
        CapabilityState.PROHIBITED,
        ApprovalMode.PER_ACTION,
        "Only a separate reviewed publisher may change the remote repository",
    ),
)


def capability_counts() -> dict[CapabilityState, int]:
    """Return the current capability posture counts for status surfaces."""
    return {
        state: sum(capability.state is state for capability in SECURE_BUILDERS_CAPABILITIES)
        for state in CapabilityState
    }
