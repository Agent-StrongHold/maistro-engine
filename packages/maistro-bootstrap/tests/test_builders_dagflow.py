"""DAG flow progress substrate for builder session monitoring."""

from __future__ import annotations

from maistro_bootstrap.builders.dagflow import DagFlow
from maistro_bootstrap.builders.quality import QualityGateReport


def _passing_quality() -> QualityGateReport:
    return QualityGateReport(
        tests_passed=True,
        coverage_pct=93.0,
        mutation_score_pct=100.0,
        complexity_grade="B+",
        dry_ok=True,
        code_smells_ok=True,
        bandit_ok=True,
        ruff_ok=True,
        mypy_ok=True,
    )


def test_dagflow_advances_cards_from_todo_to_done() -> None:
    flow = DagFlow()

    flow.start("spec")
    flow.finish("spec", summary="Spec accepted")

    columns = flow.board.columns()
    assert columns["todo"][0].question == "Plan"
    assert columns["done"][0].question == "Spec"


def test_dagflow_completes_only_with_passing_quality_report() -> None:
    flow = DagFlow()
    for stage in ["spec", "plan", "implement", "test", "audit"]:
        flow.start(stage)
        flow.finish(stage, summary=f"{stage} complete")

    flow.record_quality(_passing_quality())

    assert flow.is_complete is True
    assert flow.snapshot()["quality"]["passed"] is True
