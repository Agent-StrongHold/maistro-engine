"""ImprovementKind taxonomy: budget tier, preference order, lenient parsing."""

from __future__ import annotations

from maistro_evolve.improvement import BudgetTier, ImprovementKind


def test_only_feature_unlocks_the_big_budget() -> None:
    assert ImprovementKind.FEATURE.budget is BudgetTier.UNLOCKED
    for kind in ImprovementKind:
        if kind is not ImprovementKind.FEATURE:
            assert kind.budget is BudgetTier.BOUNDED


def test_priority_is_correctness_then_growth_then_doc_last() -> None:
    order = sorted(ImprovementKind, key=lambda k: k.priority)
    assert order[0] is ImprovementKind.BUG_FIX
    assert order[-1] is ImprovementKind.DOC
    # bug-fix > new test > assertion > feature > edge (the settled ordering).
    assert (
        ImprovementKind.BUG_FIX.priority
        < ImprovementKind.NEW_TEST.priority
        < ImprovementKind.ASSERTION.priority
        < ImprovementKind.FEATURE.priority
        < ImprovementKind.EDGE_CASE.priority
    )


def test_from_str_is_lenient_and_falls_back_to_doc() -> None:
    assert ImprovementKind.from_str("FEATURE") is ImprovementKind.FEATURE
    assert ImprovementKind.from_str("  bug_fix ") is ImprovementKind.BUG_FIX
    assert ImprovementKind.from_str("nonsense") is ImprovementKind.DOC
    assert ImprovementKind.from_str("") is ImprovementKind.DOC


def test_primary_signals_cover_every_kind() -> None:
    for kind in ImprovementKind:
        assert kind.primary_signals  # non-empty tuple for each
