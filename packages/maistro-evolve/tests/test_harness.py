from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from maistro_evolve.harness import EvalHarness
from maistro_evolve.types import DAGTopology, EvalResult, EvalWeights, NodeGenome, PipelineGenome

STUB_NAMES = [
    "ifeval",
    "bfcl",
    "swebench",
    "terminalbench",
    "tau_bench",
    "gaia",
    "ragas",
    "osworld",
]


def _genome() -> PipelineGenome:
    return PipelineGenome(
        id="g1",
        name="g1",
        topology=DAGTopology(
            nodes=[
                NodeGenome(
                    id="q1",
                    role="queen",
                    strategy="react",
                    model="gpt-4",
                    temperature=0.3,
                    max_tokens=4096,
                    system_prompt="test",
                    max_tool_rounds=5,
                )
            ],
            edges=[],
            entry_node="q1",
            max_cycles=3,
            beam_width=1,
            use_scout=False,
        ),
        eval_weights=EvalWeights(),
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )


def test_use_real_benchmarks_false_registers_all_default_stubs() -> None:
    harness = EvalHarness(use_real_benchmarks=False)
    assert set(harness._benchmarks.keys()) == set(STUB_NAMES)


def test_use_real_benchmarks_true_registers_real_benchmarks_when_import_succeeds() -> None:
    harness = EvalHarness(use_real_benchmarks=True)
    from maistro_evolve.benchmarks import REAL_BENCHMARKS

    assert set(REAL_BENCHMARKS.keys()) <= set(harness._benchmarks.keys())


def test_register_real_benchmarks_falls_back_to_stubs_on_import_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import maistro_evolve.benchmarks as benchmarks_module

    monkeypatch.delattr(benchmarks_module, "REAL_BENCHMARKS", raising=True)

    with caplog.at_level(logging.WARNING, logger="maistro_evolve.harness"):
        harness = EvalHarness(use_real_benchmarks=True)

    assert set(harness._benchmarks.keys()) == set(STUB_NAMES)
    assert any("evolve_harness_stub_fallback" in record.message for record in caplog.records)


def test_register_benchmark_registers_custom_runner() -> None:
    harness = EvalHarness(use_real_benchmarks=False)

    async def custom_runner(genome: PipelineGenome, llm_call: object) -> EvalResult:
        return EvalResult(
            benchmark="custom",
            score=1.0,
            cost_usd=0.0,
            duration_seconds=0.0,
            samples_evaluated=1,
            metadata={},
        )

    harness.register_benchmark("custom", custom_runner)
    assert harness._benchmarks["custom"] is custom_runner


@pytest.mark.asyncio
async def test_evaluate_genome_skips_unregistered_benchmark_name() -> None:
    harness = EvalHarness(use_real_benchmarks=False)
    results = await harness.evaluate_genome(_genome(), benchmarks=["ifeval", "not-registered"])
    assert [r.benchmark for r in results] == ["ifeval"]


@pytest.mark.asyncio
async def test_evaluate_genome_defaults_to_all_registered_benchmarks() -> None:
    harness = EvalHarness(use_real_benchmarks=False)
    results = await harness.evaluate_genome(_genome())
    assert {r.benchmark for r in results} == set(STUB_NAMES)
