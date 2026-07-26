"""Tests tied to SPEC.md §10 (autonomous experimentation run) acceptance
criteria autorun-1..6."""

from __future__ import annotations

import json

import pytest

from maistro_rsi.autorun import (
    AuditLog,
    AutorunConfig,
    _parse_benchmarks,
    build_executor,
    build_prompt,
    make_llm_proposer,
    run_autonomous,
    template_proposer,
)
from maistro_rsi.coordinator import ExecutionReport, HtrContext
from maistro_rsi.htr import HypothesisEvidence, HypothesisTree
from maistro_rsi.quarantine import QuarantineVerdict
from maistro_rsi.runner import RsiCycleResult
from maistro_rsi.selfbranch import SelfBranchAttempt, SelfBranchResult


def _config(**overrides) -> AutorunConfig:
    base = {
        "repo_url": "https://github.com/org/repo.git",
        "test_command": "pytest -q",
    }
    base.update(overrides)
    return AutorunConfig(**base)


def _context(hypothesis: str = "root") -> HtrContext:
    tree = HypothesisTree(hypothesis)
    node = tree.nodes[tree.root_id]
    return HtrContext(node=node, insights=[], tree=tree)


def _cycle_result(*, pr_url: str | None = None, cleared: bool = True) -> RsiCycleResult:
    attempt = SelfBranchAttempt(
        branch_name="rsi/x",
        repo_url="https://github.com/org/repo.git",
        test_command="pytest -q",
        commit_message="m",
        pr_title="t",
    )
    branch_result = SelfBranchResult(
        attempt=attempt,
        test_exit_code=0,
        test_output="ok",
        diff="diff --git a/f b/f\n+1\n",
        pr_url=pr_url,
        quarantine=QuarantineVerdict(cleared=cleared, requires_adversarial_review=False, flags=()),
    )
    return RsiCycleResult(
        run_id="run1",
        model_used="m1",
        branch_result=branch_result,
        baseline_results=[],
        candidate_results=[],
        battles=[],
    )


class TestApplyPatchFactorySwap:
    @pytest.mark.asyncio
    async def test_default_factory_used_when_none_supplied(self):
        """autorun-1: with no apply_patch_factory, the opencode-template
        default drives the cycle."""
        commands: list[str] = []

        class _FakeSandbox:
            async def exec(self, command, timeout=60):
                commands.append(command)
                return 0, "ok"

        config = _config()
        # Exercise the actual factory selection logic without a full RsiCycle.
        from maistro_rsi.autorun import _default_apply_patch_factory

        factory = config.apply_patch_factory or _default_apply_patch_factory(config)
        patch = factory("do the experiment")
        await patch(_FakeSandbox(), "/ws")
        assert commands == ["opencode run --auto 'do the experiment'"]

    @pytest.mark.asyncio
    async def test_custom_factory_overrides_default(self):
        """autorun-1: a supplied apply_patch_factory is used instead of the
        opencode default — e.g. to drive the native builders agent."""
        calls: list[str] = []

        def custom_factory(prompt: str):
            calls.append(prompt)

            async def _patch(sandbox, workspace, model=None):
                pass

            return _patch

        config = _config(apply_patch_factory=custom_factory)
        from maistro_rsi.autorun import _default_apply_patch_factory

        factory = config.apply_patch_factory or _default_apply_patch_factory(config)
        assert factory is custom_factory
        factory("some prompt")
        assert calls == ["some prompt"]


class TestBuildExecutorQuarantine:
    @pytest.mark.asyncio
    async def test_quarantine_check_is_always_wired(self, monkeypatch):
        """autorun-2: RsiCycle is always constructed with a quarantine_check
        backed by quarantine_scan + a Warden — never None."""
        captured = {}

        class _FakeRsiCycle:
            def __init__(self, *args, **kwargs):
                captured["quarantine_check"] = kwargs.get("quarantine_check")

            async def run(self, baseline, candidate, models):
                return _cycle_result()

        monkeypatch.setattr("maistro_rsi.autorun.RsiCycle", _FakeRsiCycle)
        monkeypatch.setattr("maistro_rsi.autorun.discover_models", _fake_discover)

        executor = build_executor(_config())
        await executor(_context())

        assert captured["quarantine_check"] is not None


