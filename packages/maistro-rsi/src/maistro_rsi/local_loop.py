"""Safe, capped, *local* recursive-self-improvement loop.

The full `RsiCycle` (`maistro_rsi.runner`) runs inside a Docker micro-VM, drives
an external coding agent (Codex CLI), scores candidates against SWE-Bench-class
benchmarks, and can open PRs. That is the eventual shape. This module is the
first, deliberately small increment underneath it:

  - **Native provider.** The patch is produced by the *native* builders agent
    loop (`maistro_bootstrap.builders` — the same engine behind `maistro
    builders`), wrapped as an `ApplyPatchFn`. No external Codex dependency.
  - **Safe + local.** Everything happens in throwaway git worktrees under a
    work root. The user's real checkout and its branches are never touched, and
    nothing is pushed or PR'd. The only "commit" is to an internal
    ``rsi-baseline`` branch inside a *clone*.
  - **Tests gate every promotion.** A cycle's candidate is promoted to the new
    baseline only if it (a) actually changed something and (b) the repo's own
    test command passes. This is the recursive ratchet — each accepted cycle
    becomes the base the next cycle builds on.
  - **Fixed cap.** The loop runs at most ``max_cycles`` cycles, so a first run
    is observable and can't run away. (Quota-headroom pacing via
    `maistro_rsi.quota_burn` is the next increment, not this one.)

It composes with the rest of the package: `LocalSandbox` satisfies the same
`MicroVmSandbox` protocol the micro-VM backend does, and the apply-patch
callable satisfies the same `ApplyPatchFn` the full runner consumes — so the
native provider built here drops straight into `RsiCycle` later.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from maistro_evolve.improvement import BudgetTier, ImprovementKind
from maistro_rsi.competitors import Competitor
from maistro_rsi.merge import greedy_merge
from maistro_rsi.protocols import ApplyPatchFn, MicroVmSandbox

logger = structlog.get_logger()

_DEFAULT_OBJECTIVE = (
    "Make exactly one small, safe, self-contained improvement to this codebase, "
    "in priority order: fix a real bug (test-first: add the failing test, then the "
    "fix), add a focused unit test for currently-untested behavior, strengthen a "
    "weak test assertion — and only if the code is already well-tested, improve a "
    "type hint or docstring. Read files before you edit them, keep the diff "
    "minimal, and do not break existing behavior. "
    "Use only the read_file, write_file and search tools — do NOT run git, "
    "commit, or shell commands: the harness stages, commits, and runs the tests "
    "for you after you finish. If you cannot find a safe improvement, make no "
    "changes and stop."
)


def _targeted_objective(path: str) -> str:
    """Build a per-cycle objective that names one explicit file to improve.

    Naming the file removes the discovery step that weak models fail at (they
    can't reliably search for a target), so each cycle is a concrete, bounded
    edit of a known file. Test-first by default: substantive verification work
    (a new test, a stronger assertion, a bug-fix) outranks docstring/type
    polish, which is a fallback only — mirroring the fitness signals
    (new_test/coverage-delta reward, doc-regression veto).
    """
    return (
        f"Improve the module `{path}`, in priority order: (1) add ONE focused unit test for "
        f"currently-untested behavior in it — create or extend its test file — and make sure it "
        f"passes; (2) fix a real bug if you find one, test-first (add the failing test, then the "
        f"fix); (3) strengthen a test assertion that checks too little. Only if the module is "
        f"already well-tested and correct, improve a type hint or docstring instead. First read "
        f"`{path}` with the read_file tool; use edit_file for targeted exact-string changes and "
        f"write_file only to create a new test file — do NOT rewrite existing files wholesale, "
        f"and do not reformat or touch lines unrelated to your change. Keep the diff minimal and "
        f"do not alter runtime behavior except to fix a bug. Edit only this module and its test "
        f"file. Do not run git or shell commands."
    )


# ---------------------------------------------------------------------------
# git plumbing (sync, shell=False — argv lists, no interpolation)
# ---------------------------------------------------------------------------


_GIT_CONFIG = (
    # core.longpaths lets git write objects when the worktree sits under a deep
    # path (a real hazard on Windows, where MAX_PATH is 260 and throwaway
    # worktrees nest under a work root). No-op elsewhere.
    "-c",
    "core.longpaths=true",
    # RSI commits are bot commits made in throwaway clones, which don't inherit
    # the source's (repo-local) identity and can't rely on a global one. Set the
    # identity per-invocation so commits never fail with "Author identity
    # unknown", independent of worktree/clone config inheritance.
    "-c",
    "user.email=rsi@maistro.local",
    "-c",
    "user.name=maistro-rsi",
)


def _git(
    cwd: Path, *args: str, check: bool = True, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *_GIT_CONFIG, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip()}")
    return proc


def _git_apply(cwd: Path, patch: str) -> bool:
    """Apply ``patch`` onto the worktree at ``cwd``; return whether it landed.

    A non-zero exit (a conflict with what's already applied) is the *signal*
    the greedy merge uses to drop a competing candidate — so this must not raise.
    """
    proc = subprocess.run(
        ["git", *_GIT_CONFIG, "apply", "--whitespace=nowarn", "-"],
        cwd=str(cwd),
        input=patch,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode == 0


def _scouted_objective(path: str, instruction: str) -> str:
    """Wrap a scout's concrete instruction in the agent's tool-use guidance so
    every competitor implements the *same* identified improvement."""
    return (
        f"Improve the file `{path}`. A reviewer identified this specific improvement:\n"
        f"  {instruction}\n"
        f"Implement exactly that. First read `{path}` with the read_file tool, then make the "
        f"change with the edit_file tool (a targeted exact-string replacement) — do NOT rewrite "
        f"the whole file, do not reformat unrelated lines, and do not alter runtime behavior. "
        f"Use only read_file and edit_file — do not run git or shell commands."
    )


def _guess_test_path(target: str) -> str:
    """Best-effort test file for a source path: ``.../pkg/src/mod.py`` →
    ``.../pkg/tests/test_mod.py``. Used to show the scout the module's existing
    tests so it can reason about weak assertions / missing cases."""
    t = target.replace("\\", "/")
    stem = t.rsplit("/", 1)[-1]
    name = stem[:-3] if stem.endswith(".py") else stem
    if "/src/" in t:
        pkg_root = t.split("/src/", 1)[0]
        return f"{pkg_root}/tests/test_{name}.py"
    return f"tests/test_{name}.py"


def _fixer_objective(path: str, kind: ImprovementKind, instruction: str) -> str:
    """The tiered base-fixer scaffold: implement one scout item, with rules keyed
    to its kind. FEATURE (v2.0) work is allowed to be ambitious and multi-file;
    everything else is a bounded, test-first, single-module change. This is the
    fixed task contract — the evolvable strategy layer is the genome's prompt."""
    if kind is ImprovementKind.FEATURE:
        return (
            f"Implement this enhancement to the `{path}` module:\n  {instruction}\n"
            "This is a substantial, ambitious change — design the improved capability or API and "
            "implement it across the files it needs. Prove it with NEW tests written first that "
            "specify the new behavior, and keep all existing tests green; preserve backward "
            "compatibility unless the enhancement explicitly supersedes it. Use read_file, "
            "edit_file and write_file across the files involved. Do not run git or shell commands."
        )
    return (
        f"Implement this specific improvement to `{path}`:\n  {instruction}\n"
        "Work test-first: add or extend the test for this module (create or extend its test file) "
        "so it fails against the current code, then change the code until it passes. Keep the diff "
        "minimal and focused on this one item — do not reformat or touch unrelated lines, and all "
        "existing tests must stay green. Edit only this module and its test file, using read_file, "
        "edit_file and write_file. Do not run git or shell commands."
    )


# ---------------------------------------------------------------------------
# LocalSandbox — a host-backed MicroVmSandbox
# ---------------------------------------------------------------------------


class LocalSandbox:
    """A `MicroVmSandbox` that runs directly on the host inside a worktree.

    No isolation beyond the working directory — this is the *safe local loop*
    backend, meant for running a self-improvement cycle against a throwaway
    clone of the repo, not for executing untrusted code. Snapshots are git
    commits so `restore` genuinely rewinds the tree (unlike the Docker backend,
    which can only record a label and rebuild from a ref).
    """

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)

    @property
    def workspace(self) -> Path:
        return self._workspace

    async def exec(self, command: str, timeout: int = 60) -> tuple[int, str]:
        def _run() -> tuple[int, str]:
            # shell=True: `command` is operator-supplied test/health config
            # (e.g. "pytest -q && ruff check"), not agent-controlled input.
            proc = subprocess.run(  # nosemgrep
                command,
                shell=True,  # nosemgrep
                cwd=str(self._workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

        return await asyncio.to_thread(_run)

    async def read_file(self, path: str) -> str:
        return await asyncio.to_thread((self._workspace / path).read_text, "utf-8")

    async def write_file(self, path: str, content: str) -> None:
        target = self._workspace / path

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        await asyncio.to_thread(_write)

    async def snapshot(self, label: str) -> str:
        del label  # bookkeeping only (microVM-backend parity); the id is the sha
        proc = await asyncio.to_thread(_git, self._workspace, "rev-parse", "HEAD")
        return proc.stdout.strip()

    async def restore(self, snapshot_id: str) -> None:
        await asyncio.to_thread(_git, self._workspace, "reset", "--hard", snapshot_id)

    async def destroy(self) -> None:
        # Worktrees are torn down by the loop that created them; nothing to do.
        return None

    async def __aenter__(self) -> LocalSandbox:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.destroy()


# ---------------------------------------------------------------------------
# Native builders provider — the ApplyPatchFn
# ---------------------------------------------------------------------------


def make_builders_apply_patch(
    objective: str = _DEFAULT_OBJECTIVE,
    *,
    model: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    system_prompt: str | None = None,
    max_agent_turns: int = 6,
    isolation: str = "local",
    image: str = "maistro-builders:latest",
) -> ApplyPatchFn:
    """Build an `ApplyPatchFn` that drives the native builders agent loop.

    Returns an async callable ``apply(sandbox, workspace)`` that points the
    builders coding agent (the same `TurnRunner` engine behind `maistro
    builders`) at ``workspace`` and asks it to carry out ``objective``. Up to
    ``max_agent_turns`` turns run so a single cycle can do multi-step work.

    ``isolation`` selects the BuilderSandbox:
      - ``"local"``    — `LocalWorktreeSandbox`, edits run on the host (fast).
      - ``"container"``— `ContainerBuilderSandbox`, the agent's edits and commands
        run inside an ephemeral Docker container (ADR-093), then sync back to the
        worktree for the loop to commit. Requires ``image`` to be built.

    Model resolution is left to `ResponsesAPICallable` (``model=None`` →
    ``MAISTRO_BUILDERS_MODEL``/``DEFAULT_MODEL`` from the loaded ``.env``).
    """

    async def _run_turns(session: object, cycle_model: str | None = None) -> None:
        from maistro_bootstrap.builders.agent_loop import AgentLoopConfig, TurnRunner
        from maistro_bootstrap.builders.responses_callable import ResponsesAPICallable

        # Factory `model` is an explicit operator choice and wins; otherwise the
        # per-cycle model (the quota-burn scheduler's pick, threaded through
        # ApplyPatchFn's third argument) applies.
        effective_model = model or cycle_model
        config = AgentLoopConfig(model=effective_model) if effective_model else AgentLoopConfig()
        runner = TurnRunner(session=session, config=config)  # type: ignore[arg-type]
        # 300s timeout: the code group load-balances across reasoning deployments
        # (gpt-oss-120b on Cerebras at 5 RPM) whose queueing + long generations
        # overran the default 120s in a live run (httpx.ReadTimeout).
        runner.set_llm(
            ResponsesAPICallable(
                model=effective_model,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                timeout=300.0,
            )
        )

        # The genome's evolvable strategy prompt (when supplied) becomes the system
        # message; otherwise the builders default. The task (objective) is the user
        # message either way, so mutation tunes *approach*, not the task contract.
        messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt or config.system_prompt},
            {"role": "user", "content": objective},
        ]
        for turn in range(max_agent_turns):
            result = await runner.execute_turn(messages=messages)
            content = result.get("content", "")
            await logger.ainfo(
                "rsi_local_agent_turn",
                turn=turn + 1,
                stop_reason=result.get("stop_reason"),
                content_preview=str(content)[:160],
            )
            # execute_turn resolves its own internal tool loop; a non-tool_use
            # stop means the agent considers this objective done.
            if result.get("stop_reason") not in ("tool_use", "max_turns"):
                break
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": "Continue if useful, otherwise stop."})

    async def apply(
        sandbox: MicroVmSandbox, workspace: str, cycle_model: str | None = None
    ) -> None:
        # Imported lazily so the package stays importable without the builders
        # extras installed (mirrors _builders_tui.py's own lazy import).
        from maistro_bootstrap.builders.session import BuilderSession

        work_path = Path(workspace)
        if isolation == "container":
            from maistro_bootstrap.builders.container_sandbox import ContainerBuilderSandbox

            with ContainerBuilderSandbox(work_path, image=image) as csbx:
                await _run_turns(BuilderSession(sandbox=csbx), cycle_model)
                # Agent ran isolated in the container; bring its edits back to the
                # host worktree so the loop can stage/commit/test them.
                csbx.sync_to_host()
        else:
            from maistro_bootstrap.builders.sandbox import LocalWorktreeSandbox

            await _run_turns(
                BuilderSession(sandbox=LocalWorktreeSandbox(work_path)), cycle_model
            )

    return apply


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


@dataclass
class LocalRsiConfig:
    """Inputs for one capped local self-improvement run."""

    repo_path: str
    test_command: str
    work_root: str
    max_cycles: int = 3
    objective: str = _DEFAULT_OBJECTIVE
    # Explicit files to improve, one per cycle (rotated). When set, each cycle
    # gets a targeted objective naming its file instead of the generic
    # `objective` — capable models edit a named file reliably, where weak ones
    # fail to discover a target by searching.
    targets: list[str] = field(default_factory=list)
    model: str | None = None
    agent_turns_per_cycle: int = 6
    # Larger turn budget for a FEATURE (v2.0) slot — ambitious, multi-file work
    # (ImprovementKind.FEATURE unlocks it; bounded kinds use agent_turns_per_cycle).
    feature_agent_turns: int = 15
    # "local" (host worktree) or "container" (ADR-093 Docker isolation).
    isolation: str = "local"
    sandbox_image: str = "maistro-builders:latest"
    baseline_branch: str = "rsi-baseline"
    test_timeout: int = 900
    # When True, promotion is decided by the full multi-signal Scorecard
    # (gates + weighted scores) instead of the bare test_command, and each
    # decision is logged via scorecard.explain(). Requires the quality tools
    # (ruff/mypy/bandit/coverage/…) to be importable in the run environment.
    use_fitness: bool = False
    coverage_source: str = "."
    # pytest args for the coverage run (e.g. a scoped test path). Empty means a
    # bare `pytest` — which, in a monorepo with many testpaths, runs the whole
    # suite every cycle; scope it to keep a fitness run tractable.
    coverage_pytest_args: str = ""
    # Tournament (ADR-070126-6386 / SPEC-070126-9d37). Each cycle runs every
    # competitor (a fixer config = evolve NodeGenome projection) on the same
    # target, scores them, and combines the results: same-region → highest
    # composite wins; disjoint regions → both kept. Empty ⇒ a single attempt
    # with `model` (the classic one-shot cycle).
    competitors: list[Competitor] = field(default_factory=list)
    # When set, one model reads the file and names the shared improvement all
    # competitors implement (a fairer head-to-head than each inventing its own).
    scout: bool = False
    scout_model: str | None = None
    # Stage 4 (ADR-070126-6386): when set, after the run each promotion is
    # exported here as a git-am-able patch plus a manifest.json, for the harvester
    # to open PRs grouped by file. This is the durable output of an isolated run.
    export_patches: str | None = None
    # Checkpointing for long runs. Every ``report_every`` cycles (0 = only at the
    # end), write a progress report (markdown + JSON) into ``report_dir`` and
    # refresh a rolling, harvestable patch export of everything promoted so far.
    # The baseline keeps ratcheting forward across the whole run — a checkpoint is
    # an observation point, not a reset — so each report covers cumulative
    # progress and the export always holds the complete promotion set to date
    # (recoverable if a long run is interrupted). Point ``report_dir`` at a path
    # OUTSIDE the edited workspace (e.g. a host-mounted dir) to get reports out of
    # an isolated run without exposing them to the agent.
    report_every: int = 0
    report_dir: str | None = None


@dataclass
class _VariantResult:
    """One competitor's attempt: its worktree/branch, whether it passed the
    gates, and its composite — the raw material the cycle ranks and merges."""

    branch: str
    cycle_dir: Path
    label: str = ""
    changed: bool = False
    accepted: bool = False
    composite: float = 0.0
    tests_passed: bool = False
    files_touched: int = 0
    changed_files: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class CycleOutcome:
    index: int
    changed: bool
    tests_passed: bool
    promoted: bool
    files_touched: int = 0
    target: str = ""
    note: str = ""
    composite: float = 0.0


@dataclass
class LocalRsiResult:
    cycles: list[CycleOutcome] = field(default_factory=list)
    baseline_dir: str = ""

    @property
    def promotions(self) -> int:
        return sum(1 for c in self.cycles if c.promoted)

    def summary(self) -> str:
        lines = [f"RSI local loop: {self.promotions}/{len(self.cycles)} cycles promoted"]
        for c in self.cycles:
            mark = (
                "[promoted]" if c.promoted else ("[no change]" if not c.changed else "[rejected]")
            )
            detail = f"tests={'pass' if c.tests_passed else 'fail'} files={c.files_touched}"
            tgt = f" {c.target}" if c.target else ""
            note = f" - {c.note}" if c.note else ""
            lines.append(f"  cycle {c.index}:{tgt} {mark}  ({detail}){note}")
        lines.append(f"  baseline: {self.baseline_dir} (branch {self.promotions} promotions deep)")
        return "\n".join(lines)


def build_checkpoint_report(
    cycles: list[CycleOutcome],
    *,
    total_planned: int,
    baseline_dir: str,
    window: int,
    label: str = "",
) -> tuple[str, dict[str, Any]]:
    """Render a progress report over ``cycles`` run so far — cumulative totals
    plus a detail of the most recent ``window`` cycles. Pure: derived entirely
    from the outcome list, so it's testable without git or an agent.

    Returns ``(markdown, machine_json)``. ``label`` distinguishes an interim
    checkpoint ("cycle 5") from the "final" report in headings.
    """
    done = len(cycles)
    promoted = [c for c in cycles if c.promoted]
    per_file = Counter(c.target for c in promoted if c.target)
    # Every promoted cycle counts — 0.0 is a valid promoted composite (a
    # non-fitness run defaults to 0.0, and an accepted scorecard can compose to
    # 0.0), so filtering truthy values would overstate the average.
    composites = [c.composite for c in promoted]
    avg_composite = round(sum(composites) / len(composites), 3) if composites else 0.0
    recent = cycles[-window:] if window > 0 else cycles
    heading = label or (f"cycle {done}" if done else "start")

    data: dict[str, Any] = {
        "checkpoint": heading,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "cycles_run": done,
        "cycles_planned": total_planned,
        "promotions": len(promoted),
        "promotion_rate": round(len(promoted) / done, 3) if done else 0.0,
        "avg_composite": avg_composite,
        "files_improved": dict(per_file),
        "baseline_dir": baseline_dir,
        "recent": [
            {
                "index": c.index,
                "target": c.target,
                "promoted": c.promoted,
                "changed": c.changed,
                "tests_passed": c.tests_passed,
                "files_touched": c.files_touched,
                "composite": c.composite,
                "note": c.note,
            }
            for c in recent
        ],
    }

    lines = [
        f"# RSI checkpoint — {heading} / {total_planned} planned",
        "",
        f"_generated {data['generated_at']}_",
        "",
        "## Cumulative",
        f"- Cycles run: **{done} / {total_planned}**",
        f"- Promotions: **{len(promoted)}** ({data['promotion_rate']:.0%} of cycles run)",
        f"- Distinct files improved: **{len(per_file)}**",
        f"- Avg composite (promoted): **{avg_composite}**",
        f"- Baseline: `{baseline_dir}` — {len(promoted)} promotions deep",
    ]
    if per_file:
        lines += ["", "## Per-file promotions"]
        lines += [f"- `{f}`: {n}" for f, n in per_file.most_common()]
    lines += ["", f"## Recent window (last {len(recent)} cycle(s))"]
    for c in recent:
        mark = "promoted" if c.promoted else ("no change" if not c.changed else "rejected")
        detail = f"composite={c.composite}" if c.promoted else c.note or ""
        tgt = f" {c.target}" if c.target else ""
        lines.append(f"- cycle {c.index}:{tgt} — **{mark}** {detail}".rstrip())
    return "\n".join(lines) + "\n", data


class LocalRsiLoop:
    """Run up to ``max_cycles`` self-improvement cycles against a throwaway clone.

    Each cycle branches a fresh worktree off the current baseline, lets the
    native builders agent patch it, runs the test command, and fast-forwards the
    baseline only if the change is real *and* green. Winners ratchet forward;
    losers are discarded. Nothing leaves the work root.
    """

    def __init__(self, config: LocalRsiConfig, apply_patch: ApplyPatchFn | None = None) -> None:
        self._config = config
        self._injected_apply = apply_patch
        self._baseline = Path(config.work_root) / "baseline"
        self._baseline_cov: float | None = None  # cached; invalidated on promote
        self._start_ref: str | None = None  # baseline sha before any promotion

    def _baseline_coverage(self) -> float | None:
        if not self._config.use_fitness:
            return None
        if self._baseline_cov is None:
            from maistro_evolve.coverage_gate import measure_coverage

            self._baseline_cov = measure_coverage(
                self._baseline,
                source=self._config.coverage_source,
                pytest_args=self._config.coverage_pytest_args,
            )
        return self._baseline_cov

    def _target_for_cycle(self, index: int) -> str:
        if self._config.targets:
            return self._config.targets[(index - 1) % len(self._config.targets)]
        return ""

    def _objective_for_cycle(self, index: int) -> str:
        target = self._target_for_cycle(index)
        return _targeted_objective(target) if target else self._config.objective

    def _cycle_slots(self, index: int) -> list[tuple[str, BudgetTier]]:
        """The (objective, budget) slots competitors fill this cycle.

        With ``scout`` on, the scout reads the target's source + existing tests and
        returns a ranked shortlist of typed improvements; each becomes a slot whose
        objective is the tiered fixer scaffold and whose budget is set by its kind
        (FEATURE unlocks the big budget). Competitors spread across the slots
        (complementary) and, over runs, collide on hot ones (competitive). Without
        scout — or on a silent/garbled scout — a single bounded slot carries the
        classic targeted/generic objective so a cycle never stalls.
        """
        target = self._target_for_cycle(index)
        fallback = [(self._objective_for_cycle(index), BudgetTier.BOUNDED)]
        if not (self._config.scout and target):
            return fallback
        try:
            source = (self._baseline / target).read_text(encoding="utf-8")
        except OSError:
            return fallback
        try:
            tests = (self._baseline / _guess_test_path(target)).read_text(encoding="utf-8")
        except OSError:
            tests = ""
        from maistro_bootstrap.builders.responses_callable import ResponsesAPICallable
        from maistro_rsi.scout import scout_shortlist

        llm = ResponsesAPICallable(model=self._config.scout_model or self._config.model)
        items = scout_shortlist(source, tests, "", llm, max_items=3)
        if not items:
            return fallback
        logger.info(
            "rsi_local_scout",
            index=index,
            target=target,
            items=[{"kind": it.kind.value, "instruction": it.instruction[:120]} for it in items],
        )
        return [(_fixer_objective(target, it.kind, it.instruction), it.kind.budget) for it in items]

    def _competitors(self) -> list[Competitor]:
        # Empty roster ⇒ a single attempt with the configured model (classic cycle).
        return self._config.competitors or [Competitor(model=self._config.model or "")]

    def _apply_for_competitor(
        self, competitor: Competitor, objective: str, budget: BudgetTier = BudgetTier.BOUNDED
    ) -> ApplyPatchFn:
        # An injected callable (tests) wins; otherwise build a builders provider
        # carrying this competitor's model + temperature and the slot's objective.
        # A FEATURE (v2.0) slot unlocks a larger turn budget for ambitious work.
        if self._injected_apply is not None:
            return self._injected_apply
        turns = self._config.agent_turns_per_cycle
        if budget is BudgetTier.UNLOCKED:
            turns = max(turns, self._config.feature_agent_turns)
        return make_builders_apply_patch(
            objective,
            model=competitor.model or self._config.model,
            temperature=competitor.temperature,
            reasoning_effort=competitor.reasoning_effort,
            system_prompt=competitor.prompt,
            max_agent_turns=turns,
            isolation=self._config.isolation,
            image=self._config.sandbox_image,
        )

    def _changed_files(self, cwd: Path) -> list[str]:
        status = _git(cwd, "status", "--porcelain")
        return [ln[3:].strip() for ln in status.stdout.splitlines() if ln.strip()]

    def _setup_baseline(self) -> None:
        work_root = Path(self._config.work_root)
        work_root.mkdir(parents=True, exist_ok=True)
        if self._baseline.exists():
            raise RuntimeError(f"work root already has a baseline: {self._baseline}")
        # Local clone — never touches the source repo's branches or working tree.
        _git(work_root, "clone", "--quiet", str(Path(self._config.repo_path).resolve()), "baseline")
        _git(self._baseline, "checkout", "-q", "-B", self._config.baseline_branch)
        # Remember where the baseline started so we can export exactly the
        # promotion commits (start_ref..baseline), not the repo's whole history.
        self._start_ref = _git(self._baseline, "rev-parse", "HEAD").stdout.strip()
        logger.info(
            "rsi_local_baseline_ready",
            baseline=str(self._baseline),
            branch=self._config.baseline_branch,
        )

    def _run_variant(
        self,
        index: int,
        seq: int,
        competitor: Competitor,
        objective: str,
        budget: BudgetTier = BudgetTier.BOUNDED,
    ) -> _VariantResult:
        """Run one competitor in its own worktree off the baseline and score it.

        Leaves the committed worktree/branch in place for the cycle to merge and
        clean up. Never raises — an agent/LLM error becomes a non-accepted result
        so one bad competitor can't sink the whole cycle.
        """
        branch = f"rsi/cycle-{index}-v{seq}-{uuid.uuid4().hex[:6]}"
        cdir = Path(self._config.work_root) / f"cycle-{index}-v{seq}"
        _git(
            self._baseline,
            "worktree",
            "add",
            "-q",
            "-b",
            branch,
            str(cdir),
            self._config.baseline_branch,
        )
        r = _VariantResult(branch=branch, cycle_dir=cdir, label=competitor.label)
        try:
            apply_fn = self._apply_for_competitor(competitor, objective, budget)
            asyncio.run(apply_fn(LocalSandbox(cdir), str(cdir), None))
            _git(cdir, "add", "-A")
            r.changed_files = self._changed_files(cdir)
            if not r.changed_files:
                r.note = "no change"
                return r
            r.changed = True
            r.files_touched = len(r.changed_files)
            _git(
                cdir,
                "commit",
                "-q",
                "-m",
                f"RSI cycle {index} [{competitor.label}]: {objective[:50]}",
            )
            if self._config.use_fitness:
                r.accepted, r.composite, r.note, r.tests_passed = self._fitness_decision(
                    index, cdir, r.changed_files
                )
            else:
                r.tests_passed = self._run_tests(cdir)
                r.accepted = r.tests_passed
                r.note = "" if r.tests_passed else "test command failed"
        except Exception as exc:
            r.note = f"variant errored: {exc}"
        logger.info(
            "rsi_local_variant",
            index=index,
            competitor=competitor.label,
            accepted=r.accepted,
            composite=r.composite,
            changed=r.changed,
        )
        return r

    def _apply_to_merge(self, merge_dir: Path, variant: _VariantResult) -> bool:
        patch = _git(
            self._baseline, "diff", f"{self._config.baseline_branch}..{variant.branch}"
        ).stdout
        applied = bool(patch.strip()) and _git_apply(merge_dir, patch)
        logger.info(
            "rsi_local_merge_apply",
            variant=variant.label,
            applied=applied,
            patch_lines=len(patch.splitlines()),
        )
        return applied

    def _run_cycle(self, index: int) -> CycleOutcome:
        target = self._target_for_cycle(index)
        slots = self._cycle_slots(index)
        competitors = self._competitors()
        variants: list[_VariantResult] = []
        created: list[tuple[str, Path]] = []
        try:
            for seq, comp in enumerate(competitors, 1):
                # Spread competitors across the scout's shortlist slots; with more
                # competitors than slots they double up (competitive on one item).
                objective, budget = slots[(seq - 1) % len(slots)]
                r = self._run_variant(index, seq, comp, objective, budget)
                variants.append(r)
                created.append((r.branch, r.cycle_dir))

            accepted = sorted(
                (r for r in variants if r.accepted), key=lambda r: r.composite, reverse=True
            )
            if not accepted:
                changed_any = any(r.changed for r in variants)
                note = next(
                    (r.note for r in variants if r.changed and r.note),
                    "agent made no change" if not changed_any else "rejected by fitness",
                )
                return CycleOutcome(
                    index,
                    changed=changed_any,
                    tests_passed=any(r.tests_passed for r in variants),
                    promoted=False,
                    files_touched=(variants[0].files_touched if variants else 0),
                    target=target,
                    note=note,
                )

            promote_branch, composite, files, kept_n = self._select_and_merge(
                index, target, accepted, created
            )
            _git(self._baseline, "merge", "--ff-only", promote_branch)
            self._baseline_cov = None  # baseline advanced — recompute coverage next cycle
            note = (
                f"tournament: {len(competitors)} competitor(s), {len(accepted)} passed, "
                f"kept {kept_n} (composite={composite})"
            )
            logger.info(
                "rsi_local_cycle_promoted",
                index=index,
                target=target,
                competitors=len(competitors),
                passed=len(accepted),
                kept=kept_n,
                composite=composite,
            )
            return CycleOutcome(
                index,
                changed=True,
                tests_passed=True,
                promoted=True,
                files_touched=files,
                target=target,
                composite=composite,
                note=note,
            )
        finally:
            for branch, worktree_dir in created:
                _git(
                    self._baseline, "worktree", "remove", "--force", str(worktree_dir), check=False
                )
                _git(self._baseline, "branch", "-D", branch, check=False)

    def _select_and_merge(
        self,
        index: int,
        target: str,
        accepted: list[_VariantResult],
        created: list[tuple[str, Path]],
    ) -> tuple[str, float, int, int]:
        """Combine passing candidates (highest-composite first). Returns
        ``(promote_branch, composite, files_touched, kept_count)``.

        One winner promotes its branch directly (identical to the classic cycle).
        A 2+ combination keeps only non-conflicting diffs (complementary), is
        re-scored, and falls back to the single top candidate if it regresses.
        """
        if len(accepted) == 1:
            top = accepted[0]
            return top.branch, top.composite, top.files_touched, 1

        merge_branch = f"rsi/cycle-{index}-m-{uuid.uuid4().hex[:6]}"
        merge_dir = Path(self._config.work_root) / f"cycle-{index}-m"
        _git(
            self._baseline,
            "worktree",
            "add",
            "-q",
            "-b",
            merge_branch,
            str(merge_dir),
            self._config.baseline_branch,
        )
        created.append((merge_branch, merge_dir))
        kept = greedy_merge(accepted, lambda r: self._apply_to_merge(merge_dir, r))
        if len(kept) <= 1:
            # 1 kept: every candidate collided into one region — the top-scored
            # one won. 0 kept: nothing applied cleanly onto the merge worktree —
            # fall back to the top candidate, which is committed and validated.
            top = kept[0] if kept else accepted[0]
            return top.branch, top.composite, top.files_touched, 1
        changed_files = self._changed_files(merge_dir)
        _git(merge_dir, "add", "-A")
        _git(
            merge_dir,
            "commit",
            "-q",
            "-m",
            f"RSI cycle {index}: merged {len(kept)} complementary fix(es) of {target}",
        )
        if self._config.use_fitness:
            m_ok, m_comp, reason, _tp = self._fitness_decision(index, merge_dir, changed_files)
            if not m_ok:
                logger.info("rsi_local_merge_regressed", index=index, reason=reason)
                return kept[0].branch, kept[0].composite, kept[0].files_touched, 1
            return merge_branch, m_comp, len(changed_files), len(kept)
        # No fitness: each kept candidate passed its own tests in isolation, but
        # the COMBINATION was never tested — two non-conflicting patches can still
        # interact and break the suite. Retest the merged worktree; fall back to
        # the top candidate (known-good on its own) if the combination regresses.
        if self._run_tests(merge_dir):
            return merge_branch, kept[0].composite, len(changed_files), len(kept)
        logger.info("rsi_local_merge_untested_regressed", index=index)
        return kept[0].branch, kept[0].composite, kept[0].files_touched, 1

    def _fitness_decision(
        self, index: int, cycle_dir: Path, changed_files: list[str]
    ) -> tuple[bool, float, str, bool]:
        """Build the multi-signal Scorecard for the candidate and return
        (accepted, composite, reject_reason, tests_passed). Logs explain()."""
        from maistro_rsi.candidate_fitness import evaluate_candidate

        scorecard = evaluate_candidate(
            cycle_dir,
            changed_files,
            test_command=self._config.test_command,
            coverage_source=self._config.coverage_source,
            coverage_pytest_args=self._config.coverage_pytest_args,
            baseline_coverage=self._baseline_coverage(),
            baseline_ref=self._config.baseline_branch,
            timeout=self._config.test_timeout,
        )
        logger.info(
            "rsi_local_scorecard",
            index=index,
            accepted=scorecard.accepted,
            composite=scorecard.composite,
            explain="\n" + scorecard.explain(),
        )
        tests_passed = next((g.passed for g in scorecard.gates if g.name == "tests_pass"), False)
        reason = next((f"{g.name}: {g.reason}" for g in scorecard.gates if not g.passed), "")
        return scorecard.accepted, scorecard.composite, reason, tests_passed

    def _run_tests(self, cycle_dir: Path) -> bool:
        # shell=True: the test command is operator-supplied config, not agent input.
        proc = subprocess.run(  # nosemgrep
            self._config.test_command,
            shell=True,  # nosemgrep
            cwd=str(cycle_dir),
            capture_output=True,
            text=True,
            timeout=self._config.test_timeout,
        )
        if proc.returncode != 0:
            logger.info("rsi_local_tests_failed", tail=(proc.stdout + proc.stderr)[-500:])
        return proc.returncode == 0

    def run(self) -> LocalRsiResult:
        self._setup_baseline()
        result = LocalRsiResult(baseline_dir=str(self._baseline))
        for index in range(1, self._config.max_cycles + 1):
            logger.info("rsi_local_cycle_start", index=index, of=self._config.max_cycles)
            try:
                outcome = self._run_cycle(index)
            except Exception as exc:  # one bad cycle shouldn't kill the run
                logger.warning("rsi_local_cycle_error", index=index, error=str(exc))
                outcome = CycleOutcome(
                    index, changed=False, tests_passed=False, promoted=False, note=f"error: {exc}"
                )
            result.cycles.append(outcome)
            # Interim checkpoint every N cycles: a progress report + a refreshed
            # export of everything promoted so far. The baseline is not touched —
            # the loop keeps ratcheting from here.
            if (
                self._config.report_dir
                and self._config.report_every
                and index % self._config.report_every == 0
                and index != self._config.max_cycles
            ):
                self._write_checkpoint(result, label=f"cycle {index}")
        logger.info(
            "rsi_local_loop_complete", promotions=result.promotions, cycles=len(result.cycles)
        )
        # A final report always closes out a reported run (captures the last,
        # possibly-partial window).
        if self._config.report_dir:
            self._write_checkpoint(result, label="final")
        if self._config.export_patches and result.promotions:
            n = self.export_promotions(Path(self._config.export_patches))
            logger.info("rsi_local_exported", patches=n, dest=self._config.export_patches)
        return result

    def _write_checkpoint(self, result: LocalRsiResult, *, label: str) -> None:
        """Write a progress report (markdown + JSON) and refresh the rolling,
        complete patch export under ``report_dir``.

        Never raises: a checkpoint is observability for a long run, so a reporting
        hiccup must never abort the loop that is producing real promotions.
        """
        try:
            report_dir = Path(self._config.report_dir or ".")
            report_dir.mkdir(parents=True, exist_ok=True)
            md, data = build_checkpoint_report(
                result.cycles,
                total_planned=self._config.max_cycles,
                baseline_dir=str(self._baseline),
                window=self._config.report_every or len(result.cycles),
                label=label,
            )
            slug = label.replace(" ", "-")
            (report_dir / f"checkpoint-{slug}.md").write_text(md, encoding="utf-8")
            (report_dir / f"checkpoint-{slug}.json").write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
            # Refresh a rolling, COMPLETE export of everything promoted so far, so
            # an interrupted long run stays harvestable from its last checkpoint.
            # Always clear+rewrite — even at zero promotions — so a reused report
            # dir can't leave stale patches/manifest that `harvest` would apply.
            self.export_promotions(report_dir / "export", clear=True)
            logger.info(
                "rsi_local_checkpoint",
                label=label,
                cycles=len(result.cycles),
                promotions=result.promotions,
                dir=str(report_dir),
            )
        except Exception as exc:
            logger.warning("rsi_local_checkpoint_error", label=label, error=str(exc))

    def export_promotions(self, dest: Path, *, clear: bool = False) -> int:
        """Export each promotion commit (start_ref..baseline) as a git-am-able
        patch plus a manifest.json mapping patch -> edited file, for the harvester
        to open PRs grouped by file. Returns the number of patches written.

        ``clear`` first removes any stale ``*.patch``/manifest from a prior write,
        so a rolling checkpoint export always reflects exactly the current set.
        """
        dest.mkdir(parents=True, exist_ok=True)
        if clear:
            for stale in dest.glob("*.patch"):
                stale.unlink()
            (dest / "manifest.json").unlink(missing_ok=True)
        rng = f"{self._start_ref}..{self._config.baseline_branch}"
        revs = _git(self._baseline, "rev-list", "--reverse", rng).stdout.split()
        manifest: list[dict[str, str]] = []
        for i, sha in enumerate(revs, 1):
            names = [
                ln.strip()
                for ln in _git(
                    self._baseline, "show", "--name-only", "--pretty=format:", sha
                ).stdout.splitlines()
                if ln.strip()
            ]
            subject = _git(self._baseline, "show", "-s", "--pretty=format:%s", sha).stdout.strip()
            patch_name = f"{i:04d}-{sha[:8]}.patch"
            patch = _git(self._baseline, "format-patch", "-1", "--stdout", sha).stdout
            (dest / patch_name).write_text(patch, encoding="utf-8")
            src = next((n for n in names if n.endswith(".py")), names[0] if names else "")
            manifest.append({"patch_file": patch_name, "file": src, "subject": subject})
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return len(manifest)
