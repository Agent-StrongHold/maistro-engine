"""7-tier episodic memory with enforced weight bounds (ADR-016)."""

from __future__ import annotations

from maistro.memory.types import (
    REINFORCE_DELTA,
    WEIGHT_BOUNDS,
    EpisodicMemory,
    MemoryTier,
)


def clamp_weight(tier: MemoryTier, proposed: float) -> float:
    """Clamp weight to tier bounds."""
    lo, hi = WEIGHT_BOUNDS.get(tier, (0.1, 1.0))
    return max(lo, min(hi, proposed))


def reinforce(memory: EpisodicMemory, delta: float = REINFORCE_DELTA) -> EpisodicMemory:
    """Return a new EpisodicMemory with increased weight, clamped to tier ceiling."""
    return EpisodicMemory(
        memory_id=memory.memory_id,
        tier=memory.tier,
        content=memory.content,
        weight=clamp_weight(memory.tier, memory.weight + delta),
        org_id=memory.org_id,
        team_id=memory.team_id,
        agent_id=memory.agent_id,
        user_id=memory.user_id,
        scope=memory.scope,
        source=memory.source,
        context=memory.context,
        reinforcement_count=memory.reinforcement_count + 1,
        contradiction_count=memory.contradiction_count,
        created_at=memory.created_at,
        last_accessed_at=memory.last_accessed_at,
        deleted=memory.deleted,
    )


def decay(memory: EpisodicMemory, delta: float = REINFORCE_DELTA) -> EpisodicMemory:
    """Return a new EpisodicMemory with decreased weight, clamped to tier floor."""
    return EpisodicMemory(
        memory_id=memory.memory_id,
        tier=memory.tier,
        content=memory.content,
        weight=clamp_weight(memory.tier, memory.weight - delta),
        org_id=memory.org_id,
        team_id=memory.team_id,
        agent_id=memory.agent_id,
        user_id=memory.user_id,
        scope=memory.scope,
        source=memory.source,
        context=memory.context,
        reinforcement_count=memory.reinforcement_count,
        contradiction_count=memory.contradiction_count + 1,
        created_at=memory.created_at,
        last_accessed_at=memory.last_accessed_at,
        deleted=memory.deleted,
    )