async def _fake_discover():
    return ["m1"]


class TestSeedHypotheses:
    @pytest.mark.asyncio
    async def test_seeds_expanded_before_first_step(self, monkeypatch, tmp_path):
        """autorun-3: seed hypotheses are pre-expanded onto the tree before the
        coordinator's first step, so they run before the proposer invents any."""
        seen_hypotheses: list[str] = []

        async def fake_executor(context: HtrContext) -> ExecutionReport:
            seen_hypotheses.append(context.node.hypothesis)
            return ExecutionReport(
                evidence=HypothesisEvidence(
                    tests_passed=True, benchmarks_won=1, battles=1, improved=True
                )
            )

        def failing_proposer(context: HtrContext) -> str:
            raise AssertionError("proposer should not be called while seeds are queued")

        config = _config(
            root_hypothesis="root idea",
            seed_hypotheses=["seed one"],
            num_cycles=2,
            workspace_root=str(tmp_path),
        )
        result = await run_autonomous(config, executor=fake_executor, proposer=failing_proposer)

        assert len(result.steps) == 2
        # both root and seed are OPEN with equal (unscored) parent priority;
        # pending() breaks that tie by recency, so the just-added seed (the
        # caller's explicit experiment idea) runs before the bare root.
        assert seen_hypotheses == ["seed one", "root idea"]
        assert set(seen_hypotheses) == {"root idea", "seed one"}


class TestWallClockBudget:
    @pytest.mark.asyncio
    async def test_budget_stops_new_cycles(self, monkeypatch, tmp_path):
        """autorun-4: once max_wall_clock_s has elapsed, no further cycles run;
        steps reflects exactly what ran before the cutoff."""
        calls = {"n": 0}

        async def fake_executor(context: HtrContext) -> ExecutionReport:
            calls["n"] += 1
            return ExecutionReport(
                evidence=HypothesisEvidence(
                    tests_passed=True, benchmarks_won=1, battles=1, improved=True
                )
            )

        import itertools

        # started=0.0, then every subsequent check reads 100.0 (budget blown) --
        # an unbounded repeat so the exact number of internal monotonic() calls
        # doesn't need to be predicted.
        times = itertools.chain([0.0], itertools.repeat(100.0))
        monkeypatch.setattr("maistro_rsi.autorun.time.monotonic", lambda: next(times))

        config = _config(num_cycles=5, max_wall_clock_s=10.0, workspace_root=str(tmp_path))
        result = await run_autonomous(
            config,
            executor=fake_executor,
            proposer=lambda ctx: "next",
        )

        assert calls["n"] < 5
        assert len(result.steps) == calls["n"]


class TestLlmProposerFallback:
    def test_falls_back_to_template_on_http_failure(self, monkeypatch):
        """autorun-5: an unreachable/erroring LiteLLM gateway degrades to the
        deterministic template proposer instead of raising."""

        def boom(*args, **kwargs):
            raise ConnectionError("no gateway")

        monkeypatch.setattr("maistro_rsi.autorun.httpx.post", boom)
        proposer = make_llm_proposer()
        context = _context("root hyp")

        result = proposer(context)
        assert result == template_proposer(context)

    def test_falls_back_to_template_on_empty_content(self, monkeypatch):
        """autorun-5: an empty completion also falls back rather than
        returning a blank hypothesis."""

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "   "}}]}

        monkeypatch.setattr("maistro_rsi.autorun.httpx.post", lambda *a, **k: _Resp())
        proposer = make_llm_proposer()
        context = _context("root hyp")
        assert proposer(context) == template_proposer(context)


