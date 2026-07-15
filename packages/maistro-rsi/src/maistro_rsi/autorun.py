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
import json
import time
import uuid
from collections.abc import Callable
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
from maistro_rsi.htr import HypothesisTree
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


def build_prompt(context: HtrContext) -> str:
    """The experiment brief a coding agent receives: the hypothesis to test,
    grounded in the lineage's distilled insights, with the ground rules."""
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
    return "\n".join(lines)


def template_proposer(context: HtrContext) -> str:
    """Deterministic fallback proposer: refine the seed hypothesis textually."""
    attempt = len(context.tree.nodes)
    return f"Refinement #{attempt} of: {context.node.hypothesis}"


def make_llm_proposer(model: str | None = None) -> HypothesisProposer:
    """An LLM-backed proposer over the connected LiteLLM instance.

    `HypothesisProposer` is synchronous by contract, so this uses a short
    blocking HTTP call; any failure falls back to `template_proposer` — the
    loop degrades to deterministic refinement rather than dying.
    """

    def _propose(context: HtrContext) -> str:
        settings = get_settings()
        insights = "\n".join(f"- {i}" for i in context.insights) or "- (none yet)"
        prompt = (
            "You steer an autonomous code-improvement experiment loop.\n"
            f"Current branch of inquiry: {context.node.hypothesis}\n"
            f"Distilled lessons so far:\n{insights}\n\n"
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
        prompt = build_prompt(context)
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


async def run_autonomous(
    config: AutorunConfig,
    *,
    executor: ExecutorFn | None = None,
    proposer: HypothesisProposer | None = None,
    audit: AuditLog | None = None,
) -> CoordinatorResult:
    """Run the full autonomous experimentation loop and return the grown tree.

    `executor`/`proposer`/`audit` are injectable for tests; production wiring is
    the default. The wall-clock budget is enforced between cycles.
    """
    run_id = uuid.uuid4().hex[:10]
    active_audit = audit or AuditLog(Path(config.workspace_root) / f"autorun-{run_id}.jsonl")
    active_executor = executor or build_executor(config, audit=active_audit)
    active_proposer = proposer or make_llm_proposer(config.model)

    tree = HypothesisTree(config.root_hypothesis)
    for hypothesis in config.seed_hypotheses:
        tree.expand(tree.root_id, hypothesis)

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

    result = CoordinatorResult(tree=tree, steps=steps)
    best = result.best
    await logger.ainfo(
        "rsi_autorun_complete",
        run_id=run_id,
        steps=len(steps),
        best_node=best.id if best else None,
        best_score=best.score if best else None,
        audit=str(active_audit.path),
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
    "build_executor",
    "build_prompt",
    "default_genome",
    "main",
    "make_llm_proposer",
    "run_autonomous",
    "template_proposer",
]
