"""Autonomous exploratory RSI runs: assemble the HTR loop into a launchable driver.

This is the *auto-experimentation* variant of RSI — distinct from directed
cleanup runs. `HtrCoordinator` grows a `HypothesisTree`; each cycle a CLI coding
agent (opencode by default, via `apply_agents`) attempts one hypothesis against
a fresh checkout, and *differential workspace probes* (`RsiCycleConfig
.benchmark_commands`) measure what the patch actually did; the Elo tournament
keeps or prunes the branch. Every diff is Warden-quarantined before it may leave
the sandbox as a PR, and every cycle is appended to a JSONL audit log.

Launch (inside an sbx sandbox or any environment with the agent binary):

    maistro-rsi-autorun --repo <url> --test-command "pytest -q" \
        --benchmark "lint=ruff check -q . && echo 1.0 || echo 0.0" --cycles 5
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog

from maistro.config.settings import get_settings
from maistro.quota.tracker import InMemoryQuotaTracker
from maistro.security.warden.detector import Warden
from maistro_evolve.tournament import EloTournament
from maistro_evolve.types import DAGTopology, EvalWeights, NodeGenome, PipelineGenome
from maistro_rsi.apply_agents import OPENCODE_TEMPLATE, command_apply_patch
from maistro_rsi.coordinator import (
    CoordinatorResult,
    ExecutionReport,
    ExecutorFn,
    HtrContext,
    HtrCoordinator,
    HypothesisProposer,
    report_from_cycle_result,
)
from maistro_rsi.htr import HypothesisNode, HypothesisTree
from maistro_rsi.protocols import ApplyPatchFn
from maistro_rsi.quarantine import QuarantineVerdict, quarantine_scan
from maistro_rsi.quota_burn import QuotaBurnScheduler, discover_models
from maistro_rsi.runner import (
    DEFAULT_WORKSPACE_ROOT,
    RsiCycle,
    RsiCycleConfig,
    RsiCycleResult,
    build_harness,
)

logger = structlog.get_logger()

_DEFAULT_ROOT_HYPOTHESIS = (
    "Find one small, measurable improvement to this codebase that keeps the test suite green."
)


@dataclass
class AutorunConfig:
    """Everything one autonomous experimentation run needs."""

    repo_url: str
    test_command: str
    root_hypothesis: str = _DEFAULT_ROOT_HYPOTHESIS
    # Experiment ideas queued ahead of the LLM proposer; the root hypothesis is
    # itself the first executed experiment, these refine it.
    seed_hypotheses: list[str] = field(default_factory=list)
    # Differential probes: name -> shell command (see RsiCycleConfig).
    benchmark_commands: dict[str, str] = field(default_factory=dict)
    num_cycles: int = 3
    agent_template: str = OPENCODE_TEMPLATE
    # Pluggable code-modification driver: given the experiment prompt, return
    # an ApplyPatchFn. Defaults to the opencode template driver
    # (command_apply_patch); pass e.g.
    # ``lambda prompt: make_builders_apply_patch(prompt)`` (maistro_rsi.local_loop)
    # to drive the native builders agent instead -- both satisfy the same
    # 3-arg ApplyPatchFn the RsiCycle consumes. opencode is one option among
    # several, not the only one.
    apply_patch_factory: Callable[[str], ApplyPatchFn] | None = None
    model: str | None = None
    open_prs: bool = False
    workspace_root: str = DEFAULT_WORKSPACE_ROOT
    base_branch: str = "main"
    # Stop growing the tree once this much wall-clock has elapsed (checked
    # between cycles; a running cycle is never interrupted).
    max_wall_clock_s: float | None = None
    # Explicit model pool; when empty, discovered from LiteLLM at run start.
    available_models: list[str] = field(default_factory=list)
    # -- durable memory (resumable tree + retained learnings) -----------------
    # Tree snapshot: saved atomically after EVERY cycle; loaded (and continued)
    # on the next run unless `fresh` is set. None -> <workspace_root>/htr-tree.json.
    tree_path: str | None = None
    # Start a new tree even if a snapshot exists (the snapshot is overwritten
    # on the first cycle). Learnings are STILL recalled -- fresh discards the
    # tree, never the lessons.
    fresh: bool = False
    # Learnings ledger: append-only JSONL of distilled insights that outlives
    # any single tree. None -> <workspace_root>/learnings.jsonl.
    learnings_path: str | None = None
    # How many prior insights to inject into proposer/prompt context.
    recall_top_k: int = 8


def build_prompt(context: HtrContext, prior_learnings: Sequence[str] = ()) -> str:
    """The experiment brief a coding agent receives: the hypothesis to test,
    grounded in the lineage's distilled insights (this tree) and the retained
    learnings recalled from previous runs (any tree), with the ground rules."""
    lines = [
        f"Hypothesis to test: {context.node.hypothesis}",
        "",
        "You are one experiment in an autonomous improvement loop. Make the",
        "smallest focused change that tests this hypothesis. Keep the test",
        "suite green. Do not touch CI config or credentials.",
    ]
    if context.insights:
        lines += ["", "Lessons from earlier experiments on this branch of inquiry:"]
        lines += [f"- {insight}" for insight in context.insights]
    lineage = set(context.insights)
    retained = [lesson for lesson in prior_learnings if lesson not in lineage]
    if retained:
        lines += ["", "Lessons retained from previous runs:"]
        lines += [f"- {lesson}" for lesson in retained]
    return "\n".join(lines)


def template_proposer(context: HtrContext) -> str:
    """Deterministic fallback proposer: refine the seed hypothesis textually."""
    attempt = len(context.tree.nodes)
    return f"Refinement #{attempt} of: {context.node.hypothesis}"


def make_llm_proposer(
    model: str | None = None, prior_learnings: Sequence[str] = ()
) -> HypothesisProposer:
    """An LLM-backed proposer over the connected LiteLLM instance.

    `HypothesisProposer` is synchronous by contract, so this uses a short
    blocking HTTP call; any failure falls back to `template_proposer` — the
    loop degrades to deterministic refinement rather than dying.
    """

    def _propose(context: HtrContext) -> str:
        settings = get_settings()
        lineage = set(context.insights)
        combined = list(context.insights) + [
            lesson for lesson in prior_learnings if lesson not in lineage
        ]
        insights = "\n".join(f"- {i}" for i in combined) or "- (none yet)"
        prompt = (
            "You steer an autonomous code-improvement experiment loop.\n"
            f"Current branch of inquiry: {context.node.hypothesis}\n"
            f"Distilled lessons so far (this run and previous runs):\n{insights}\n\n"
            "Propose the single most promising NEXT hypothesis to test — one "
            "sentence, concrete and measurable. Reply with the hypothesis only."
        )
        try:
            response = httpx.post(
                settings.litellm.base_url.rstrip("/") + "/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.litellm.master_key}"},
                json={
                    "model": model or "default",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            text = str(response.json()["choices"][0]["message"]["content"]).strip()
            if text:
                return text.splitlines()[0][:500]
        except Exception as exc:
            logger.warning("rsi_llm_proposer_failed", error=str(exc))
        return template_proposer(context)

    return _propose


def default_genome(genome_id: str, *, model: str = "default") -> PipelineGenome:
    """A minimal single-node genome so tournament bookkeeping has identities to
    battle under. In the experimentation loop the *evidence* comes from the
    workspace probes, not the genome topology."""
    now = datetime.now(UTC).isoformat()
    return PipelineGenome(
        id=genome_id,
        name=genome_id,
        topology=DAGTopology(
            nodes=[
                NodeGenome(
                    id="worker",
                    role="queen",
                    strategy="react",
                    model=model,
                    temperature=0.2,
                    max_tokens=4096,
                    system_prompt="autorun",
                    max_tool_rounds=5,
                )
            ],
            edges=[],
            entry_node="worker",
            max_cycles=3,
            beam_width=1,
            use_scout=False,
        ),
        eval_weights=EvalWeights(),
        created_at=now,
        updated_at=now,
    )


class AuditLog:
    """Append-only JSONL trail: one record per executed experiment."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, context: HtrContext, result: RsiCycleResult) -> None:
        branch = result.branch_result
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "node_id": context.node.id,
            "depth": context.node.depth,
            "hypothesis": context.node.hypothesis,
            "run_id": result.run_id,
            "model": result.model_used,
            "tests_passed": branch.tests_passed,
            "benchmarks_won": result.benchmarks_won,
            "battles": len(result.battles),
            "improved": result.improved,
            "diff_lines": branch.diff.count("\n"),
            "baseline_metrics": branch.baseline_metrics,
            "candidate_metrics": branch.candidate_metrics,
            "quarantine_cleared": branch.quarantine.cleared if branch.quarantine else None,
            "quarantine_flags": list(branch.quarantine.flags) if branch.quarantine else [],
            "pr_url": branch.pr_url,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Write ``payload`` to ``path`` atomically (tmp file + os.replace in the
    same directory), so a crash mid-write can never leave a truncated snapshot
    — the previous complete snapshot survives instead (autorun-7)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


