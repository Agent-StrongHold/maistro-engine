"""RSI cycle orchestration: branch on the agent's own codebase inside an
isolated sandbox, score baseline vs. candidate against the shared benchmark
suite, and let the existing Elo tournament decide whether the self-modification
actually won.

Deliberately thin — it composes pieces that already exist (or are scaffolded
alongside it) rather than reimplementing them:

- `maistro_rsi.sandbox`         → isolated execution (protocol-first; Docker today)
- `maistro_rsi.selfbranch`      → clone/branch/patch/test/PR via `maistro.tools.git`
- `maistro_rsi.quota_burn`      → pick the model with the most idle headroom
- `maistro_evolve.harness`      → run the (8 + RSI-added) benchmark suite
- `maistro_evolve.tournament`   → Elo battle: did the candidate beat the baseline?
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog

from maistro_evolve.harness import EvalHarness
from maistro_evolve.tournament import EloTournament, GenomeBattle
from maistro_evolve.types import EvalFidelity, EvalResult, PipelineGenome
from maistro_rsi.benchmarks import RSI_BENCHMARKS
from maistro_rsi.protocols import ApplyPatchFn
from maistro_rsi.quota_burn import QuotaBurnScheduler
from maistro_rsi.sandbox.microvm import create_microvm_sandbox
from maistro_rsi.selfbranch import SelfBranchResult, new_attempt, run_self_branch_attempt

logger = structlog.get_logger()

DEFAULT_BENCHMARKS = ["swebench", "swebench_pro", "terminalbench"]


@dataclass
class RsiCycleConfig:
    repo_url: str
    test_command: str
    workspace_root: str = "/tmp/maistro-workspace/rsi"
    benchmarks: list[str] = field(default_factory=lambda: list(DEFAULT_BENCHMARKS))
    open_prs: bool = False
    base_branch: str = "develop"


@dataclass
class RsiCycleResult:
    run_id: str
    model_used: str | None
    branch_result: SelfBranchResult
    baseline_results: list[EvalResult]
    candidate_results: list[EvalResult]
    battles: list[GenomeBattle]

    @property
    def benchmarks_won(self) -> int:
        return sum(1 for b in self.battles if b.winner_id == b.genome_b_id)

    @property
    def candidate_outperformed(self) -> bool:
        return self.branch_result.tests_passed and self.benchmarks_won > len(self.battles) / 2

    @property
    def promotion_eligible(self) -> bool:
        results = [*self.baseline_results, *self.candidate_results]
        return (
            bool(results)
            and all(result.promotion_eligible for result in results)
            and self.branch_result.quarantine is not None
            and self.branch_result.quarantine.cleared
        )

    @property
    def improved(self) -> bool:
        return self.candidate_outperformed and self.promotion_eligible


def build_harness(benchmark_fidelity: EvalFidelity = EvalFidelity.PROXY) -> EvalHarness:
    """An `EvalHarness` carrying both maistro-evolve's stock benchmarks and
    the longer-horizon ones added here (e.g. SWE-Bench Pro)."""
    harness = EvalHarness(benchmark_fidelity=benchmark_fidelity)
    for name, runner in RSI_BENCHMARKS.items():
        harness.register_benchmark(name, runner, fidelity=EvalFidelity.PROXY)
    return harness


class RsiCycle:
    """One end-to-end loop: branch → patch → test → evaluate → battle."""

    def __init__(
        self,
        config: RsiCycleConfig,
        harness: EvalHarness,
        tournament: EloTournament,
        scheduler: QuotaBurnScheduler,
        apply_patch: ApplyPatchFn,
    ) -> None:
        self._config = config
        self._harness = harness
        self._tournament = tournament
        self._scheduler = scheduler
        self._apply_patch = apply_patch

    async def run(
        self,
        baseline: PipelineGenome,
        candidate: PipelineGenome,
        available_models: list[str],
    ) -> RsiCycleResult:
        if self._config.open_prs:
            raise RuntimeError(
                "Direct PR creation is disabled for autonomous RSI cycles; "
                "publish proposal artifacts through the external approval gate"
            )
        run_id = uuid.uuid4().hex[:10]
        workspace = f"{self._config.workspace_root}/{run_id}"
        model = await self._scheduler.next_model(available_models)

        sandbox = await create_microvm_sandbox(workspace)
        try:
            attempt = new_attempt(
                self._config.repo_url,
                self._config.test_command,
                base_branch=self._config.base_branch,
            )
            branch_result = await run_self_branch_attempt(
                sandbox,
                workspace,
                attempt,
                self._apply_patch,
                open_pr=self._config.open_prs,
            )

            baseline_results = await self._harness.evaluate_genome(
                baseline,
                benchmarks=self._config.benchmarks,
            )
            candidate_results = await self._harness.evaluate_genome(
                candidate,
                benchmarks=self._config.benchmarks,
            )
            expected = set(self._config.benchmarks)
            baseline_seen = {result.benchmark for result in baseline_results}
            candidate_seen = {result.benchmark for result in candidate_results}
            if baseline_seen != expected or candidate_seen != expected:
                raise RuntimeError(
                    "RSI evaluation incomplete; "
                    f"expected={sorted(expected)} baseline={sorted(baseline_seen)} "
                    f"candidate={sorted(candidate_seen)}"
                )

            battles = [
                self._tournament.record_battle(
                    benchmark=b_res.benchmark,
                    genome_a_id=baseline.id,
                    genome_b_id=candidate.id,
                    score_a=b_res.score,
                    score_b=c_res.score,
                )
                for b_res, c_res in zip(baseline_results, candidate_results, strict=False)
                if b_res.benchmark == c_res.benchmark
            ]
        finally:
            await sandbox.destroy()

        result = RsiCycleResult(
            run_id=run_id,
            model_used=model,
            branch_result=branch_result,
            baseline_results=baseline_results,
            candidate_results=candidate_results,
            battles=battles,
        )

        await logger.ainfo(
            "rsi_cycle_complete",
            run_id=run_id,
            model=model,
            tests_passed=branch_result.tests_passed,
            benchmarks_won=result.benchmarks_won,
            benchmarks_total=len(battles),
            candidate_outperformed=result.candidate_outperformed,
            promotion_eligible=result.promotion_eligible,
            improved=result.improved,
            opened_pr=branch_result.pr_url is not None,
        )

        return result
