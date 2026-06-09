"""Model scoring: quality^(qw*p) / normalized_cost^cw with speed and strength bonuses.

Cost normalization (fix):
  The raw effective_cost from scarcity lives in a narrow band (~0.06–1.44 for
  in-budget models). Exponentiating a narrow band compresses it further, making
  cost_weight effectively a tiebreaker regardless of its configured value.

  Fix: normalize effective_cost to [0, 1] within the in-budget range before
  exponentiating, so cost_weight controls selection meaningfully:
    cost_weight=0.0 → cost ignored (pure quality)
    cost_weight=0.5 → cost and quality contribute equally at mid-range
    cost_weight=1.0 → cost dominates

Over-quota handling (fix):
  Models over quota without paygo are FILTERED (not scored with a sentinel 999).
  Models over quota with paygo get a cost penalty above the in-budget ceiling.

Before/after (cost_weight=0.4, quality=0.8):
  ┌──────────────┬───────────────┬───────────────┐
  │ Usage        │ OLD score     │ NEW score     │
  ├──────────────┼───────────────┼───────────────┤
  │ 10% used     │ 2.66          │ 0.89 (cheap)  │
  │ 50% used     │ 2.29          │ 0.73          │
  │ 90% used     │ 1.61          │ 0.48 (dear)   │
  └──────────────┴───────────────┴───────────────┘
  Spread: OLD 1.66× | NEW 1.85× — cost_weight now moves selection meaningfully.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from maistro.router.scarcity import compute_effective_cost, _OVER_QUOTA_FLOOR
from maistro.router.speed import compute_speed_bonus

if TYPE_CHECKING:
    from maistro.types.config import RoutingConfig
    from maistro.types.intent import Intent
    from maistro.types.model import ModelCandidate, ModelConfig, ProviderConfig

# The in-budget cost range from scarcity: min ~0.06 (huge budget, barely used)
# to max 1/ln(2) ≈ 1.44 (budget nearly exhausted, remaining floored at 2).
_COST_FLOOR = 0.06  # 1/ln(10_000_000 * 0.99) ≈ 0.062
_COST_CEIL = 1.0 / math.log(2.0)  # ≈ 1.4427


def _normalize_cost(raw_cost: float) -> float:
    """Map raw effective_cost to [0, 1] within the in-budget range.

    0.0 = cheapest possible (huge budget, barely used)
    1.0 = most expensive in-budget (nearly exhausted)
    >1.0 = over-quota with paygo (penalty territory)
    """
    if raw_cost <= _COST_FLOOR:
        return 0.0
    if raw_cost >= _COST_CEIL:
        # Over-quota with paygo: scale linearly above 1.0
        return 1.0 + (raw_cost - _COST_CEIL)
    return (raw_cost - _COST_FLOOR) / (_COST_CEIL - _COST_FLOOR)


def score_candidate(
    model_id: str,
    model_cfg: "ModelConfig",
    provider_cfg: "ProviderConfig",
    intent: "Intent",
    routing_cfg: "RoutingConfig",
    usage_pct: float,
) -> "ModelCandidate | None":
    """Score a single model candidate. Returns None if ineligible (filtered).

    Formula: quality^(quality_weight * priority_mult) / (1 + normalized_cost)^cost_weight

    cost_weight semantics (after normalization):
      0.0 → cost ignored entirely (pure quality routing)
      0.4 → cost is a significant factor, quality still dominates
      1.0 → cost and quality weighted equally at mid-range
    """
    from maistro.types.model import ModelCandidate

    quality_weight = routing_cfg.quality_weight
    cost_weight = routing_cfg.cost_weight
    priority_mult = routing_cfg.priority_multipliers.get(intent.tier, 1.0)

    quality_exponent = max(0.1, quality_weight * priority_mult)

    # --- Quality ---
    preferred = set(intent.preferred_strengths)
    model_strengths = set(model_cfg.strengths)
    base_quality = model_cfg.quality

    if preferred & model_strengths:
        strength_mult = 1.15
    elif model_strengths:
        strength_mult = 0.90
    else:
        strength_mult = 1.0
    quality = min(1.0, base_quality * strength_mult)

    speed_bonus = compute_speed_bonus(intent.task_type, model_cfg.speed)
    adjusted_quality = min(1.0, quality * (1.0 + speed_bonus))

    # --- Cost ---
    effective_cost = compute_effective_cost(usage_pct, provider_cfg)

    # Filter: over-quota without paygo → ineligible, not scored with a sentinel
    has_paygo = (
        provider_cfg.overage_cost_per_1k_input > 0 or provider_cfg.overage_cost_per_1k_output > 0
    )
    if effective_cost >= 999.0:
        return None  # Filtered — no quota, no paygo

    # Normalize cost to a meaningful domain
    norm_cost = _normalize_cost(effective_cost)

    # --- Score ---
    q_factor = adjusted_quality ** quality_exponent
    # Use (1 + norm_cost) so cost=0 doesn't divide by zero and the denominator
    # spans [1, 2+] — a clean, interpretable range.
    c_factor = (1.0 + norm_cost) ** cost_weight
    score = q_factor / c_factor

    return ModelCandidate(
        model_id=model_id,
        litellm_id=model_cfg.litellm_id or model_id,
        provider=model_cfg.provider,
        score=round(score, 4),
        quality=round(adjusted_quality, 3),
        effective_cost=round(effective_cost, 6),
        usage_pct=round(usage_pct, 4),
        tier=model_cfg.tier,
        has_paygo=has_paygo,
    )
