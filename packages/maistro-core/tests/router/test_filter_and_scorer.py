"""Gap-filler tests for router filter and scorer (from codebase-wide mutation scan)."""

from __future__ import annotations

from maistro.router.filter import (
    _modality_matches,
    _quota_allows,
    _tier_in_range,
    filter_candidates,
)
from maistro.router.scorer import score_candidate
from maistro.types.config import RoutingConfig
from maistro.types.intent import Intent
from maistro.types.model import ModelConfig, ProviderConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _intent(**kw) -> Intent:
    defaults = dict(
        task_type="chat", tier="P2", min_tier="small", max_tier=None, preferred_strengths=("chat",)
    )
    return Intent(**{**defaults, **kw})


def _provider(**kw) -> ProviderConfig:
    defaults = dict(status="active", billing_cycle="monthly", free_tokens=100_000)
    return ProviderConfig(**{**defaults, **kw})


def _model(**kw) -> ModelConfig:
    defaults = dict(
        provider="openai",
        tier="medium",
        quality=0.8,
        speed=200,
        modality="text",
        strengths=("chat",),
    )
    return ModelConfig(**{**defaults, **kw})


def _routing() -> RoutingConfig:
    return RoutingConfig()


# ---------------------------------------------------------------------------
# _modality_matches — missing complement paths
# ---------------------------------------------------------------------------


class TestModalityMatches:
    def test_image_gen_task_accepts_image_gen_model(self):
        assert _modality_matches("image_gen", "image_gen") is True

    def test_image_gen_task_rejects_text_model(self):
        # complement: text model must NOT handle image_gen tasks
        assert _modality_matches("image_gen", "text") is False

    def test_embedding_task_accepts_embedding_model(self):
        assert _modality_matches("embedding", "embedding") is True

    def test_embedding_task_rejects_text_model(self):
        # complement: text model must NOT handle embedding tasks
        assert _modality_matches("embedding", "text") is False

    def test_chat_task_rejects_image_gen_model(self):
        # text/chat tasks must NOT route to image_gen models
        assert _modality_matches("chat", "image_gen") is False

    def test_chat_task_rejects_embedding_model(self):
        # text/chat tasks must NOT route to embedding models
        assert _modality_matches("chat", "embedding") is False

    def test_chat_task_accepts_text_model(self):
        assert _modality_matches("chat", "text") is True

    def test_code_task_accepts_text_model(self):
        assert _modality_matches("code", "text") is True


# ---------------------------------------------------------------------------
# _tier_in_range — boundary and max_tier=None
# ---------------------------------------------------------------------------


class TestTierInRange:
    def test_max_tier_none_accepts_any_tier(self):
        intent = _intent(min_tier="small", max_tier=None)
        assert _tier_in_range("frontier", intent) is True

    def test_below_min_tier_rejected(self):
        intent = _intent(min_tier="medium", max_tier=None)
        assert _tier_in_range("small", intent) is False

    def test_at_min_tier_accepted(self):
        intent = _intent(min_tier="medium", max_tier=None)
        assert _tier_in_range("medium", intent) is True

    def test_at_max_tier_accepted(self):
        intent = _intent(min_tier="small", max_tier="large")
        assert _tier_in_range("large", intent) is True

    def test_above_max_tier_rejected(self):
        intent = _intent(min_tier="small", max_tier="large")
        assert _tier_in_range("frontier", intent) is False

    def test_unknown_tier_rank_defaults_to_zero(self):
        # unknown tier has rank 0; if min_tier="small" (rank 0), it should pass
        intent = _intent(min_tier="small", max_tier=None)
        assert _tier_in_range("unknown_tier", intent) is True


# ---------------------------------------------------------------------------
# _quota_allows — both False paths
# ---------------------------------------------------------------------------


class TestQuotaAllows:
    def test_below_limit_no_paygo_allows(self):
        provider = _provider(overage_cost_per_1k_input=0.0, overage_cost_per_1k_output=0.0)
        intent = _intent(tier="P2")
        assert _quota_allows(provider, 0.5, intent, 0.05) is True

    def test_at_100pct_no_paygo_blocks(self):
        # usage_pct >= 1.0 and no paygo → False
        provider = _provider(overage_cost_per_1k_input=0.0, overage_cost_per_1k_output=0.0)
        intent = _intent(tier="P2")
        assert _quota_allows(provider, 1.0, intent, 0.05) is False

    def test_at_100pct_with_paygo_allows(self):
        # paygo provider can still serve even at 100%
        provider = _provider(overage_cost_per_1k_input=0.001, overage_cost_per_1k_output=0.002)
        intent = _intent(tier="P2")
        assert _quota_allows(provider, 1.0, intent, 0.05) is True

    def test_in_reserve_band_non_p0_no_paygo_blocks(self):
        # usage_pct >= (1 - reserve_pct) and tier != P0 and no paygo → False
        provider = _provider(overage_cost_per_1k_input=0.0, overage_cost_per_1k_output=0.0)
        intent = _intent(tier="P2")
        assert _quota_allows(provider, 0.96, intent, 0.05) is False

    def test_in_reserve_band_p0_allows(self):
        # P0 bypasses reserve check
        provider = _provider(overage_cost_per_1k_input=0.0, overage_cost_per_1k_output=0.0)
        intent = _intent(tier="P0")
        assert _quota_allows(provider, 0.96, intent, 0.05) is True

    def test_in_reserve_band_with_paygo_allows(self):
        # paygo provider bypasses reserve check
        provider = _provider(overage_cost_per_1k_input=0.001)
        intent = _intent(tier="P2")
        assert _quota_allows(provider, 0.96, intent, 0.05) is True


