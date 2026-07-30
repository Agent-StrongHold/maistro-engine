from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from maistro_evolve.harness import EvalHarness
from maistro_evolve.types import DAGTopology, EvalResult, EvalWeights, NodeGenome, PipelineGenome

PROXY_NAMES = [
    "ifeval",
    "bfcl",
    "swebench",
    "terminalbench",
    "tau_bench",
    "gaia",
    "ragas",
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
    assert "osworld" not in harness._benchmarks
    assert harness.fidelity == "proxy"


def test_real_fidelity_registers_only_available_real_adapters() -> None:
    """A real harness must not backfill missing adapters from the proxy registry.

    Mixing tiers behind one `fidelity` label is the dishonesty SPEC-202's
    two-tier model exists to prevent: a caller that reads
    `harness.fidelity == "real"` off a harness whose swebench score came from 8
    handcrafted samples has been misled by the object it asked.

    Availability-agnostic on purpose: which real adapters can run depends on
    the environment (the ifeval extra may not be installed here), so this
    asserts the invariants — registered == available, available ⊆ real
    registry, and everything real-but-unregistered carries a reason.
    """
    from maistro_evolve.benchmarks import (
        PROXY_BENCHMARKS,
        REAL_BENCHMARKS,
        available_real_benchmarks,
    )

    harness = EvalHarness(benchmark_fidelity="real")
    available, unavailable = available_real_benchmarks()
    assert harness.fidelity == "real"
    assert set(harness._benchmarks) == set(available)
    assert set(available) | set(unavailable) == set(REAL_BENCHMARKS)
    assert all(reason for reason in harness.unavailable_real.values())
    # BFCL's vendored checker is stdlib-only, so it is available on any
    # correct checkout — a real harness is never empty.
    assert "bfcl" in harness._benchmarks
    # Strictly fewer benchmarks than proxy — the point, not an oversight.
    assert set(harness._benchmarks) < set(PROXY_BENCHMARKS)


def test_unavailable_real_adapter_is_skipped_by_default_but_explicit_ask_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The optional-includes contract, both halves.

    Real benchmarks the environment can't run are skipped when the caller
    doesn't name benchmarks (a bare install still evaluates on what it has),
    but an explicit request for one raises with the install hint — and never
    quietly swaps in the proxy namesake.
    """
    import maistro_evolve.benchmarks as bench_pkg

    async def stub_bfcl(genome: PipelineGenome, llm_call: object) -> EvalResult:
        return _fake_runner_result("bfcl")

    monkeypatch.setattr(
        bench_pkg,
        "available_real_benchmarks",
        lambda: ({"bfcl": stub_bfcl}, {"ifeval": "install 'maistro-evolve[ifeval]'"}),
    )
    harness = EvalHarness(benchmark_fidelity="real")
    assert set(harness._benchmarks) == {"bfcl"}
    assert harness.unavailable_real == {"ifeval": "install 'maistro-evolve[ifeval]'"}

    # Unnamed: only the available adapter runs; the unavailable one is skipped.
    results = asyncio.run(harness.evaluate_genome(_genome(), None, None))
    assert [r.benchmark for r in results] == ["bfcl"]

    # Named: explicit ask, explicit answer.
    with pytest.raises(ValueError, match="exists but is unavailable"):
        asyncio.run(harness.evaluate_genome(_genome(), ["ifeval"], None))


def test_no_available_real_adapter_at_all_raises_at_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import maistro_evolve.benchmarks as bench_pkg

    monkeypatch.setattr(
        bench_pkg,
        "available_real_benchmarks",
        lambda: ({}, {"ifeval": "no extra", "bfcl": "no corpus"}),
    )
    with pytest.raises(ValueError, match="no real-benchmark adapter can run"):
        EvalHarness(benchmark_fidelity="real")


def test_proxy_harness_reports_no_unavailable_real() -> None:
    assert EvalHarness().unavailable_real == {}


def test_real_fidelity_refuses_a_benchmark_with_no_real_adapter() -> None:
    """Skipping silently would make a short result list look like a clean run.

    At proxy tier an unknown name is harmlessly skipped. At real tier the likely
    cause is "no real adapter exists for this yet", and swallowing that lets
    compute_fitness score a genome on fewer benchmarks than the caller asked for
    without anyone noticing.
    """
    harness = EvalHarness(benchmark_fidelity="real")

    async def llm_call(messages: object, **kwargs: object) -> str:
        return "x"

    with pytest.raises(ValueError, match="no real-fidelity adapter for benchmark 'swebench'"):
        asyncio.run(harness.evaluate_genome(_genome(), ["swebench"], llm_call))


def test_proxy_fidelity_still_skips_unknown_benchmarks() -> None:
    """The stricter real-tier behaviour above must not leak into proxy."""
    harness = EvalHarness()
    results = asyncio.run(harness.evaluate_genome(_genome(), ["not_a_benchmark"], None))
    assert results == []


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
        return _fake_runner_result("ifeval")

    harness.register_benchmark("ifeval", fake_ifeval)
    results = await harness.evaluate_genome(_genome(), benchmarks=["ifeval", "not-registered"])
    assert [r.benchmark for r in results] == ["ifeval"]


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
