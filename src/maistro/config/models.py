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


# MIN-07: Tier defaults — env vars are read lazily via get_tier_config()
_TIER_DEFAULTS: dict[Tier, dict[str, str | int | float]] = {
    Tier.QUICK: {
        "env": "MAISTRO_TIER_1_MODEL",
        "default": "ollama/qwen2.5-coder:7b",
        "max_retries": 1,
        "temperature": 0.0,
    },
    Tier.STANDARD: {
        "env": "MAISTRO_TIER_2_MODEL",
        "default": "ollama/qwen2.5-coder:32b",
        "max_retries": 3,
        "temperature": 0.0,
    },
    Tier.THOROUGH: {
        "env": "MAISTRO_TIER_3_MODEL",
        "default": "ollama/qwen3-coder-next:latest",
        "max_retries": 5,
        "temperature": 0.3,
    },
    Tier.ULTRA: {
        "env": "MAISTRO_TIER_4_MODEL",
        "default": "ollama/qwen3-coder-next:latest",
        "max_retries": 5,
        "temperature": 0.5,
    },
}


def get_tier_config(tier: int | None = None) -> TierConfig:
    """Build tier config lazily, reading env vars at call time."""
    t = Tier(tier) if tier and tier in [e.value for e in Tier] else Tier.STANDARD
    defaults = _TIER_DEFAULTS[t]
    model = os.environ.get(str(defaults["env"]), str(defaults["default"]))
    return TierConfig(
        tier=t,
        model=model,
        max_retries=int(defaults["max_retries"]),
        temperature=float(defaults["temperature"]),
    )


# Legacy alias for backwards compat
DEFAULT_TIERS: dict[Tier, TierConfig] = {t: get_tier_config(t) for t in Tier}
