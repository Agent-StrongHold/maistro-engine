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
the official dataset.

``real`` is implemented for **ifeval only** (``benchmarks/ifeval_real.py``:
the official 541-prompt corpus, graded by Google Research's own vendored
verifier). Every other name in the proxy registry remains proxy-tier. A
``real`` harness therefore registers one benchmark, not seven, and
deliberately does not backfill the rest — see
``EvalHarness._register_real_benchmarks``.

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
            self._register_real_benchmarks()
            self.fidelity = "real"
            return
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

    def _register_real_benchmarks(self) -> None:
        """Register only official-dataset/official-harness adapters.

        A ``real`` harness registers a **strict subset** of a proxy harness's
        benchmarks — one, currently — and does not backfill the rest from the
        proxy registry. Mixing the tiers behind one ``fidelity`` label is the
        specific dishonesty SPEC-202's two-tier model exists to prevent: a
        caller reading ``harness.fidelity == "real"`` off a harness whose
        swebench score came from 8 handcrafted samples has been misled by the
        object it asked.

        Consequence, called out because it is easy to trip over: a real harness
        evaluates fewer benchmarks, so ``compute_fitness`` sees fewer
        ``eval_scores``. Do not compare a real-harness fitness number to a
        proxy-harness one.
        """
        from .benchmarks import REAL_BENCHMARKS

        if not REAL_BENCHMARKS:
            raise ValueError(
                "benchmark_fidelity='real' requested but no real-benchmark "
                "adapters are registered (SPEC-202). Use 'proxy' (default)."
            )
        for name, runner in REAL_BENCHMARKS.items():
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
                if self.fidelity == "real":
                    # Silently skipping is tolerable at proxy tier (a caller
                    # naming an unknown benchmark gets fewer results and no
                    # false ones). At real tier it is not: the likely cause is
                    # "this benchmark has no real adapter yet", and returning a
                    # short list makes that look like a clean run over
                    # everything asked for. Say which ones are missing.
                    available = ", ".join(sorted(self._benchmarks)) or "none"
                    raise ValueError(
                        f"no real-fidelity adapter for benchmark {name!r}; "
                        f"available at real fidelity: {available}. Real adapters "
                        "are not backfilled from the proxy registry — see "
                        "EvalHarness._register_real_benchmarks."
                    )
                continue
            result = await runner(genome, llm_call)
            results.append(result)
        return results
