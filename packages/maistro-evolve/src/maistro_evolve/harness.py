from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from .types import EvalResult, PipelineGenome

logger = logging.getLogger("maistro_evolve.harness")

BenchmarkRunner = Callable[[PipelineGenome, Any], Awaitable[EvalResult]]

BenchmarkFidelity = Literal["stub", "proxy", "real"]
"""Per SPEC-202: ``stub`` is random noise (no evaluation occurred); ``proxy``
is heuristic/keyword scoring against handcrafted samples (development-only,
never trust for promotion); ``real`` is the official benchmark harness
against the official dataset — not yet implemented for any benchmark."""


def _make_stub(benchmark_name: str) -> BenchmarkRunner:
    async def stub(genome: PipelineGenome, llm_call: Any) -> EvalResult:
        start = time.monotonic()
        await asyncio.sleep(random.uniform(0.01, 0.05))
        node_factor = len(genome.topology.nodes) * 0.05
        base = random.uniform(0.2, 0.8) + node_factor
        score = max(0.0, min(1.0, base))
        elapsed = time.monotonic() - start
        return EvalResult(
            benchmark=benchmark_name,
            score=round(score, 4),
            cost_usd=round(random.uniform(0.001, 0.05), 4),
            duration_seconds=round(elapsed, 3),
            samples_evaluated=random.randint(50, 500),
            metadata={"stub": True, "fidelity": "stub"},
        )

    return stub


class EvalHarness:
    def __init__(self, benchmark_fidelity: BenchmarkFidelity = "proxy") -> None:
        self._benchmarks: dict[str, BenchmarkRunner] = {}
        self.fidelity: BenchmarkFidelity
        if benchmark_fidelity == "real":
            # No official-harness adapter exists for any benchmark yet
            # (SPEC-202 §3). Fail loudly rather than silently downgrading to
            # proxy/stub and letting a caller believe it got real signal.
            raise ValueError(
                "benchmark_fidelity='real' requested but no real-benchmark "
                "adapters are implemented (SPEC-202). Use 'proxy' (default) "
                "or 'stub'."
            )
        elif benchmark_fidelity == "stub":
            self._register_default_stubs()
            self.fidelity = "stub"
        else:
            self._register_proxy_benchmarks()

    def register_benchmark(self, name: str, runner_fn: BenchmarkRunner) -> None:
        self._benchmarks[name] = runner_fn

    def _register_default_stubs(self) -> None:
        for name in [
            "ifeval",
            "bfcl",
            "swebench",
            "terminalbench",
            "tau_bench",
            "gaia",
            "ragas",
            "osworld",
        ]:
            self.register_benchmark(name, _make_stub(name))

    def _register_proxy_benchmarks(self) -> None:
        try:
            from .benchmarks import PROXY_BENCHMARKS

            for name, runner in PROXY_BENCHMARKS.items():
                self.register_benchmark(name, runner)
            self.fidelity = "proxy"
        except ImportError as exc:
            # Falling back to random-number stubs SILENTLY would let evolution
            # optimize against pure noise with no signal that it happened. Make
            # it loud — a stub fallback during a proxy run is a serious problem.
            logger.warning(
                "evolve_harness_stub_fallback: proxy benchmarks failed to import "
                "(%s); fitness scores will be RANDOM stubs, not even proxy evals — "
                "results must not be trusted. Stub results carry metadata.stub=True.",
                exc,
            )
            self._register_default_stubs()
            self.fidelity = "stub"

    async def evaluate_genome(
        self,
        genome: PipelineGenome,
        benchmarks: list[str] | None = None,
        llm_call: Any = None,
    ) -> list[EvalResult]:
        bench_list = benchmarks or list(self._benchmarks.keys())
        results: list[EvalResult] = []
        for name in bench_list:
            runner = self._benchmarks.get(name)
            if runner is None:
                continue
            result = await runner(genome, llm_call)
            results.append(result)
        return results


run_ifeval_stub = _make_stub("ifeval")
run_bfcl_stub = _make_stub("bfcl")
run_swebench_stub = _make_stub("swebench")
run_terminalbench_stub = _make_stub("terminalbench")
run_tau_bench_stub = _make_stub("tau_bench")
run_gaia_stub = _make_stub("gaia")
run_ragas_stub = _make_stub("ragas")
run_osworld_stub = _make_stub("osworld")