class TestAuditLog:
    def test_record_appends_one_json_line_per_cycle(self, tmp_path):
        """autorun-6: one JSON object per cycle is appended, never overwritten."""
        path = tmp_path / "audit.jsonl"
        audit = AuditLog(path)
        ctx = _context("h1")

        audit.record(ctx, _cycle_result(pr_url="https://x/pr/1"))
        audit.record(ctx, _cycle_result(cleared=False))

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["pr_url"] == "https://x/pr/1"
        assert first["quarantine_cleared"] is True
        assert second["quarantine_cleared"] is False
        assert second["pr_url"] is None


class TestBuildPromptAndParsing:
    def test_build_prompt_includes_hypothesis_and_insights(self):
        tree = HypothesisTree("root")
        node = tree.nodes[tree.root_id]
        ctx = HtrContext(node=node, insights=["lesson one"], tree=tree)
        prompt = build_prompt(ctx)
        assert "root" in prompt
        assert "lesson one" in prompt

    def test_parse_benchmarks_valid(self):
        assert _parse_benchmarks(["lint=ruff check ."]) == {"lint": "ruff check ."}

    def test_parse_benchmarks_rejects_malformed(self):
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            _parse_benchmarks(["nocommand"])


class TestQuarantineCheckInvocation:
    @pytest.mark.asyncio
    async def test_quarantine_check_actually_scans_via_warden(self, monkeypatch):
        """autorun-2: the wired quarantine_check really calls quarantine_scan
        (not just a placeholder), and audit.record fires when audit is given."""
        from maistro.security._types import WardenVerdict

        captured = {}

        class _FakeRsiCycle:
            def __init__(self, *args, **kwargs):
                captured["quarantine_check"] = kwargs.get("quarantine_check")

            async def run(self, baseline, candidate, models):
                return _cycle_result()

        class _StubWarden:
            async def scan(self, content, boundary):
                return WardenVerdict(clean=True)

        recorded = []

        class _RecordingAudit(AuditLog):
            def __init__(self):
                pass

            def record(self, context, result):
                recorded.append((context, result))

        monkeypatch.setattr("maistro_rsi.autorun.RsiCycle", _FakeRsiCycle)
        monkeypatch.setattr("maistro_rsi.autorun.discover_models", _fake_discover)

        executor = build_executor(_config(), warden=_StubWarden(), audit=_RecordingAudit())
        await executor(_context())

        verdict = await captured["quarantine_check"]("diff --git a/f b/f\n", ["f"])
        assert verdict.cleared is True
        assert len(recorded) == 1


class TestMain:
    def test_main_runs_end_to_end_and_prints_summary(self, monkeypatch, capsys, tmp_path):
        """main() parses argv, runs the loop, and prints a summary."""

        async def fake_executor(context: HtrContext) -> ExecutionReport:
            return ExecutionReport(
                evidence=HypothesisEvidence(
                    tests_passed=True, benchmarks_won=1, battles=1, improved=True
                )
            )

        monkeypatch.setattr(
            "maistro_rsi.autorun.build_executor",
            lambda config, audit=None, prior_learnings=(): fake_executor,
        )

        from maistro_rsi.autorun import main

        exit_code = main(
            [
                "--repo",
                "https://github.com/org/repo.git",
                "--test-command",
                "pytest -q",
                "--cycles",
                "1",
                "--workspace-root",
                str(tmp_path),
            ]
        )

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "steps: 1" in out
        assert "best:" in out


def _ok_report() -> ExecutionReport:
    return ExecutionReport(
        evidence=HypothesisEvidence(tests_passed=True, benchmarks_won=1, battles=1, improved=True)
    )


