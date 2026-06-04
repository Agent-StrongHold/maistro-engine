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


def test_dagflow_snapshot_keys_and_initial_column_counts() -> None:
    flow = DagFlow()

    snap = flow.snapshot()

    assert isinstance(snap, dict)
    assert set(snap.keys()) == {"columns", "quality", "complete"}
    # All 5 stages start in todo
    assert snap["columns"] == {"todo": 5, "wip": 0, "done": 0}
    assert snap["quality"] is None
    assert snap["complete"] is False


def test_dagflow_snapshot_reflects_in_progress_stage() -> None:
    flow = DagFlow()

    flow.start("spec")
    snap = flow.snapshot()

    assert snap["columns"] == {"todo": 4, "wip": 1, "done": 0}
    assert snap["complete"] is False


def test_dagflow_snapshot_quality_after_record() -> None:
    flow = DagFlow()
    for stage in ["spec", "plan", "implement", "test", "audit"]:
        flow.start(stage)
        flow.finish(stage, summary=f"{stage} done")

    flow.record_quality(_passing_quality())
    snap = flow.snapshot()

    assert snap["quality"] is not None
    assert snap["quality"]["passed"] is True
    assert snap["quality"]["failures"] == []
    assert snap["quality"]["coverage_pct"] == 93.0
    assert snap["quality"]["mutation_score_pct"] == 100.0
    assert snap["columns"] == {"todo": 0, "wip": 0, "done": 5}
    assert snap["complete"] is True


def test_dagflow_is_not_complete_before_quality_recorded() -> None:
    flow = DagFlow()
    for stage in ["spec", "plan", "implement", "test", "audit"]:
        flow.start(stage)
        flow.finish(stage, summary=f"{stage} done")

    # All stages done but quality not yet recorded
    assert flow.is_complete is False
    assert flow.snapshot()["complete"] is False


def test_dagflow_is_not_complete_with_failing_quality() -> None:
    flow = DagFlow()
    for stage in ["spec", "plan", "implement", "test", "audit"]:
        flow.start(stage)
        flow.finish(stage, summary=f"{stage} done")

    flow.record_quality(
        QualityGateReport(
            tests_passed=False,
            coverage_pct=0.0,
            mutation_score_pct=0.0,
            complexity_grade="C",
            dry_ok=False,
            code_smells_ok=False,
            bandit_ok=False,
            ruff_ok=False,
            mypy_ok=False,
        )
    )

    assert flow.is_complete is False
    snap = flow.snapshot()
    assert snap["complete"] is False
    assert snap["quality"]["passed"] is False
    assert len(snap["quality"]["failures"]) == 9
