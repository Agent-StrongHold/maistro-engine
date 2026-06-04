"""Quality gates for autonomous builder completion."""

from __future__ import annotations

from dataclasses import dataclass

_COMPLEXITY_RANKS: dict[str, int] = {
    "A": 5,
    "A-": 4,
    "B+": 3,
    "B": 2,
    "B-": 1,
    "C": 0,
    "D": -1,
    "F": -2,
}


@dataclass(frozen=True)
class QualityGateReport:
    """Evidence summary for the requested autonomous completion bar."""

    tests_passed: bool
    coverage_pct: float
    mutation_score_pct: float
    complexity_grade: str
    dry_ok: bool
    code_smells_ok: bool
    bandit_ok: bool
    ruff_ok: bool
    mypy_ok: bool

    @property
    def passed(self) -> bool:
        return not self.failures()

    def failures(self) -> list[str]:
        checks = (
            (self.tests_passed, "tests pass"),
            (self.coverage_pct >= 90.0, "coverage >= 90%"),
            (self.mutation_score_pct >= 90.0, "mutation score >= 90%"),
            (
                _complexity_rank(self.complexity_grade) >= _complexity_rank("B+"),
                "complexity grade >= B+",
            ),
            (self.dry_ok, "DRY"),
            (self.code_smells_ok, "no code smells"),
            (self.bandit_ok, "bandit"),
            (self.ruff_ok, "ruff"),
            (self.mypy_ok, "mypy"),
        )
        return [message for passed, message in checks if not passed]


def _complexity_rank(grade: str) -> int:
    return _COMPLEXITY_RANKS.get(grade.upper(), -999)
