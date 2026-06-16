from __future__ import annotations

from pathlib import Path

import pytest

from maistro_rsi.experiment import (
    ExperimentLedger,
    decide_candidate,
    decide_sample_candidate,
    measure_command,
    measure_sample_set,
)


@pytest.mark.asyncio
async def test_measurement_uses_injected_executor() -> None:
    async def executor(command: str, timeout: int) -> tuple[int, str]:
        assert command == "pytest -q"
        assert timeout == 30
        return 0, "passed"

    result = await measure_command(
        executor,
        phase="baseline",
        command="pytest -q",
        timeout_seconds=30,
        scorer=lambda exit_code, output, duration: 1.0 if exit_code == 0 else 0.0,
    )

    assert result.passed is True
    assert result.output == "passed"
    assert result.quality_score == 1.0


def test_candidate_repairing_failure_is_accepted() -> None:
    from maistro_rsi.experiment import CommandMeasurement

    baseline = CommandMeasurement("baseline", "pytest -q", 1, 2.0, "failed", "now")
    candidate = CommandMeasurement("candidate", "pytest -q", 0, 2.1, "passed", "later")

    decision = decide_candidate(baseline, candidate)

    assert decision.accepted is True


def test_candidate_with_changed_benchmark_is_rejected() -> None:
    from maistro_rsi.experiment import CommandMeasurement

    baseline = CommandMeasurement("baseline", "pytest -q", 0, 2.0, "passed", "now")
    candidate = CommandMeasurement("candidate", "pytest -k easy", 0, 0.1, "passed", "later")

    assert decide_candidate(baseline, candidate).accepted is False


def test_candidate_with_better_quality_score_is_accepted() -> None:
    from maistro_rsi.experiment import CommandMeasurement

    baseline = CommandMeasurement("baseline", "pytest -q", 0, 2.0, "25 warnings", "now", -25)
    candidate = CommandMeasurement("candidate", "pytest -q", 0, 2.1, "0 warnings", "later", 0)

    decision = decide_candidate(baseline, candidate)

    assert decision.accepted is True
    assert "quality score" in decision.reason


def test_ledger_is_append_only_jsonl(tmp_path: Path) -> None:
    from maistro_rsi.experiment import CommandMeasurement

    ledger = ExperimentLedger(tmp_path / "ledger.jsonl")
    measurement = CommandMeasurement("baseline", "pytest -q", 0, 2.0, "passed", "now")

    ledger.append_measurement(measurement)
    ledger.append_decision(decide_candidate(measurement, measurement))

    records = ledger.records()
    assert [record["type"] for record in records] == ["measurement", "decision"]
    assert records[1]["baseline_exit_code"] == 0


@pytest.mark.asyncio
async def test_sample_set_candidate_must_improve_same_samples() -> None:
    samples = [{"id": "a", "task": "A"}, {"id": "b", "task": "B"}]

    async def baseline_responder(sample: dict[str, object]) -> str:
        return "partial"

    async def candidate_responder(sample: dict[str, object]) -> str:
        return "complete"

    def scorer(response: str, sample: dict[str, object]) -> float:
        return 1.0 if response == "complete" else 0.5

    baseline = await measure_sample_set(
        phase="baseline",
        benchmark="terminalbench-proxy",
        samples=samples,
        responder=baseline_responder,
        scorer=scorer,
    )
    candidate = await measure_sample_set(
        phase="candidate",
        benchmark="terminalbench-proxy",
        samples=samples,
        responder=candidate_responder,
        scorer=scorer,
    )

    assert decide_sample_candidate(baseline, candidate).accepted is True
