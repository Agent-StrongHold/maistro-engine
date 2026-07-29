from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from .types import EvalResult, PipelineGenome

BenchmarkRunner = Callable[[PipelineGenome, Any], Awaitable[EvalResult]]

BenchmarkFidelity = Literal["proxy", "real"]
"""Per SPEC-202: ``proxy`` is a lite version of the real methodology — small
handcrafted/lite sample sets, but genuine scoring (rule verification,
exact-match, tool-call matching, real execution + assertion/state checks),
never fabricated noise; ``real`` is the official benchmark harness against
the official dataset — not yet implemented for any benchmark.

There is deliberately no ``stub`` tier: a benchmark either evaluates a real
model response against real criteria (``proxy``), or it does not run at all.
Random-noise placeholder scores were removed outright rather than gated,
because a fitness signal that can silently become noise is worse than no
signal — see SPEC-202 and the evolve CLAUDE.md stability statement.
"""


class EvalHarness:
    def __init__(self, benchmark_fidelity: BenchmarkFidelity = "proxy") -> None:
        self._benchmarks: dict[str, BenchmarkRunner] = {}
        self.fidelity: BenchmarkFidelity
        if benchmark_fidelity == "real":
            # No official-harness adapter exists for any benchmark yet
            # (SPEC-202 §3). Fail loudly rather than silently downgrading to
            # proxy and letting a caller believe it got real signal.
            raise ValueError(
                "benchmark_fidelity='real' requested but no real-benchmark "
                "adapters are implemented (SPEC-202). Use 'proxy' (default)."
            )
        if benchmark_fidelity != "proxy":
            # Explicitly reject anything else — including the removed "stub"
            # tier — rather than silently falling through to proxy for an
            # unrecognized value.
            raise ValueError(
                f"unknown benchmark_fidelity {benchmark_fidelity!r}; "
                "valid values are 'proxy' (default) or 'real'. There is no "
                "'stub' tier — see BenchmarkFidelity's docstring."
            )
        self._register_proxy_benchmarks()
        self.fidelity = "proxy"

    def register_benchmark(self, name: str, runner_fn: BenchmarkRunner) -> None:
        self._benchmarks[name] = runner_fn

    def _register_proxy_benchmarks(self) -> None:
        from .benchmarks import PROXY_BENCHMARKS

        for name, runner in PROXY_BENCHMARKS.items():
            self.register_benchmark(name, runner)

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
