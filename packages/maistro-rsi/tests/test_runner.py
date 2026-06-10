"""Tests tied to SPEC.md §5 (RSI cycle runner) acceptance criteria runner-1..5."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from maistro_evolve.tournament import EloTournament
from maistro_evolve.types import DAGTopology, EvalResult, EvalWeights, NodeGenome, PipelineGenome
from maistro_rsi.runner import RsiCycle, RsiCycleConfig
from maistro_rsi.selfbranch import SelfBranchResult


def _genome(genome_id: str) -> PipelineGenome:
    return PipelineGenome(
        id=genome_id,
        name=genome_id,
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


class FakeSandbox:
    def __init__(self, *, raise_on_exec: bool = False) -> None:
        self.destroyed = False
        self.raise_on_exec = raise_on_exec

    async def exec(self, command, timeout=60):
        if self.raise_on_exec:
            raise RuntimeError("sandbox blew up")
        return 0, "ok"

    async def destroy(self):
        self.destroyed = True


class FakeHarness:
    """Returns a fixed score map per genome id; benchmark sets can differ to exercise runner-2."""

    def __init__(self, scores: dict[str, dict[str, float]]) -> None:
        self._scores = scores

    async def evaluate_genome(self, genome, benchmarks=None, llm_call=None):
        per_benchmark = self._scores[genome.id]
        return [
            EvalResult(benchmark=name, score=score)
            for name, score in per_benchmark.items()
            if benchmarks is None or name in benchmarks
        ]


class FakeScheduler:
    def __init__(self, model: str | None = "openai/gpt-5") -> None:
        self._model = model

    async def next_model(self, available_models):
        return self._model


def _config(**overrides) -> RsiCycleConfig:
    base = {
        "repo_url": "https://github.com/org/repo.git",
        "test_command": "pytest -q",
        "benchmarks": ["swebench", "swebench_pro"],
    }
    base.update(overrides)
    return RsiCycleConfig(**base)


async def _noop_patch(sandbox, workspace) -> None:
    pass


@pytest.fixture
def patched_sandbox(monkeypatch):
    """Replace `create_microvm_sandbox` with a controllable fake; returns the fake instance holder."""
    holder: dict[str, FakeSandbox] = {}

    async def fake_create(workspace, settings=None, env=None):
        sandbox = holder.setdefault("sandbox", FakeSandbox())
        return sandbox

    monkeypatch.setattr("maistro_rsi.runner.create_microvm_sandbox", fake_create)
    return holder


@pytest.fixture
def patched_self_branch(monkeypatch):
    """Skip the real git/sandbox plumbing; the runner only needs a SelfBranchResult back."""

    async def fake_run_attempt(sandbox, workspace, attempt, apply_patch, open_pr=False):
        await apply_patch(sandbox, workspace)
        exit_code, output = await sandbox.exec(attempt.test_command)
        return SelfBranchResult(
            attempt=attempt,
            test_exit_code=exit_code,
            test_output=output,
            diff="diff",
        )

    monkeypatch.setattr("maistro_rsi.runner.run_self_branch_attempt", fake_run_attempt)


class TestRsiCycleRun:
    @pytest.mark.asyncio
    async def test_evaluates_baseline_and_candidate_on_configured_benchmarks(
        self,
        patched_sandbox,
        patched_self_branch,
    ):
        """runner-1: both genomes are evaluated on exactly RsiCycleConfig.benchmarks."""
        scores = {
            "baseline": {"swebench": 0.4, "swebench_pro": 0.2},
            "candidate": {"swebench": 0.6, "swebench_pro": 0.5},
        }
        cycle = RsiCycle(
            _config(benchmarks=["swebench", "swebench_pro"]),
            FakeHarness(scores),
            EloTournament(),
            FakeScheduler(),
            _noop_patch,
        )

        result = await cycle.run(_genome("baseline"), _genome("candidate"), ["openai/gpt-5"])

        assert {r.benchmark for r in result.baseline_results} == {"swebench", "swebench_pro"}
        assert {r.benchmark for r in result.candidate_results} == {"swebench", "swebench_pro"}

    @pytest.mark.asyncio
    async def test_battles_only_recorded_for_benchmarks_present_in_both_result_sets(
        self,
        patched_sandbox,
        patched_self_branch,
    ):
        """runner-2: a benchmark missing from either side is skipped, not battled with a missing score."""
        scores = {
            "baseline": {"swebench": 0.4, "swebench_pro": 0.2},
            "candidate": {"swebench": 0.6},  # no swebench_pro score for the candidate
        }
        cycle = RsiCycle(
            _config(benchmarks=["swebench", "swebench_pro"]),
            FakeHarness(scores),
            EloTournament(),
            FakeScheduler(),
            _noop_patch,
        )

        result = await cycle.run(_genome("baseline"), _genome("candidate"), ["openai/gpt-5"])

        assert len(result.battles) == 1
        assert result.battles[0].benchmark == "swebench"

    @pytest.mark.asyncio
    async def test_benchmarks_won_counts_only_outright_candidate_wins(
        self,
        patched_sandbox,
        patched_self_branch,
    ):
        """runner-3: draws and baseline wins do not count toward benchmarks_won."""
        scores = {
            "baseline": {"a": 0.5, "b": 0.5, "c": 0.7},
            "candidate": {"a": 0.5, "b": 0.9, "c": 0.3},  # a=draw, b=candidate win, c=baseline win
        }
        cycle = RsiCycle(
            _config(benchmarks=["a", "b", "c"]),
            FakeHarness(scores),
            EloTournament(),
            FakeScheduler(),
            _noop_patch,
        )

        result = await cycle.run(_genome("baseline"), _genome("candidate"), ["openai/gpt-5"])

        assert result.benchmarks_won == 1

    @pytest.mark.asyncio
    async def test_improved_requires_passing_tests_and_benchmark_majority(
        self,
        patched_sandbox,
        patched_self_branch,
        monkeypatch,
    ):
        """runner-4: improved is True only with BOTH a passing test suite and a benchmark majority."""
        winning_scores = {
            "baseline": {"a": 0.3, "b": 0.3},
            "candidate": {"a": 0.9, "b": 0.9},  # candidate wins both
        }

        # Case 1: tests pass + candidate wins majority -> improved
        cycle = RsiCycle(
            _config(benchmarks=["a", "b"]),
            FakeHarness(winning_scores),
            EloTournament(),
            FakeScheduler(),
            _noop_patch,
        )
        result_ok = await cycle.run(_genome("baseline"), _genome("candidate"), ["openai/gpt-5"])
        assert result_ok.improved is True

        # Case 2: candidate wins majority but tests fail -> not improved
        async def failing_attempt(sandbox, workspace, attempt, apply_patch, open_pr=False):
            await apply_patch(sandbox, workspace)
            return SelfBranchResult(attempt=attempt, test_exit_code=1, test_output="boom", diff="")

        monkeypatch.setattr("maistro_rsi.runner.run_self_branch_attempt", failing_attempt)
        result_failed_tests = await cycle.run(
            _genome("baseline"), _genome("candidate"), ["openai/gpt-5"]
        )
        assert result_failed_tests.improved is False

    @pytest.mark.asyncio
    async def test_sandbox_destroyed_even_when_apply_patch_raises(
        self, patched_sandbox, monkeypatch
    ):
        """runner-5: the sandbox is torn down even when the cycle fails mid-way."""
        scores = {"baseline": {"swebench": 0.5}, "candidate": {"swebench": 0.5}}

        async def boom_patch(sandbox, workspace):
            raise RuntimeError("agent crashed mid-patch")

        async def attempt_that_runs_the_patch(
            sandbox, workspace, attempt, apply_patch, open_pr=False
        ):
            await apply_patch(sandbox, workspace)
            raise AssertionError("apply_patch should have raised before this point")

        monkeypatch.setattr(
            "maistro_rsi.runner.run_self_branch_attempt", attempt_that_runs_the_patch
        )

        cycle = RsiCycle(
            _config(benchmarks=["swebench"]),
            FakeHarness(scores),
            EloTournament(),
            FakeScheduler(),
            boom_patch,
        )

        with pytest.raises(RuntimeError):
            await cycle.run(_genome("baseline"), _genome("candidate"), ["openai/gpt-5"])

        assert patched_sandbox["sandbox"].destroyed is True