class LearningsLedger:
    """Append-only JSONL of distilled insights that outlives any single tree.

    This is the "retain learnings" half of durable memory: the tree snapshot
    makes a run *resumable*, but the ledger makes the *lessons* permanent — a
    ``--fresh`` run (new tree, new root, even a new disposable sbx sandbox over
    the same mounted workspace) still recalls what previous runs learned.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, *, repo_url: str, run_id: str, node: HypothesisNode) -> None:
        """Record one executed hypothesis's distilled insight (autorun-10)."""
        if not node.insight:
            return
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "repo_url": repo_url,
            "run_id": run_id,
            "node_id": node.id,
            "hypothesis": node.hypothesis,
            "insight": node.insight,
            "improved": bool(node.evidence.improved) if node.evidence else False,
            "tests_passed": bool(node.evidence.tests_passed) if node.evidence else False,
            "score": node.score,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _read_entries(self) -> list[dict[str, object]]:
        """Parse the ledger tolerantly: corrupt or partial lines are skipped
        with a warning (never raise) and a missing/unreadable file is an empty
        ledger (autorun-12)."""
        if not self.path.exists():
            return []
        try:
            raw_lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("rsi_learnings_read_failed", path=str(self.path), error=str(exc))
            return []
        entries: list[dict[str, object]] = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                logger.warning("rsi_learnings_corrupt_line_skipped", path=str(self.path))
                continue
            if isinstance(entry, dict) and entry.get("insight"):
                entries.append(entry)
        return entries

    def recall(self, top_k: int = 8, repo_url: str | None = None) -> list[str]:
        """Prior insights for prompt context, best-first: insights from
        experiments that actually *improved* the agent come before the rest,
        recency breaks ties, duplicates are dropped (autorun-11)."""
        entries = self._read_entries()
        if repo_url is not None:
            entries = [e for e in entries if e.get("repo_url") == repo_url]
        # Most recent first, then stable-sort improved wins to the front.
        entries.reverse()
        entries.sort(key=lambda e: not bool(e.get("improved")))
        seen: set[str] = set()
        insights: list[str] = []
        for entry in entries:
            insight = str(entry["insight"])
            if insight not in seen:
                seen.add(insight)
                insights.append(insight)
            if len(insights) >= top_k:
                break
        return insights


