"""Durable recursive self-improvement campaigns.

The approved installed path is `AutonomousCampaign`: it pins a repository
commit, generates patches through a non-executing controller-side provider,
evaluates each patch in fresh VM-grade offline Builders workspaces, evolves
candidate strategy from objective feedback, and persists resumable evidence.
It has no publication capability.

`RsiCycle`, `MicroVmSandbox`, and self-branch exports remain as legacy
compatibility APIs. They are not the approved path for autonomous untrusted
execution.
"""

from __future__ import annotations

from maistro_rsi.campaign import AutonomousCampaign, CampaignConfig, CampaignState, CampaignStatus
from maistro_rsi.protocols import ApplyPatchFn, MicroVmSandbox
from maistro_rsi.runner import RsiCycle, RsiCycleConfig, RsiCycleResult

__all__ = [
    "ApplyPatchFn",
    "AutonomousCampaign",
    "CampaignConfig",
    "CampaignState",
    "CampaignStatus",
    "MicroVmSandbox",
    "RsiCycle",
    "RsiCycleConfig",
    "RsiCycleResult",
]
