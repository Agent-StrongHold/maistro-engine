"""Tests for router scorer — normalization boundaries, over-quota filter, ordering."""

from __future__ import annotations

import math
from typing import ClassVar

import pytest

from maistro.router.scorer import _COST_CEIL, _normalize_cost, score_candidate

# ─── _normalize_cost boundaries ──────────────────────────────────────────────


class TestNormalizeCost:
    def test_zero_returns_zero(self):
        assert _normalize_cost(0.0) == 0.0

    def test_negative_returns_zero(self):
        assert _normalize_cost(-1.0) == 0.0

    def test_at_ceil_returns_one(self):
        assert _normalize_cost(_COST_CEIL) == pytest.approx(1.0, abs=0.01)

    def test_above_ceil_returns_above_one(self):
        # Over-quota paygo territory
        result = _normalize_cost(_COST_CEIL + 0.5)
        assert result > 1.0
        assert result == pytest.approx(1.5, abs=0.01)

    def test_mid_range_is_proportional(self):
        mid = _COST_CEIL / 2
        result = _normalize_cost(mid)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_large_budget_still_differentiates(self):
        """100M and 1B budgets produce DIFFERENT normalized costs (no floor clamp)."""
        raw_100m = 1.0 / math.log(100_000_000 * 0.9)
        raw_1b = 1.0 / math.log(1_000_000_000 * 0.9)
        norm_100m = _normalize_cost(raw_100m)
        norm_1b = _normalize_cost(raw_1b)
        # Both are tiny but distinct
        assert norm_100m > norm_1b
        assert norm_100m > 0
        assert norm_1b > 0

    def test_small_budget_high_usage_near_one(self):
        """1K budget at 99% → near ceiling."""
        remaining = 1000 * 0.01
        raw = 1.0 / math.log(max(remaining, 2.0))
        result = _normalize_cost(raw)
        assert 0.2 < result < 1.0


# ─── score_candidate filter ─────────────────────────────────────────────────


class FakeModelCfg:
    def __init__(self, quality=0.8):
        self.quality = quality
        self.strengths = ["coding"]
        self.speed = 0.7
        self.litellm_id = "test-model"
        self.provider = "azure"
        self.tier = "pro"


class FakeProviderCfg:
    def __init__(self, free_tokens=10000, paygo=False):
        self.free_tokens = free_tokens
        self.billing_cycle = "daily"
        self.overage_cost_per_1k_input = 0.01 if paygo else 0
        self.overage_cost_per_1k_output = 0.02 if paygo else 0


class FakeIntent:
    tier = "standard"
    preferred_strengths: ClassVar[list[str]] = ["coding"]
    task_type = "code"


class FakeRoutingCfg:
    quality_weight = 1.0
    cost_weight = 0.4
    priority_multipliers: ClassVar[dict[str, float]] = {"standard": 1.0}


class TestScoreCandidate:
    def test_over_quota_no_paygo_returns_none(self):
        """Over quota without paygo → filtered (None), not scored."""
        result = score_candidate(
            "m1",
            FakeModelCfg(),
            FakeProviderCfg(free_tokens=1000, paygo=False),
            FakeIntent(),
            FakeRoutingCfg(),
            usage_pct=1.5,
        )
        assert result is None

    def test_over_quota_with_paygo_returns_penalized_score(self):
        """Over quota with paygo → scored, but penalized (lower than in-budget)."""
        in_budget = score_candidate(
            "m1",
            FakeModelCfg(),
            FakeProviderCfg(free_tokens=10000, paygo=True),
            FakeIntent(),
            FakeRoutingCfg(),
            usage_pct=0.5,
        )
        over_quota = score_candidate(
            "m1",
            FakeModelCfg(),
            FakeProviderCfg(free_tokens=10000, paygo=True),
            FakeIntent(),
            FakeRoutingCfg(),
            usage_pct=1.5,
        )
        assert in_budget is not None
        assert over_quota is not None
        assert over_quota.score < in_budget.score

    def test_lower_usage_scores_higher(self):
        """Less usage → cheaper → higher score."""
        low = score_candidate(
            "m1",
            FakeModelCfg(),
            FakeProviderCfg(free_tokens=10000),
            FakeIntent(),
            FakeRoutingCfg(),
            usage_pct=0.1,
        )
        high = score_candidate(
            "m1",
            FakeModelCfg(),
            FakeProviderCfg(free_tokens=10000),
            FakeIntent(),
            FakeRoutingCfg(),
            usage_pct=0.9,
        )
        assert low is not None and high is not None
        assert low.score > high.score

    def test_higher_quality_scores_higher(self):
        """Better quality → higher score at same cost."""
        good = score_candidate(
            "m1",
            FakeModelCfg(quality=0.95),
            FakeProviderCfg(free_tokens=10000),
            FakeIntent(),
            FakeRoutingCfg(),
            usage_pct=0.5,
        )
        bad = score_candidate(
            "m1",
            FakeModelCfg(quality=0.5),
            FakeProviderCfg(free_tokens=10000),
            FakeIntent(),
            FakeRoutingCfg(),
            usage_pct=0.5,
        )
        assert good is not None and bad is not None
        assert good.score > bad.score

    def test_cost_weight_zero_ignores_cost(self):
        """cost_weight=0 → same score regardless of usage."""

        class NoCostRouting:
            quality_weight = 1.0
            cost_weight = 0.0
            priority_multipliers: ClassVar[dict[str, float]] = {"standard": 1.0}

        cheap = score_candidate(
            "m1",
            FakeModelCfg(),
            FakeProviderCfg(free_tokens=10000),
            FakeIntent(),
            NoCostRouting(),
            usage_pct=0.1,
        )
        dear = score_candidate(
            "m1",
            FakeModelCfg(),
            FakeProviderCfg(free_tokens=10000),
            FakeIntent(),
            NoCostRouting(),
            usage_pct=0.9,
        )
        assert cheap is not None and dear is not None
        assert cheap.score == pytest.approx(dear.score, abs=0.001)
