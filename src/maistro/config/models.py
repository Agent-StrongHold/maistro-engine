"""Configuration sub-models for provider tiers and compute budgets."""

from __future__ import annotations

import os
from enum import IntEnum

from pydantic import BaseModel


class Tier(IntEnum):
    """Compute tiers — higher tier = more capable model + more retries."""

    QUICK = 1      # Fast, cheap — single-shot with small model
    STANDARD = 2   # Default — good model, moderate retries
    THOROUGH = 3   # Multi-attempt with voting/ensemble
    ULTRA = 4      # Parallel generation + consensus voting (Ultra Think)


class TierConfig(BaseModel):
    """Per-tier model and retry configuration."""

    tier: Tier
    model: str
    max_retries: int = 3
    temperature: float = 0.0
    parallel_generations: int = 1  # >1 for ensemble (tier 3-4)


# Default tier configurations — overridable via config/env
# Uses local Ollama models by default (P40 24GB VRAM)
# Override with MAISTRO_TIER_*_MODEL env vars for cloud models
DEFAULT_TIERS: dict[Tier, TierConfig] = {
    Tier.QUICK: TierConfig(
        tier=Tier.QUICK,
        model=os.environ.get("MAISTRO_TIER_1_MODEL", "ollama/qwen2.5-coder:7b"),
        max_retries=1,
        temperature=0.0,
    ),
    Tier.STANDARD: TierConfig(
        tier=Tier.STANDARD,
        model=os.environ.get("MAISTRO_TIER_2_MODEL", "ollama/qwen2.5-coder:32b"),
        max_retries=3,
        temperature=0.0,
    ),
    Tier.THOROUGH: TierConfig(
        tier=Tier.THOROUGH,
        model=os.environ.get("MAISTRO_TIER_3_MODEL", "ollama/qwen3-coder-next:latest"),
        max_retries=5,
        temperature=0.3,
        parallel_generations=1,  # single-gen on P40 (VRAM-constrained)
    ),
    Tier.ULTRA: TierConfig(
        tier=Tier.ULTRA,
        model=os.environ.get("MAISTRO_TIER_4_MODEL", "ollama/qwen3-coder-next:latest"),
        max_retries=5,
        temperature=0.5,
        parallel_generations=1,  # single-gen on P40 (VRAM-constrained)
    ),
}
