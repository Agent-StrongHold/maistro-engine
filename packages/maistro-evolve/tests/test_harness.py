from __future__ import annotations

from datetime import UTC, datetime

import pytest

from maistro_evolve.harness import EvalHarness
from maistro_evolve.types import DAGTopology, EvalResult, EvalWeights, NodeGenome, PipelineGenome

PROXY_NAMES = [
    "proxy_ifeval",
    "proxy_bfcl",
    "proxy_swebench",
    "proxy_terminalbench",
    "proxy_tau_bench",
    "proxy_gaia",
    "proxy_ragas",
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


def _fake_runner_result(name: str) -> EvalResult:
    return EvalResult(
        benchmark=name,
        score=1.0,
        cost_usd=0.0,
        duration_seconds=0.0,
        samples_evaluated=1,
        metadata={"fidelity": "proxy"},
    )


def test_default_fidelity_is_proxy() -> None:
    """SPEC-202: the default must be honest about what ships today."""
    harness = EvalHarness()
    assert harness.fidelity == "proxy"


def test_proxy_fidelity_registers_proxy_benchmarks() -> None:
    harness = EvalHarness(benchmark_fidelity="proxy")
    from maistro_evolve.benchmarks import PROXY_BENCHMARKS

    assert set(PROXY_BENCHMARKS.keys()) == set(harness._benchmarks.keys())
    assert set(harness._benchmarks.keys()) == set(PROXY_NAMES)
    assert "proxy_osworld" not in harness._benchmarks
    assert harness.fidelity == "proxy"


def test_real_fidelity_raises_no_adapter_exists() -> None:
    """SPEC-202: requesting 'real' with no adapter is a hard error, never a
    silent downgrade to proxy."""
    with pytest.raises(ValueError, match="real"):
        EvalHarness(benchmark_fidelity="real")


def test_no_stub_fidelity_option_exists() -> None:
    """SPEC-202/product decision: there is no random-noise placeholder tier —
    a benchmark evaluates for real or does not run at all."""
    with pytest.raises((ValueError, TypeError)):
        EvalHarness(benchmark_fidelity="stub")  # type: ignore[arg-type]


def test_register_benchmark_registers_custom_runner() -> None:
    harness = EvalHarness()

    async def custom_runner(genome: PipelineGenome, llm_call: object) -> EvalResult:
        return _fake_runner_result("custom")

    harness.register_benchmark("custom", custom_runner)
    assert harness._benchmarks["custom"] is custom_runner


@pytest.mark.asyncio
async def test_evaluate_genome_skips_unregistered_benchmark_name() -> None:
    harness = EvalHarness()
    harness._benchmarks.clear()

    async def fake_ifeval(genome: PipelineGenome, llm_call: object) -> EvalResult:
        return _fake_runner_result("proxy_ifeval")

    harness.register_benchmark("proxy_ifeval", fake_ifeval)
    results = await harness.evaluate_genome(
        _genome(), benchmarks=["proxy_ifeval", "not-registered"]
    )
    assert [r.benchmark for r in results] == ["proxy_ifeval"]


@pytest.mark.asyncio
async def test_evaluate_genome_defaults_to_all_registered_benchmarks() -> None:
    harness = EvalHarness()
    harness._benchmarks.clear()
    for name in ("a", "b", "c"):

        async def fake_runner(
            genome: PipelineGenome, llm_call: object, _name: str = name
        ) -> EvalResult:
            return _fake_runner_result(_name)

        harness.register_benchmark(name, fake_runner)

    results = await harness.evaluate_genome(_genome())
    assert {r.benchmark for r in results} == {"a", "b", "c"}
