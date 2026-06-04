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