# ---------------------------------------------------------------------------
# score_candidate — formula and strength_mult branches
# ---------------------------------------------------------------------------


class TestScoreCandidate:
    def test_score_is_positive(self):
        candidate = score_candidate("model-1", _model(), _provider(), _intent(), _routing(), 0.0)
        assert candidate.score > 0.0

    def test_matching_strengths_gives_higher_score_than_empty(self):
        # strength_mult 1.15 when preferred & model_strengths overlap
        intent = _intent(preferred_strengths=("chat",))
        with_match = score_candidate(
            "m1", _model(strengths=("chat",)), _provider(), intent, _routing(), 0.0
        )
        no_strengths = score_candidate(
            "m2", _model(strengths=()), _provider(), intent, _routing(), 0.0
        )
        # matching strengths → higher score (1.15 mult) than no strengths (1.0 mult)
        assert with_match.score > no_strengths.score

    def test_non_matching_strengths_gives_lower_score(self):
        # strength_mult 0.90 when model has strengths but none match preferred
        intent = _intent(preferred_strengths=("code",))
        mismatch = score_candidate(
            "m1", _model(strengths=("chat",)), _provider(), intent, _routing(), 0.0
        )
        no_strengths = score_candidate(
            "m2", _model(strengths=()), _provider(), intent, _routing(), 0.0
        )
        # mismatch (0.90) < no_strengths (1.0)
        assert mismatch.score < no_strengths.score

    def test_priority_mult_widens_quality_gap(self):
        # Higher priority (P0) amplifies quality differences between models.
        # At P0 (exponent=0.9) the ratio high_q/low_q is larger than at P5 (exponent=0.42).
        intent_p0 = _intent(tier="P0")
        intent_p5 = _intent(tier="P5")
        high_q = _model(quality=0.9, strengths=())
        low_q = _model(quality=0.5, strengths=())
        s_high_p0 = score_candidate("h", high_q, _provider(), intent_p0, _routing(), 0.0)
        s_low_p0 = score_candidate("l", low_q, _provider(), intent_p0, _routing(), 0.0)
        s_high_p5 = score_candidate("h", high_q, _provider(), intent_p5, _routing(), 0.0)
        s_low_p5 = score_candidate("l", low_q, _provider(), intent_p5, _routing(), 0.0)
        ratio_p0 = s_high_p0.score / s_low_p0.score
        ratio_p5 = s_high_p5.score / s_low_p5.score
        # P0 must widen the gap between good and bad models
        assert ratio_p0 > ratio_p5

    def test_has_paygo_flag_reflects_provider(self):
        paygo = _provider(overage_cost_per_1k_input=0.001)
        no_paygo = _provider(overage_cost_per_1k_input=0.0, overage_cost_per_1k_output=0.0)
        c_paygo = score_candidate("m", _model(), paygo, _intent(), _routing(), 0.0)
        c_no = score_candidate("m", _model(), no_paygo, _intent(), _routing(), 0.0)
        assert c_paygo.has_paygo is True
        assert c_no.has_paygo is False

    def test_quality_clamped_to_1(self):
        # base_quality=0.95 * 1.15 would exceed 1.0 without clamp
        intent = _intent(preferred_strengths=("chat",))
        candidate = score_candidate(
            "m", _model(quality=0.95, strengths=("chat",)), _provider(), intent, _routing(), 0.0
        )
        assert candidate.quality <= 1.0


# ---------------------------------------------------------------------------
# filter_candidates — inactive provider and modality exclusion
# ---------------------------------------------------------------------------


class TestFilterCandidates:
    def test_inactive_provider_excluded(self):
        intent = _intent()
        models = {"m1": _model(provider="inactive_p")}
        providers = {"inactive_p": _provider(status="inactive")}
        result = filter_candidates(intent, models, providers)
        assert result == []

    def test_wrong_modality_excluded(self):
        intent = _intent(task_type="chat")
        models = {"img": _model(modality="image_gen", provider="p")}
        providers = {"p": _provider()}
        result = filter_candidates(intent, models, providers)
        assert result == []

    def test_quota_exhausted_excluded(self):
        intent = _intent(tier="P2")
        models = {"m": _model(provider="p")}
        providers = {"p": _provider(overage_cost_per_1k_input=0.0, overage_cost_per_1k_output=0.0)}
        result = filter_candidates(intent, models, providers, usage_pcts={"p": 1.0})
        assert result == []

    def test_valid_model_included(self):
        intent = _intent()
        models = {"m": _model(provider="p")}
        providers = {"p": _provider()}
        result = filter_candidates(intent, models, providers)
        assert len(result) == 1
        assert result[0][0] == "m"