def _default_apply_patch_factory(config: AutorunConfig) -> Callable[[str], ApplyPatchFn]:
    """The opencode-template driver, closing over the configured template."""

    def _make(prompt: str) -> ApplyPatchFn:
        return command_apply_patch(prompt, template=config.agent_template)

    return _make


def build_executor(
    config: AutorunConfig,
    *,
    warden: Warden | None = None,
    audit: AuditLog | None = None,
    prior_learnings: Sequence[str] = (),
) -> ExecutorFn:
    """Wire one `RsiCycle` per hypothesis into the coordinator's executor seam.

    Safety defaults are deliberate: quarantine runs with `adversarial_review=None`,
    so a diff touching the agent's own containment surface *parks* (never ships
    as a PR) until a reviewer implementation exists.
    """
    active_warden = warden or Warden()
    harness = build_harness()
    tournament = EloTournament()
    scheduler = QuotaBurnScheduler(InMemoryQuotaTracker())
    cycle_config = RsiCycleConfig(
        repo_url=config.repo_url,
        test_command=config.test_command,
        workspace_root=config.workspace_root,
        open_prs=config.open_prs,
        base_branch=config.base_branch,
        benchmark_commands=dict(config.benchmark_commands),
    )

    async def _quarantine_check(diff: str, touched_paths: list[str]) -> QuarantineVerdict:
        return await quarantine_scan(diff, touched_paths, active_warden)

    async def _execute(context: HtrContext) -> ExecutionReport:
        prompt = build_prompt(context, prior_learnings)
        cycle = RsiCycle(
            cycle_config,
            harness,
            tournament,
            scheduler,
            (config.apply_patch_factory or _default_apply_patch_factory(config))(prompt),
            quarantine_check=_quarantine_check,
        )
        models = list(config.available_models) or await discover_models()
        result = await cycle.run(
            default_genome("baseline", model=config.model or "default"),
            default_genome(f"candidate-{context.node.id}", model=config.model or "default"),
            models,
        )
        if audit is not None:
            audit.record(context, result)
        return report_from_cycle_result(result)

    return _execute


