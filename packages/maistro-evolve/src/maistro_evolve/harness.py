from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .types import EvalFidelity, EvalResult, PipelineGenome

logger = logging.getLogger("maistro_evolve.harness")

BenchmarkRunner = Callable[[PipelineGenome, Any], Awaitable[EvalResult]]


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
            metadata={"stub": True, "runner": "stub"},
            fidelity=EvalFidelity.STUB,
        )

    return stub


class EvalHarness:
    def __init__(self, benchmark_fidelity: EvalFidelity = EvalFidelity.PROXY) -> None:
        self._benchmarks: dict[str, BenchmarkRunner] = {}
        self._fidelity: dict[str, EvalFidelity] = {}
        if benchmark_fidelity is EvalFidelity.PROXY:
            self._register_proxy_benchmarks()
        elif benchmark_fidelity is EvalFidelity.STUB:
            self._register_default_stubs()
        else:
            raise RuntimeError(
                "No real benchmark harnesses are registered. Real evidence must come from "
                "an explicit, sandboxed benchmark integration."
            )

    def register_benchmark(
        self,
        name: str,
        runner_fn: BenchmarkRunner,
        *,
        fidelity: EvalFidelity = EvalFidelity.PROXY,
    ) -> None:
        self._benchmarks[name] = runner_fn
        self._fidelity[name] = fidelity

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
            self.register_benchmark(name, _make_stub(name), fidelity=EvalFidelity.STUB)

    def _register_proxy_benchmarks(self) -> None:
        try:
            from .benchmarks import PROXY_BENCHMARKS

            for name, runner in PROXY_BENCHMARKS.items():
                self.register_benchmark(name, runner, fidelity=EvalFidelity.PROXY)
        except ImportError as exc:
            # Falling back to random-number stubs SILENTLY would let evolution
            # optimize against pure noise with no signal that it happened. Make
            # it loud — a stub fallback during a real run is a serious problem.
            logger.warning(
                "evolve_harness_stub_fallback: proxy benchmarks failed to import "
                "(%s); fitness scores will be RANDOM stubs, not real evals — "
                "results must not be trusted. Stub results carry metadata.stub=True.",
                exc,
            )
            self._register_default_stubs()

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
                raise ValueError(f"Unknown or unavailable benchmark requested: {name}")
            result = await runner(genome, llm_call)
            result.fidelity = self._fidelity[name]
            result.metadata = {
                **result.metadata,
                "runner": result.fidelity.value,
                "fidelity": result.fidelity.value,
            }
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
