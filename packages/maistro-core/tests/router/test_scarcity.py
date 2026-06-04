"""Tests for scarcity-based effective cost computation.

The router treats cost as a denominator (``quality^x / cost^cw``): a lower
effective cost yields a higher score. Therefore an over-quota provider that
still bills (paygo) must have a *higher* effective cost than any in-budget
free provider, otherwise paid overage would outrank free in-budget quota.
"""

from __future__ import annotations

import math

import pytest

from maistro.router.scarcity import compute_effective_cost
from maistro.types.model import ProviderConfig


def _free_provider() -> ProviderConfig:
    return ProviderConfig(
        billing_cycle="daily",
        free_tokens=1_000_000,
        overage_cost_per_1k_input=0.0,
        overage_cost_per_1k_output=0.0,
    )


def _paygo_provider() -> ProviderConfig:
    return ProviderConfig(
        billing_cycle="daily",
        free_tokens=1_000_000,
        overage_cost_per_1k_input=2.0,
        overage_cost_per_1k_output=6.0,
    )


class TestOverQuotaScale:
    def test_over_quota_paygo_costs_more_than_in_budget_free(self) -> None:
        in_budget_cost = compute_effective_cost(0.99, _free_provider())
        over_quota_cost = compute_effective_cost(1.0, _paygo_provider())
        assert over_quota_cost > in_budget_cost

    def test_over_quota_paygo_above_max_in_budget_ceiling(self) -> None:
        ceiling = 1.0 / math.log(2.0)
        over_quota_cost = compute_effective_cost(1.0, _paygo_provider())
        assert over_quota_cost > ceiling

    def test_over_quota_no_paygo_is_prohibitive(self) -> None:
        no_paygo = ProviderConfig(billing_cycle="daily", free_tokens=1000)
        assert compute_effective_cost(1.0, no_paygo) == 999.0

    def test_higher_overage_rate_costs_more(self) -> None:
        cheap = ProviderConfig(
            billing_cycle="daily",
            free_tokens=1000,
            overage_cost_per_1k_input=1.0,
            overage_cost_per_1k_output=1.0,
        )
        pricey = ProviderConfig(
            billing_cycle="daily",
            free_tokens=1000,
            overage_cost_per_1k_input=10.0,
            overage_cost_per_1k_output=10.0,
        )
        assert compute_effective_cost(1.0, pricey) > compute_effective_cost(1.0, cheap)

    def test_in_budget_free_unchanged_behaviour(self) -> None:
        fresh = compute_effective_cost(0.0, _free_provider())
        assert fresh < 1.0 / math.log(2.0)
        assert fresh > 0.0


class TestScarcityBoundary:
    def test_daily_zero_free_tokens_returns_1(self) -> None:
        provider = ProviderConfig(billing_cycle="daily", free_tokens=0)
        assert compute_effective_cost(0.0, provider) == 1.0

    def test_monthly_billing_divides_by_30(self) -> None:
        daily_p = ProviderConfig(billing_cycle="daily", free_tokens=30_000_000)
        monthly_p = ProviderConfig(billing_cycle="monthly", free_tokens=30_000_000)
        daily_cost = compute_effective_cost(0.0, daily_p)
        monthly_cost = compute_effective_cost(0.0, monthly_p)
        assert monthly_cost > daily_cost

    def test_usage_zero_exact_formula(self) -> None:
        import math

        provider = ProviderConfig(billing_cycle="daily", free_tokens=1_000_000)
        expected = 1.0 / math.log(1_000_000)
        actual = compute_effective_cost(0.0, provider)
        assert actual == pytest.approx(expected, rel=1e-6)

    def test_over_quota_paygo_exact_formula(self) -> None:
        import math

        provider = ProviderConfig(
            billing_cycle="daily",
            free_tokens=1000,
            overage_cost_per_1k_input=2.0,
            overage_cost_per_1k_output=6.0,
        )
        expected = 1.0 / math.log(2.0) + 1.0 + (2.0 + 6.0) / 2.0
        actual = compute_effective_cost(1.0, provider)
        assert actual == pytest.approx(expected, rel=1e-6)

    def test_remaining_floored_at_2(self) -> None:
        provider = ProviderConfig(billing_cycle="daily", free_tokens=3)
        cost = compute_effective_cost(0.5, provider)
        expected = 1.0 / math.log(2.0)
        assert cost == pytest.approx(expected, rel=1e-6)