def _load_or_create_tree(config: AutorunConfig, tree_path: Path) -> HypothesisTree:
    """Resume the persisted tree when one exists (and ``fresh`` is unset), else
    start a new one. Seeds are expanded only on a NEW tree — on resume they are
    already nodes and re-expanding would duplicate them (autorun-8).

    A persisted tree whose root hypothesis differs from the configured one is
    refused with a clear error: silently continuing a different investigation
    (or silently discarding one) are both wrong; ``fresh=True`` is the explicit
    way to start over.
    """
    if config.fresh or not tree_path.exists():
        tree = HypothesisTree(config.root_hypothesis)
        for hypothesis in config.seed_hypotheses:
            tree.expand(tree.root_id, hypothesis)
        return tree

    data = json.loads(tree_path.read_text(encoding="utf-8"))
    tree = HypothesisTree.from_dict(data)
    restored_root = tree.nodes[tree.root_id].hypothesis
    if restored_root != config.root_hypothesis:
        raise ValueError(
            f"persisted tree at {tree_path} has root hypothesis {restored_root!r}, "
            f"which differs from the configured {config.root_hypothesis!r}; "
            "pass --fresh to start a new tree (retained learnings still apply)"
        )
    logger.info(
        "rsi_autorun_tree_resumed",
        tree_path=str(tree_path),
        **tree.summary(),
    )
    return tree


async def run_autonomous(
    config: AutorunConfig,
    *,
    executor: ExecutorFn | None = None,
    proposer: HypothesisProposer | None = None,
    audit: AuditLog | None = None,
    ledger: LearningsLedger | None = None,
) -> CoordinatorResult:
    """Run the full autonomous experimentation loop and return the grown tree.

    Durable memory (autorun-7..12): the tree snapshot is written atomically
    after every cycle so the run is resumable, and each cycle's distilled
    insight is appended to the LearningsLedger so the *lessons* survive even a
    ``fresh`` tree. Prior learnings are recalled into the proposer and the
    experiment prompts on every start, resumed or fresh.

    `executor`/`proposer`/`audit`/`ledger` are injectable for tests; production
    wiring is the default. The wall-clock budget is enforced between cycles.
    """
    run_id = uuid.uuid4().hex[:10]
    tree_path = Path(config.tree_path or Path(config.workspace_root) / "htr-tree.json")
    active_ledger = ledger or LearningsLedger(
        config.learnings_path or Path(config.workspace_root) / "learnings.jsonl"
    )
    prior_learnings = active_ledger.recall(config.recall_top_k, repo_url=config.repo_url)

    active_audit = audit or AuditLog(Path(config.workspace_root) / f"autorun-{run_id}.jsonl")
    active_executor = executor or build_executor(
        config, audit=active_audit, prior_learnings=prior_learnings
    )
    active_proposer = proposer or make_llm_proposer(config.model, prior_learnings=prior_learnings)

    tree = _load_or_create_tree(config, tree_path)

    coordinator = HtrCoordinator(tree, active_executor)
    started = time.monotonic()
    steps: list[str] = []
    for _ in range(config.num_cycles):
        budget = config.max_wall_clock_s
        if budget is not None and time.monotonic() - started >= budget:
            await logger.awarning("rsi_autorun_budget_exhausted", steps=len(steps))
            break
        partial = await coordinator.run(1, active_proposer)
        steps.extend(partial.steps)
        # Durable memory after EVERY cycle: crash/kill loses at most the
        # in-flight cycle, and the distilled insight is already permanent.
        _atomic_write_json(tree_path, tree.to_dict())
        for node_id in partial.steps:
            active_ledger.append(repo_url=config.repo_url, run_id=run_id, node=tree.nodes[node_id])

    result = CoordinatorResult(tree=tree, steps=steps)
    best = result.best
    await logger.ainfo(
        "rsi_autorun_complete",
        run_id=run_id,
        steps=len(steps),
        best_node=best.id if best else None,
        best_score=best.score if best else None,
        audit=str(active_audit.path),
        tree=str(tree_path),
        learnings=str(active_ledger.path),
        prior_learnings_recalled=len(prior_learnings),
    )
    return result


