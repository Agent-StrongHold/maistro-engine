"""Improvement taxonomy — the kinds of change the RSI scout can propose, and
what each kind means for *budget* and *scoring* (ADR-070126-6386 v2).

The scout tags every shortlist item with an ``ImprovementKind``. That one flag
is the routing key for everything downstream:

- **Budget** — how much compute a competitor may spend on it. Correctness and
  verification work is a bounded, single-file (+ its test) change; a ``FEATURE``
  ("v2.0") is ambitious multi-file work that unlocks a large token/turn budget.
- **Scoring** — which fitness signals decide promotion. Correctness is cheap to
  score objectively (tests pass, coverage rises, red→green); a feature is not, so
  it is judged by the LLM impact judge plus a capability/benchmark delta when one
  exists (see ``candidate_fitness``/``scorecard``).

The point of the loop is recursive self-improvement — real growth up to a module
"v2.0" — not docstring churn, so ``DOC`` is a last-resort fallback only.
"""

from __future__ import annotations

from enum import StrEnum


class BudgetTier(StrEnum):
    """How much a single competitor may spend on one item."""

    BOUNDED = "bounded"  # one focused change to the target file (+ its test)
    UNLOCKED = "unlocked"  # ambitious: multi-file, many turns, high token budget


class ImprovementKind(StrEnum):
    """The kind of improvement a scout item proposes.

    Ordered by the scout's default *preference* when several are available on a
    module (see :pyattr:`priority`): correctness and verification before growth,
    with ``DOC`` only when nothing better is warranted.
    """

    BUG_FIX = "bug_fix"  # code violates its contract — turn red→green
    NEW_TEST = "new_test"  # evidence-based test for untested behavior
    ASSERTION = "assertion"  # strengthen a test that asserts too little
    FEATURE = "feature"  # a genuinely better capability/API/design (v2.0)
    EDGE_CASE = "edge_case"  # a boundary/error path with no test
    REFACTOR = "refactor"  # behavior-preserving clarity/DRY/complexity win
    PERF = "perf"  # a measurable performance optimization
    DOC = "doc"  # docstring/type — fallback only, never the goal

    @property
    def budget(self) -> BudgetTier:
        """FEATURE work is the only tier that unlocks the large, multi-file budget."""
        return BudgetTier.UNLOCKED if self is ImprovementKind.FEATURE else BudgetTier.BOUNDED

    @property
    def priority(self) -> int:
        """Scout preference rank (lower wins) when several kinds are available."""
        return _PRIORITY[self]

    @property
    def primary_signals(self) -> tuple[str, ...]:
        """The fitness signals that chiefly reward this kind (for docs/routing).

        Names match the ``SignalScore``/gate names produced by ``candidate_fitness``.
        A kind is not *limited* to these — every candidate is scored by the whole
        Scorecard — but these are the ones its acceptance hinges on.
        """
        return _PRIMARY_SIGNALS[self]

    @classmethod
    def from_str(cls, value: str) -> ImprovementKind:
        """Parse a scout-emitted kind leniently; unknown/blank → ``DOC`` (safe fallback)."""
        try:
            return cls(value.strip().lower())
        except (ValueError, AttributeError):
            return cls.DOC


# Preference order: correctness (bug→test→assertion) → growth (feature) → edge →
# refactor → perf → doc-fallback. Tunable; the scout may still rank by impact.
_PRIORITY: dict[ImprovementKind, int] = {
    ImprovementKind.BUG_FIX: 0,
    ImprovementKind.NEW_TEST: 1,
    ImprovementKind.ASSERTION: 2,
    ImprovementKind.FEATURE: 3,
    ImprovementKind.EDGE_CASE: 4,
    ImprovementKind.REFACTOR: 5,
    ImprovementKind.PERF: 6,
    ImprovementKind.DOC: 7,
}

_PRIMARY_SIGNALS: dict[ImprovementKind, tuple[str, ...]] = {
    ImprovementKind.BUG_FIX: ("red_green",),
    ImprovementKind.NEW_TEST: ("new_test", "coverage"),
    ImprovementKind.ASSERTION: ("assertion_strength",),
    ImprovementKind.FEATURE: ("feature_judge", "capability"),
    ImprovementKind.EDGE_CASE: ("new_test", "coverage"),
    ImprovementKind.REFACTOR: ("code_quality",),
    ImprovementKind.PERF: ("perf", "capability"),
    ImprovementKind.DOC: ("code_quality",),
}
