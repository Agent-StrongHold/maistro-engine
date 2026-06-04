"""Quality gate substrate for autonomous builder completion."""

from __future__ import annotations

from maistro_bootstrap.builders.quality import QualityGateReport


def test_quality_gate_requires_coverage_at_least_90_percent() -> None:
    report = QualityGateReport(
        tests_passed=True,
        coverage_pct=89.9,
        mutation_score_pct=100.0,
        complexity_grade="B+",
        dry_ok=True,
        code_smells_ok=True,
        bandit_ok=True,
        ruff_ok=True,
        mypy_ok=True,
    )

    assert report.passed is False
    assert "coverage >= 90%" in report.failures()


def test_quality_gate_requires_mutation_evidence() -> None:
    report = QualityGateReport(
        tests_passed=True,
        coverage_pct=95.0,
        mutation_score_pct=89.9,
        complexity_grade="B+",
        dry_ok=True,
        code_smells_ok=True,
        bandit_ok=True,
        ruff_ok=True,
        mypy_ok=True,
    )

    assert report.passed is False
    assert "mutation score >= 90%" in report.failures()


def test_quality_gate_requires_complexity_b_plus_or_better() -> None:
    report = QualityGateReport(
        tests_passed=True,
        coverage_pct=95.0,
        mutation_score_pct=90.0,
        complexity_grade="B",
        dry_ok=True,
        code_smells_ok=True,
        bandit_ok=True,
        ruff_ok=True,
        mypy_ok=True,
    )

    assert report.passed is False
    assert "complexity grade >= B+" in report.failures()


def test_quality_gate_passes_only_when_all_required_checks_pass() -> None:
    report = QualityGateReport(
        tests_passed=True,
        coverage_pct=91.0,
        mutation_score_pct=90.0,
        complexity_grade="B+",
        dry_ok=True,
        code_smells_ok=True,
        bandit_ok=True,
        ruff_ok=True,
        mypy_ok=True,
    )

    assert report.passed is True
    assert report.failures() == []


def test_quality_gate_accepts_a_minus_and_rejects_unknown_complexity_grade() -> None:
    accepted = QualityGateReport(
        tests_passed=True,
        coverage_pct=90.0,
        mutation_score_pct=90.0,
        complexity_grade="a-",
        dry_ok=True,
        code_smells_ok=True,
        bandit_ok=True,
        ruff_ok=True,
        mypy_ok=True,
    )
    rejected = QualityGateReport(
        tests_passed=True,
        coverage_pct=90.0,
        mutation_score_pct=90.0,
        complexity_grade="unknown",
        dry_ok=True,
        code_smells_ok=True,
        bandit_ok=True,
        ruff_ok=True,
        mypy_ok=True,
    )

    assert accepted.failures() == []
    assert rejected.failures() == ["complexity grade >= B+"]


# ---------------------------------------------------------------------------
# Coverage boundary
# ---------------------------------------------------------------------------


def _passing_report(**overrides):  # type: ignore[no-untyped-def]
    """Return a fully-passing QualityGateReport with any field overridden."""
    from maistro_bootstrap.builders.quality import QualityGateReport

    defaults = {
        "tests_passed": True,
        "coverage_pct": 90.0,
        "mutation_score_pct": 90.0,
        "complexity_grade": "B+",
        "dry_ok": True,
        "code_smells_ok": True,
        "bandit_ok": True,
        "ruff_ok": True,
        "mypy_ok": True,
    }
    defaults.update(overrides)
    return QualityGateReport(**defaults)


def test_coverage_exactly_90_passes() -> None:
    report = _passing_report(coverage_pct=90.0)

    assert report.passed is True
    assert "coverage >= 90%" not in report.failures()


def test_coverage_89_9_fails() -> None:
    report = _passing_report(coverage_pct=89.9)

    assert report.passed is False
    assert "coverage >= 90%" in report.failures()


# ---------------------------------------------------------------------------
# Mutation score boundary
# ---------------------------------------------------------------------------


def test_mutation_score_exactly_90_passes() -> None:
    report = _passing_report(mutation_score_pct=90.0)

    assert report.passed is True
    assert "mutation score >= 90%" not in report.failures()


def test_mutation_score_89_9_fails() -> None:
    report = _passing_report(mutation_score_pct=89.9)

    assert report.passed is False
    assert "mutation score >= 90%" in report.failures()


def test_mutation_score_80_fails() -> None:
    # 80.0 is well below the 90% gate — must not slip through.
    report = _passing_report(mutation_score_pct=80.0)

    assert report.passed is False
    assert "mutation score >= 90%" in report.failures()


def test_mutation_score_79_9_fails() -> None:
    report = _passing_report(mutation_score_pct=79.9)

    assert report.passed is False
    assert "mutation score >= 90%" in report.failures()


# ---------------------------------------------------------------------------
# Unknown complexity grade
# ---------------------------------------------------------------------------


def test_unknown_complexity_grade_fails_gate() -> None:
    # _complexity_rank returns -999 for unknown grades, which is below B+ rank.
    report = _passing_report(complexity_grade="UNKNOWN")

    assert report.passed is False
    assert "complexity grade >= B+" in report.failures()


def test_complexity_rank_returns_sentinel_for_unknown_grade() -> None:
    from maistro_bootstrap.builders.quality import _complexity_rank

    assert _complexity_rank("UNKNOWN") == -999
    assert _complexity_rank("Z") == -999
    assert _complexity_rank("") == -999
