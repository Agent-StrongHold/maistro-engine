"""Model scoring: quality^(qw*p) / normalized_cost^cw with speed and strength bonuses.

Cost normalization:
  Raw effective_cost from scarcity lives in (0, ~1.44] for in-budget models.
  Normalized to [0, 1] by dividing by the ceiling (1/ln(2) ≈ 1.44), so:
    - Huge budgets barely used → near 0 (but never clamped to exactly 0)
    - Budget nearly exhausted → near 1.0
    - Over-quota with paygo → >1.0 (penalty)

  cost_weight controls how much this matters:
    0.0 → cost ignored (pure quality)
    0.5 → cost and quality contribute equally at mid-range
    1.0 → cost dominates

Over-quota handling:
  Models over quota without paygo are FILTERED (return None, not scored).
  Models over quota with paygo get a cost penalty above 1.0.
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

# The in-budget cost ceiling from scarcity: 1/ln(2) ≈ 1.44 (budget nearly exhausted).
# Floor is 0 (effectively free — huge budget barely used). No hardcoded floor constant;
# any positive cost maps proportionally into [0, 1].
_COST_CEIL = 1.0 / math.log(2.0)  # ≈ 1.4427


def _normalize_cost(raw_cost: float) -> float:
    """Map raw effective_cost to [0, 1] within the in-budget range.

    0.0 = zero cost (provider.free_tokens=0 returns 1.0 from scarcity, mapped here)
    ~0.0 = huge budget barely used
    1.0 = most expensive in-budget (nearly exhausted, raw ≈ 1.44)
    >1.0 = over-quota with paygo (penalty territory)

    No hardcoded floor — providers with 100M and 1B budgets still differentiate
    because their raw costs (0.054 vs 0.048) map to different points on [0, 1].
    """
    if raw_cost <= 0:
        return 0.0
    if raw_cost >= _COST_CEIL:
        # Over-quota with paygo: scale linearly above 1.0
        return 1.0 + (raw_cost - _COST_CEIL)
    return raw_cost / _COST_CEIL


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