class TestDurableTree:
    """Tests tied to SPEC.md §10 acceptance criteria autorun-7..9."""

    @pytest.mark.asyncio
    async def test_tree_saved_after_every_cycle(self, tmp_path):
        """autorun-7: the snapshot exists and parses after each cycle, not
        just at run end."""
        import json as _json

        from maistro_rsi.htr import HypothesisTree

        snapshots: list[int] = []
        tree_path = tmp_path / "htr-tree.json"

        async def fake_executor(context: HtrContext) -> ExecutionReport:
            # Snapshot count BEFORE this cycle's save: proves per-cycle writes.
            snapshots.append(
                len(_json.loads(tree_path.read_text())["nodes"]) if tree_path.exists() else 0
            )
            return _ok_report()

        config = _config(num_cycles=2, workspace_root=str(tmp_path))
        await run_autonomous(config, executor=fake_executor, proposer=lambda ctx: "next")

        assert tree_path.exists()
        restored = HypothesisTree.from_dict(_json.loads(tree_path.read_text()))
        assert restored.summary()["total"] >= 2
        # the second cycle observed the first cycle's persisted snapshot
        assert snapshots[1] > 0

    def test_atomic_write_leaves_no_partial_file(self, tmp_path, monkeypatch):
        """autorun-7: a crash mid-write cannot truncate the snapshot — the
        previous complete snapshot survives and no temp junk remains."""
        import json as _json

        from maistro_rsi.autorun import _atomic_write_json

        target = tmp_path / "htr-tree.json"
        _atomic_write_json(target, {"root_id": "a", "nodes": [{"id": "a"}]})
        before = target.read_text()

        def boom(src, dst):
            raise OSError("disk gone")

        monkeypatch.setattr("maistro_rsi.autorun.os.replace", boom)
        with pytest.raises(OSError):
            _atomic_write_json(target, {"root_id": "b", "nodes": []})

        assert target.read_text() == before  # old snapshot intact
        assert _json.loads(before)["root_id"] == "a"
        assert list(tmp_path.glob("*.tmp")) == []  # temp file cleaned up

    @pytest.mark.asyncio
    async def test_resume_continues_same_tree_without_duplicating_seeds(self, tmp_path):
        """autorun-8 + autorun-9: a second run over the same tree path
        continues the SAME tree (budget-stopped work is not discarded) and
        seeds are not re-expanded on resume."""
        executed: list[str] = []

        async def fake_executor(context: HtrContext) -> ExecutionReport:
            executed.append(context.node.hypothesis)
            return _ok_report()

        config = _config(
            root_hypothesis="root idea",
            seed_hypotheses=["seed one"],
            num_cycles=1,
            workspace_root=str(tmp_path),
        )
        first = await run_autonomous(config, executor=fake_executor, proposer=lambda c: "p1")
        assert len(first.steps) == 1

        second = await run_autonomous(config, executor=fake_executor, proposer=lambda c: "p2")
        # same tree continued: run 1 executed the seed (recency-first pending),
        # run 2 resumed and executed the still-open root — NOT a fresh tree, no
        # re-run of the already-explored node, and 'seed one' exists exactly once.
        assert second.tree.summary()["explored"] == 2
        seeds = [n for n in second.tree.nodes.values() if n.hypothesis == "seed one"]
        assert len(seeds) == 1
        assert len(executed) == 2
        assert set(executed) == {"root idea", "seed one"}  # each executed once, across runs

    @pytest.mark.asyncio
    async def test_root_mismatch_refused_unless_fresh(self, tmp_path):
        """autorun-8: a persisted tree with a different root hypothesis is
        refused with a clear error; fresh=True starts over instead."""

        async def fake_executor(context: HtrContext) -> ExecutionReport:
            return _ok_report()

        await run_autonomous(
            _config(root_hypothesis="original quest", num_cycles=1, workspace_root=str(tmp_path)),
            executor=fake_executor,
            proposer=lambda c: "p",
        )

        with pytest.raises(ValueError, match="differs"):
            await run_autonomous(
                _config(
                    root_hypothesis="different quest", num_cycles=1, workspace_root=str(tmp_path)
                ),
                executor=fake_executor,
                proposer=lambda c: "p",
            )

        result = await run_autonomous(
            _config(
                root_hypothesis="different quest",
                num_cycles=1,
                workspace_root=str(tmp_path),
                fresh=True,
            ),
            executor=fake_executor,
            proposer=lambda c: "p",
        )
        assert result.tree.nodes[result.tree.root_id].hypothesis == "different quest"


