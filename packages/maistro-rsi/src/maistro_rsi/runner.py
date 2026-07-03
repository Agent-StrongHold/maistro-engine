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

import shutil
import uuid
from dataclasses import dataclass, field

import structlog

from maistro_evolve.harness import EvalHarness
from maistro_evolve.tournament import EloTournament, GenomeBattle
from maistro_evolve.types import EvalResult, PipelineGenome
from maistro_rsi.benchmarks import RSI_BENCHMARKS
from maistro_rsi.gateway import LlmCall, make_gateway_llm_call
from maistro_rsi.protocols import ApplyPatchFn
from maistro_rsi.quota_burn import QuotaBurnScheduler
from maistro_rsi.sandbox.microvm import create_microvm_sandbox
from maistro_rsi.selfbranch import (
    QuarantineCheckFn,
    SelfBranchResult,
    new_attempt,
    run_self_branch_attempt,
)

logger = structlog.get_logger()

DEFAULT_BENCHMARKS = ["swebench", "swebench_pro", "terminalbench"]


@dataclass
class RsiCycleConfig:
    repo_url: str
    test_command: str
    workspace_root: str = "/tmp/maistro-workspace/rsi"
    benchmarks: list[str] = field(default_factory=lambda: list(DEFAULT_BENCHMARKS))
    open_prs: bool = False
    base_branch: str = "main"
    # Keep the cloned workspace after the cycle (debugging). Default False:
    # long-running loops would otherwise slowly fill the disk with one clone
    # per run_id that nothing ever deletes.
    keep_workspace: bool = False


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
    def improved(self) -> bool:
        return self.branch_result.tests_passed and self.benchmarks_won > len(self.battles) / 2


def build_harness(use_real_benchmarks: bool = True) -> EvalHarness:
    """An `EvalHarness` carrying both maistro-evolve's stock benchmarks and
    the longer-horizon ones added here (e.g. SWE-Bench Pro)."""
    harness = EvalHarness(use_real_benchmarks=use_real_benchmarks)
    for name, runner in RSI_BENCHMARKS.items():
        harness.register_benchmark(name, runner)
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
        llm_call: LlmCall | None = None,
        quarantine_check: QuarantineCheckFn | None = None,
    ) -> None:
        self._config = config
        self._harness = harness
        self._tournament = tournament
        self._scheduler = scheduler
        self._apply_patch = apply_patch
        # When None, run() builds a gateway-backed llm_call from the
        # scheduler-chosen model so benchmark scoring is real, not heuristic.
        self._llm_call = llm_call
        # Without a quarantine_check, run_self_branch_attempt treats every
        # diff as cleared; callers that open PRs should always supply one.
        self._quarantine_check = quarantine_check

    async def run(
        self,
        baseline: PipelineGenome,
        candidate: PipelineGenome,
        available_models: list[str],
    ) -> RsiCycleResult:
        run_id = uuid.uuid4().hex[:10]
        workspace = f"{self._config.workspace_root}/{run_id}"
        model = await self._scheduler.next_model(available_models)

        # Real benchmark scoring needs an llm_call. Prefer an injected one
        # (tests); otherwise build a gateway-backed call routed to the
        # scheduler-chosen model — which also makes that choice (idle-quota
        # headroom) actually drive the eval instead of being decorative. If no
        # model is available, leave it None and the benchmarks score
        # heuristically (loudly non-real).
        llm_call = self._llm_call
        if llm_call is None and model:
            llm_call = make_gateway_llm_call(model)

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
                quarantine_check=self._quarantine_check,
                model=model,
            )

            baseline_results = await self._harness.evaluate_genome(
                baseline,
                benchmarks=self._config.benchmarks,
                llm_call=llm_call,
            )
            candidate_results = await self._harness.evaluate_genome(
                candidate,
                benchmarks=self._config.benchmarks,
                llm_call=llm_call,
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
            if not self._config.keep_workspace:
                shutil.rmtree(workspace, ignore_errors=True)

        # Close the quota-burn feedback loop: without recording usage, the
        # scheduler ranks against a tracker nothing writes to and keeps picking
        # the same model. Gateway-built llm_calls expose cumulative counters.
        usage_in = int(getattr(llm_call, "usage_input", 0) or 0)
        usage_out = int(getattr(llm_call, "usage_output", 0) or 0)
        if model and (usage_in or usage_out):
            await self._scheduler.record_attempt(model, usage_in, usage_out)

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
            improved=result.improved,
            opened_pr=branch_result.pr_url is not None,
        )

        return result
