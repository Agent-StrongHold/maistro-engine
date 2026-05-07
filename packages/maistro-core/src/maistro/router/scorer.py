"""Model scoring: quality^(qw*p) / cost^cw with speed and strength bonuses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from maistro.router.scarcity import compute_effective_cost
from maistro.router.speed import compute_speed_bonus

if TYPE_CHECKING:
    from maistro.types.config import RoutingConfig
    from maistro.types.intent import Intent
    from maistro.types.model import ModelCandidate, ModelConfig, ProviderConfig


def score_candidate(
    model_id: str,
    model_cfg: ModelConfig,
    provider_cfg: ProviderConfig,
    intent: Intent,
    routing_cfg: RoutingConfig,
    usage_pct: float,
) -> ModelCandidate:
    """Score a single model candidate.

    Formula: quality^(quality_weight * priority_mult) / effective_cost^cost_weight
    """
    from maistro.types.model import ModelCandidate

    quality_weight = routing_cfg.quality_weight
    cost_weight = routing_cfg.cost_weight
    priority_mult = routing_cfg.priority_multipliers.get(intent.tier, 1.0)

    quality_exponent = max(0.1, quality_weight * priority_mult)

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

    effective_cost = compute_effective_cost(usage_pct, provider_cfg)

    q_factor = adjusted_quality**quality_exponent
    c_factor = effective_cost**cost_weight
    score = q_factor / c_factor if c_factor > 0 else q_factor

    has_paygo = (
        provider_cfg.overage_cost_per_1k_input > 0 or provider_cfg.overage_cost_per_1k_output > 0
    )

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
