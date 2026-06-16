"""Minimal, durable baseline-versus-candidate experiment primitives."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

CommandExecutor = Callable[[str, int], Awaitable[tuple[int, str]]]
OutputScorer = Callable[[int, str, float], float]
SampleResponder = Callable[[dict[str, object]], Awaitable[str]]
SampleScorer = Callable[[str, dict[str, object]], float]


@dataclass(frozen=True)
class CommandMeasurement:
    """One command result captured under a named experiment phase."""

    phase: str
    command: str
    exit_code: int
    duration_seconds: float
    output: str
    measured_at: str
    quality_score: float | None = None

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class ExperimentDecision:
    """Naive retain-or-reject decision for one candidate."""

    accepted: bool
    reason: str
    baseline: CommandMeasurement
    candidate: CommandMeasurement


@dataclass(frozen=True)
class SampleSetMeasurement:
    """Per-sample evidence for one candidate evaluated on a fixed sample set."""

    phase: str
    benchmark: str
    sample_ids: tuple[str, ...]
    responses: dict[str, str]
    scores: dict[str, float]
    mean_score: float
    measured_at: str


@dataclass(frozen=True)
class SampleSetDecision:
    """Retain-or-reject decision for a candidate on an unchanged sample set."""

    accepted: bool
    reason: str
    baseline: SampleSetMeasurement
    candidate: SampleSetMeasurement


async def measure_command(
    executor: CommandExecutor,
    *,
    phase: str,
    command: str,
    timeout_seconds: int = 900,
    output_limit: int = 64 * 1024,
    scorer: OutputScorer | None = None,
) -> CommandMeasurement:
    """Run one fixed command through an injected executor and capture evidence."""
    started = time.monotonic()
    exit_code, output = await executor(command, timeout_seconds)
    duration = time.monotonic() - started
    return CommandMeasurement(
        phase=phase,
        command=command,
        exit_code=exit_code,
        duration_seconds=round(duration, 6),
        output=output[-output_limit:],
        measured_at=datetime.now(UTC).isoformat(),
        quality_score=scorer(exit_code, output, duration) if scorer else None,
    )


def decide_candidate(
    baseline: CommandMeasurement,
    candidate: CommandMeasurement,
    *,
    minimum_speedup: float = 0.05,
) -> ExperimentDecision:
    """Accept an objectively better result; reject ambiguous or broken candidates."""
    if baseline.command != candidate.command:
        return ExperimentDecision(False, "benchmark command changed", baseline, candidate)
    if candidate.passed and not baseline.passed:
        return ExperimentDecision(
            True, "candidate repaired a failing baseline", baseline, candidate
        )
    if baseline.passed and not candidate.passed:
        return ExperimentDecision(
            False, "candidate regressed a passing baseline", baseline, candidate
        )
    if not baseline.passed and not candidate.passed:
        return ExperimentDecision(False, "both baseline and candidate failed", baseline, candidate)
    if baseline.quality_score is not None and candidate.quality_score is not None:
        if candidate.quality_score > baseline.quality_score:
            return ExperimentDecision(
                True, "candidate improved the configured quality score", baseline, candidate
            )
        if candidate.quality_score < baseline.quality_score:
            return ExperimentDecision(
                False, "candidate regressed the configured quality score", baseline, candidate
            )
    threshold = baseline.duration_seconds * (1.0 - minimum_speedup)
    if candidate.duration_seconds < threshold:
        return ExperimentDecision(True, "candidate met the minimum speedup", baseline, candidate)
    return ExperimentDecision(
        False, "candidate did not demonstrate a material improvement", baseline, candidate
    )


async def measure_sample_set(
    *,
    phase: str,
    benchmark: str,
    samples: Sequence[dict[str, object]],
    responder: SampleResponder,
    scorer: SampleScorer,
) -> SampleSetMeasurement:
    """Evaluate one responder on a fixed sample sequence and preserve per-sample evidence."""
    responses: dict[str, str] = {}
    scores: dict[str, float] = {}
    for sample in samples:
        sample_id = str(sample["id"])
        response = await responder(sample)
        responses[sample_id] = response
        scores[sample_id] = scorer(response, sample)
    return SampleSetMeasurement(
        phase=phase,
        benchmark=benchmark,
        sample_ids=tuple(scores),
        responses=responses,
        scores=scores,
        mean_score=sum(scores.values()) / max(len(scores), 1),
        measured_at=datetime.now(UTC).isoformat(),
    )


def decide_sample_candidate(
    baseline: SampleSetMeasurement,
    candidate: SampleSetMeasurement,
    *,
    minimum_delta: float = 0.01,
) -> SampleSetDecision:
    """Accept only a measurable improvement on the exact same sample IDs."""
    if baseline.benchmark != candidate.benchmark or baseline.sample_ids != candidate.sample_ids:
        return SampleSetDecision(False, "benchmark or sample set changed", baseline, candidate)
    if candidate.mean_score >= baseline.mean_score + minimum_delta:
        return SampleSetDecision(True, "candidate improved mean sample score", baseline, candidate)
    return SampleSetDecision(
        False, "candidate did not improve mean sample score", baseline, candidate
    )


class ExperimentLedger:
    """Append-only JSONL evidence suitable for pause/resume and later inspection."""

    def __init__(self, path: Path) -> None:
        self._path = path.resolve()

    @property
    def path(self) -> Path:
        return self._path

    def append_measurement(self, measurement: CommandMeasurement) -> None:
        self._append({"type": "measurement", **asdict(measurement)})

    def append_decision(self, decision: ExperimentDecision) -> None:
        self._append(
            {
                "type": "decision",
                "accepted": decision.accepted,
                "reason": decision.reason,
                "baseline_phase": decision.baseline.phase,
                "candidate_phase": decision.candidate.phase,
                "baseline_exit_code": decision.baseline.exit_code,
                "candidate_exit_code": decision.candidate.exit_code,
                "baseline_quality_score": decision.baseline.quality_score,
                "candidate_quality_score": decision.candidate.quality_score,
                "baseline_duration_seconds": decision.baseline.duration_seconds,
                "candidate_duration_seconds": decision.candidate.duration_seconds,
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        )

    def append_sample_measurement(self, measurement: SampleSetMeasurement) -> None:
        self._append({"type": "sample_measurement", **asdict(measurement)})

    def append_sample_decision(self, decision: SampleSetDecision) -> None:
        self._append(
            {
                "type": "sample_decision",
                "accepted": decision.accepted,
                "reason": decision.reason,
                "benchmark": decision.baseline.benchmark,
                "sample_ids": decision.baseline.sample_ids,
                "baseline_mean_score": decision.baseline.mean_score,
                "candidate_mean_score": decision.candidate.mean_score,
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        )

    def records(self) -> list[dict[str, object]]:
        if not self._path.is_file():
            return []
        return [
            json.loads(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _append(self, record: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
