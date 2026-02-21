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


# Tier defaults — env vars are read lazily via get_tier_config() so that
# changes to the environment after import are respected.
_TIER_DEFAULTS: dict[Tier, dict[str, object]] = {
    Tier.QUICK: dict(
        env_var="MAISTRO_TIER_1_MODEL",
        fallback="ollama/qwen2.5-coder:7b",
        max_retries=1,
        temperature=0.0,
    ),
    Tier.STANDARD: dict(
        env_var="MAISTRO_TIER_2_MODEL",
        fallback="ollama/qwen2.5-coder:32b",
        max_retries=3,
        temperature=0.0,
    ),
    Tier.THOROUGH: dict(
        env_var="MAISTRO_TIER_3_MODEL",
        fallback="ollama/qwen3-coder-next:latest",
        max_retries=5,
        temperature=0.3,
        parallel_generations=1,
    ),
    Tier.ULTRA: dict(
        env_var="MAISTRO_TIER_4_MODEL",
        fallback="ollama/qwen3-coder-next:latest",
        max_retries=5,
        temperature=0.5,
        parallel_generations=1,
    ),
}


def get_tier_config(tier: Tier | int | None = None) -> TierConfig:
    """Build a TierConfig, reading env vars at call time (not import time)."""
    t = Tier(tier) if tier and tier in [e.value for e in Tier] else Tier.STANDARD
    defaults = _TIER_DEFAULTS[t]
    model = os.environ.get(
        str(defaults["env_var"]), str(defaults["fallback"])
    )
    return TierConfig(
        tier=t,
        model=model,
        max_retries=int(defaults.get("max_retries", 3)),  # type: ignore[arg-type]
        temperature=float(defaults.get("temperature", 0.0)),  # type: ignore[arg-type]
        parallel_generations=int(defaults.get("parallel_generations", 1)),  # type: ignore[arg-type]
    )


# Keep DEFAULT_TIERS for backward compatibility, but document it's a snapshot
DEFAULT_TIERS: dict[Tier, TierConfig] = {t: get_tier_config(t) for t in Tier}