def _parse_benchmarks(pairs: list[str]) -> dict[str, str]:
    """Parse repeated ``name=command`` options into the benchmark map."""
    commands: dict[str, str] = {}
    for pair in pairs:
        name, sep, command = pair.partition("=")
        if not sep or not name.strip() or not command.strip():
            raise argparse.ArgumentTypeError(f"expected NAME=COMMAND, got: {pair!r}")
        commands[name.strip()] = command.strip()
    return commands


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maistro-rsi-autorun",
        description="Autonomous exploratory RSI: hypothesis loop over a repo.",
    )
    parser.add_argument("--repo", required=True, help="git URL of the repo to experiment on")
    parser.add_argument("--test-command", required=True, help="test suite command")
    parser.add_argument("--cycles", type=int, default=3, help="number of experiments to run")
    parser.add_argument("--hypothesis", default=_DEFAULT_ROOT_HYPOTHESIS, help="root hypothesis")
    parser.add_argument(
        "--seed", action="append", default=[], help="extra seed hypothesis (repeatable)"
    )
    parser.add_argument(
        "--benchmark",
        action="append",
        default=[],
        metavar="NAME=COMMAND",
        help="differential workspace probe (repeatable)",
    )
    parser.add_argument("--agent-template", default=OPENCODE_TEMPLATE)
    parser.add_argument("--model", default=None, help="model for proposer/genomes")
    parser.add_argument("--open-prs", action="store_true")
    parser.add_argument("--workspace-root", default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--max-seconds", type=float, default=None, help="wall-clock budget")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="start a new tree even if a snapshot exists (retained learnings still apply)",
    )
    parser.add_argument(
        "--tree-path", default=None, help="tree snapshot path (default: <workspace>/htr-tree.json)"
    )
    parser.add_argument(
        "--learnings-path",
        default=None,
        help="learnings ledger path (default: <workspace>/learnings.jsonl)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    config = AutorunConfig(
        repo_url=args.repo,
        test_command=args.test_command,
        root_hypothesis=args.hypothesis,
        seed_hypotheses=list(args.seed),
        benchmark_commands=_parse_benchmarks(args.benchmark),
        num_cycles=args.cycles,
        agent_template=args.agent_template,
        model=args.model,
        open_prs=args.open_prs,
        workspace_root=args.workspace_root,
        base_branch=args.base_branch,
        max_wall_clock_s=args.max_seconds,
        fresh=args.fresh,
        tree_path=args.tree_path,
        learnings_path=args.learnings_path,
    )
    result = asyncio.run(run_autonomous(config))
    best = result.best
    print(f"steps: {len(result.steps)}")
    if best is not None:
        print(f"best: [{best.score}] {best.hypothesis}")
    return 0


__all__ = [
    "AuditLog",
    "AutorunConfig",
    "LearningsLedger",
    "build_executor",
    "build_prompt",
    "default_genome",
    "main",
    "make_llm_proposer",
    "run_autonomous",
    "template_proposer",
]
