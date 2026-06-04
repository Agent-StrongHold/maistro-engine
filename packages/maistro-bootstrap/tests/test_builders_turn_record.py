"""TurnRecord and TurnOutcomeSummary tests for builder fitness signals."""

from __future__ import annotations

import pytest

from maistro_bootstrap.builders.turn_record import TurnOutcomeSummary, TurnRecord


def _record(
    *,
    action: str = "read_file",
    status: str = "ok",
    role: str = "architect",
    stage: str = "spec",
    quality_before: dict | None = None,
    quality_after: dict | None = None,
    elapsed: float = 1.0,
    tokens: int = 100,
    retries: int = 0,
) -> TurnRecord:
    return TurnRecord(
        turn_id="turn_0001",
        session_id="test-session",
        role=role,  # type: ignore[arg-type]
        model="test-model",
        stage=stage,
        action_name=action,
        status=status,  # type: ignore[arg-type]
        quality_before=quality_before or {},
        quality_after=quality_after or {},
        elapsed_seconds=elapsed,
        tokens_used=tokens,
        retry_count=retries,
    )


def test_turn_record_succeeded_property() -> None:
    assert _record(status="ok").succeeded is True
    assert _record(status="error").succeeded is False
    assert _record(status="needs_approval").succeeded is False


def test_turn_record_needs_human_property() -> None:
    assert _record(status="needs_approval").needs_human is True
    assert _record(status="ok").needs_human is False


def test_quality_delta_computes_numeric_differences() -> None:
    record = _record(
        quality_before={"coverage_pct": 80.0, "mutation_score_pct": 70.0},
        quality_after={"coverage_pct": 92.0, "mutation_score_pct": 70.0},
    )
    delta = record.quality_delta
    assert delta == {"coverage_pct": 12.0, "mutation_score_pct": 0.0}


def test_quality_delta_empty_when_no_overlap() -> None:
    record = _record(
        quality_before={"coverage_pct": 80.0},
        quality_after={"tests_passed": True},
    )
    assert record.quality_delta == {}


def test_outcome_summary_from_empty_records() -> None:
    summary = TurnOutcomeSummary.from_records("sess-1", [])
    assert summary.total_turns == 0
    assert summary.success_rate == 0.0
    assert summary.session_id == "sess-1"


def test_outcome_summary_aggregates_multiple_records() -> None:
    records = [
        _record(action="read_file", role="architect", stage="spec", status="ok", tokens=50),
        _record(action="propose_patch", role="editor", stage="implement", status="ok", tokens=200),
        _record(action="run_command", role="editor", stage="test", status="error", tokens=100),
        _record(action="read_file", role="architect", stage="spec", status="ok", tokens=75),
    ]
    summary = TurnOutcomeSummary.from_records("sess-1", records)

    assert summary.total_turns == 4
    assert summary.successful_turns == 3
    assert summary.error_turns == 1
    assert summary.approval_turns == 0
    assert summary.total_tokens == 425
    assert summary.action_distribution == {"read_file": 2, "propose_patch": 1, "run_command": 1}
    assert summary.role_distribution == {"architect": 2, "editor": 2}
    assert "spec" in summary.stages_visited
    assert "implement" in summary.stages_visited
    assert "test" in summary.stages_visited


def test_outcome_summary_success_rate() -> None:
    records = [
        _record(status="ok"),
        _record(status="ok"),
        _record(status="error"),
    ]
    summary = TurnOutcomeSummary.from_records("s", records)
    assert summary.success_rate == pytest.approx(2 / 3)


def test_outcome_summary_quality_deltas_accumulate() -> None:
    records = [
        _record(
            quality_before={"coverage_pct": 80.0},
            quality_after={"coverage_pct": 85.0},
        ),
        _record(
            quality_before={"coverage_pct": 85.0},
            quality_after={"coverage_pct": 92.0},
        ),
    ]
    summary = TurnOutcomeSummary.from_records("s", records)
    assert summary.quality_deltas == {"coverage_pct": 12.0}


def test_turn_record_serialization_round_trip() -> None:
    record = _record(
        action="search",
        quality_before={"coverage_pct": 50.0},
        quality_after={"coverage_pct": 55.0},
    )
    data = record.model_dump()
    restored = TurnRecord.model_validate(data)
    assert restored.turn_id == record.turn_id
    assert restored.action_name == "search"
    assert restored.quality_delta == {"coverage_pct": 5.0}


def test_turn_record_default_timestamp_is_utc() -> None:
    record = _record()
    assert record.timestamp.tzinfo is not None


def test_outcome_summary_approval_turns_counted() -> None:
    records = [
        _record(status="needs_approval"),
        _record(status="ok"),
        _record(status="needs_approval"),
    ]
    summary = TurnOutcomeSummary.from_records("s", records)
    assert summary.approval_turns == 2
    assert summary.successful_turns == 1
