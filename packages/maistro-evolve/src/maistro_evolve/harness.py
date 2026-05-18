from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Callable, Awaitable

from .types import EvalResult, PipelineGenome

BenchmarkRunner = Callable[[PipelineGenome, Any], Awaitable[EvalResult]]


class EvalHarness:
    def __init__(self) -> None:
        self._benchmarks: dict[str, BenchmarkRunner] = {}
        self._register_default_stubs()

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
            metadata={"stub": True},
        )

    return stub


run_ifeval_stub = _make_stub("ifeval")
run_bfcl_stub = _make_stub("bfcl")
run_swebench_stub = _make_stub("swebench")
run_terminalbench_stub = _make_stub("terminalbench")
run_tau_bench_stub = _make_stub("tau_bench")
run_gaia_stub = _make_stub("gaia")
run_ragas_stub = _make_stub("ragas")
run_osworld_stub = _make_stub("osworld")