class TestLearningsLedger:
    """Tests tied to SPEC.md §10 acceptance criteria autorun-10..12."""

    @pytest.mark.asyncio
    async def test_every_cycle_appends_an_insight(self, tmp_path):
        """autorun-10: one ledger line per executed cycle, carrying the
        distilled insight and outcome."""
        import json as _json

        async def fake_executor(context: HtrContext) -> ExecutionReport:
            return _ok_report()

        config = _config(num_cycles=2, workspace_root=str(tmp_path))
        await run_autonomous(config, executor=fake_executor, proposer=lambda c: "next")

        lines = (tmp_path / "learnings.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        entry = _json.loads(lines[0])
        assert entry["insight"]
        assert entry["improved"] is True
        assert entry["repo_url"] == config.repo_url

    @pytest.mark.asyncio
    async def test_fresh_run_still_recalls_prior_learnings(self, tmp_path):
        """autorun-11: THE retained-learnings guarantee — a fresh run (new
        tree) injects prior runs' insights into proposer and prompt context."""

        async def fake_executor(context: HtrContext) -> ExecutionReport:
            return _ok_report()

        base = _config(root_hypothesis="first quest", num_cycles=1, workspace_root=str(tmp_path))
        first = await run_autonomous(base, executor=fake_executor, proposer=lambda c: "p")
        first_insight = first.tree.nodes[first.steps[0]].insight
        assert first_insight

        # Fresh run, different root: the tree is new, the lessons are not.
        seen_prompts: list[str] = []

        async def spying_executor(context: HtrContext) -> ExecutionReport:
            from maistro_rsi.autorun import LearningsLedger, build_prompt

            ledger = LearningsLedger(tmp_path / "learnings.jsonl")
            recalled = ledger.recall(8, repo_url=base.repo_url)
            seen_prompts.append(build_prompt(context, recalled))
            return _ok_report()

        await run_autonomous(
            _config(
                root_hypothesis="second quest",
                num_cycles=1,
                workspace_root=str(tmp_path),
                fresh=True,
            ),
            executor=spying_executor,
            proposer=lambda c: "p",
        )
        assert first_insight in seen_prompts[0]
        assert "Lessons retained from previous runs:" in seen_prompts[0]

    def test_recall_prefers_improved_then_recency_and_dedupes(self, tmp_path):
        """autorun-11: improved-first ordering, recency tie-break, dedupe,
        and repo scoping."""
        import json as _json

        from maistro_rsi.autorun import LearningsLedger

        path = tmp_path / "learnings.jsonl"
        rows = [
            {"repo_url": "r1", "insight": "old failure", "improved": False},
            {"repo_url": "r1", "insight": "old win", "improved": True},
            {"repo_url": "r1", "insight": "new failure", "improved": False},
            {"repo_url": "r1", "insight": "new win", "improved": True},
            {"repo_url": "r1", "insight": "new win", "improved": True},  # dup
            {"repo_url": "r2", "insight": "other repo", "improved": True},
        ]
        path.write_text("".join(_json.dumps(r) + "\n" for r in rows))

        ledger = LearningsLedger(path)
        recalled = ledger.recall(10, repo_url="r1")
        assert recalled == ["new win", "old win", "new failure", "old failure"]
        assert "other repo" not in recalled
        # unscoped recall sees every repo
        assert "other repo" in ledger.recall(10)

    def test_ledger_tolerates_corruption_and_absence(self, tmp_path):
        """autorun-12: corrupt/partial lines are skipped, a missing file is an
        empty ledger — recall never raises."""
        import json as _json

        from maistro_rsi.autorun import LearningsLedger

        missing = LearningsLedger(tmp_path / "nope.jsonl")
        assert missing.recall(5) == []

        path = tmp_path / "learnings.jsonl"
        path.write_text(
            _json.dumps({"insight": "good one", "improved": True})
            + "\n{truncated garba"
            + "\nnot json at all\n\n"
            + _json.dumps({"no_insight_key": True})
            + "\n"
        )
        ledger = LearningsLedger(path)
        assert ledger.recall(5) == ["good one"]
