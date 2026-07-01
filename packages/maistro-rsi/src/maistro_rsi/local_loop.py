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
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from maistro_rsi.protocols import ApplyPatchFn, MicroVmSandbox

logger = structlog.get_logger()

_DEFAULT_OBJECTIVE = (
    "Make exactly one small, safe, self-contained improvement to this codebase. "
    "Good candidates: fix a clear bug, tighten a type, add a missing test, or "
    "improve a confusing name or docstring. Read files before you edit them, "
    "keep the diff minimal, and do not break existing behavior. "
    "Use only the read_file, write_file and search tools — do NOT run git, "
    "commit, or shell commands: the harness stages, commits, and runs the tests "
    "for you after you finish. If you cannot find a safe improvement, make no "
    "changes and stop."
)


def _targeted_objective(path: str) -> str:
    """Build a per-cycle objective that names one explicit file to improve.

    Naming the file removes the discovery step that weak models fail at (they
    can't reliably search for a target), so each cycle is a concrete, bounded
    edit of a known file.
    """
    return (
        f"Improve the file `{path}` in this repository. Make one small, safe, "
        f"self-contained improvement: clarify or add a module- or function-level "
        f"docstring, tighten a type hint, or fix an obvious minor issue. First read "
        f"`{path}` with the read_file tool, then make the change with the edit_file "
        f"tool (a targeted exact-string replacement) — do NOT rewrite the whole file "
        f"with write_file, and do not reformat or touch lines unrelated to your change. "
        f"Keep the edit minimal and do not alter runtime behavior. Use only read_file "
        f"and edit_file — do not run git or shell commands."
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
            proc = subprocess.run(
                command,
                shell=True,
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
        proc = await asyncio.to_thread(_git, self._workspace, "rev-parse", "HEAD")
        return proc.stdout.strip()

    async def restore(self, snapshot_id: str) -> None:
        await asyncio.to_thread(_git, self._workspace, "reset", "--hard", snapshot_id)

    async def destroy(self) -> None:
        # Worktrees are torn down by the loop that created them; nothing to do.
        return None

    async def __aenter__(self) -> LocalSandbox:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.destroy()


# ---------------------------------------------------------------------------
# Native builders provider — the ApplyPatchFn
# ---------------------------------------------------------------------------


def make_builders_apply_patch(
    objective: str = _DEFAULT_OBJECTIVE,
    *,
    model: str | None = None,
    max_agent_turns: int = 6,
) -> ApplyPatchFn:
    """Build an `ApplyPatchFn` that drives the native builders agent loop.

    Returns an async callable ``apply(sandbox, workspace)`` that points the
    builders coding agent (the same `TurnRunner`/`LocalWorktreeSandbox` engine
    behind `maistro builders`) at ``workspace`` and asks it to carry out
    ``objective``. The agent's tool calls (read_file/write_file/run_tests/…)
    operate on the worktree; when it stops requesting tools the turn ends. Up to
    ``max_agent_turns`` turns are run so a single cycle can do multi-step work.

    Model resolution is left to `ResponsesAPICallable` (``model=None`` →
    ``MAISTRO_BUILDERS_MODEL``/``DEFAULT_MODEL`` from the loaded ``.env``), so
    the loop honours the same gateway config as the interactive TUI.
    """

    async def apply(sandbox: MicroVmSandbox, workspace: str) -> None:
        # Imported lazily so the package stays importable without the builders
        # extras installed (mirrors _builders_tui.py's own lazy import).
        from maistro_bootstrap.builders.agent_loop import AgentLoopConfig, TurnRunner
        from maistro_bootstrap.builders.responses_callable import ResponsesAPICallable
        from maistro_bootstrap.builders.sandbox import LocalWorktreeSandbox
        from maistro_bootstrap.builders.session import BuilderSession

        work_path = Path(workspace)
        session = BuilderSession(sandbox=LocalWorktreeSandbox(work_path))
        config = AgentLoopConfig(model=model) if model else AgentLoopConfig()
        runner = TurnRunner(session=session, config=config)
        runner.set_llm(ResponsesAPICallable(model=model))  # type: ignore[arg-type]

        messages: list[dict[str, object]] = [
            {"role": "system", "content": config.system_prompt},
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
    baseline_branch: str = "rsi-baseline"
    test_timeout: int = 900


@dataclass
class CycleOutcome:
    index: int
    changed: bool
    tests_passed: bool
    promoted: bool
    files_touched: int = 0
    target: str = ""
    note: str = ""


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

    def _target_for_cycle(self, index: int) -> str:
        if self._config.targets:
            return self._config.targets[(index - 1) % len(self._config.targets)]
        return ""

    def _objective_for_cycle(self, index: int) -> str:
        target = self._target_for_cycle(index)
        return _targeted_objective(target) if target else self._config.objective

    def _apply_for_cycle(self, index: int) -> ApplyPatchFn:
        # An injected callable (tests) wins; otherwise build a fresh builders
        # provider carrying this cycle's (possibly targeted) objective.
        if self._injected_apply is not None:
            return self._injected_apply
        return make_builders_apply_patch(
            self._objective_for_cycle(index),
            model=self._config.model,
            max_agent_turns=self._config.agent_turns_per_cycle,
        )

    def _setup_baseline(self) -> None:
        work_root = Path(self._config.work_root)
        work_root.mkdir(parents=True, exist_ok=True)
        if self._baseline.exists():
            raise RuntimeError(f"work root already has a baseline: {self._baseline}")
        # Local clone — never touches the source repo's branches or working tree.
        _git(work_root, "clone", "--quiet", str(Path(self._config.repo_path).resolve()), "baseline")
        _git(self._baseline, "checkout", "-q", "-B", self._config.baseline_branch)
        logger.info(
            "rsi_local_baseline_ready",
            baseline=str(self._baseline),
            branch=self._config.baseline_branch,
        )

    def _run_cycle(self, index: int) -> CycleOutcome:
        cycle_branch = f"rsi/cycle-{index}-{uuid.uuid4().hex[:6]}"
        cycle_dir = Path(self._config.work_root) / f"cycle-{index}"
        _git(
            self._baseline,
            "worktree",
            "add",
            "-q",
            "-b",
            cycle_branch,
            str(cycle_dir),
            self._config.baseline_branch,
        )
        target = self._target_for_cycle(index)
        try:
            asyncio.run(self._apply_for_cycle(index)(LocalSandbox(cycle_dir), str(cycle_dir)))

            _git(cycle_dir, "add", "-A")
            status = _git(cycle_dir, "status", "--porcelain")
            changed = bool(status.stdout.strip())
            if not changed:
                return CycleOutcome(
                    index,
                    changed=False,
                    tests_passed=False,
                    promoted=False,
                    target=target,
                    note="agent made no change",
                )

            files_touched = len([ln for ln in status.stdout.splitlines() if ln.strip()])
            commit_subject = f"RSI cycle {index}: {(target or self._config.objective)[:60]}"
            _git(cycle_dir, "commit", "-q", "-m", commit_subject)

            tests_passed = self._run_tests(cycle_dir)
            if not tests_passed:
                return CycleOutcome(
                    index,
                    changed=True,
                    tests_passed=False,
                    promoted=False,
                    files_touched=files_touched,
                    target=target,
                    note="test command failed",
                )

            # Promote: fast-forward the baseline branch to include this cycle.
            _git(self._baseline, "merge", "--ff-only", cycle_branch)
            logger.info("rsi_local_cycle_promoted", index=index, files=files_touched, target=target)
            return CycleOutcome(
                index,
                changed=True,
                tests_passed=True,
                promoted=True,
                files_touched=files_touched,
                target=target,
            )
        finally:
            _git(self._baseline, "worktree", "remove", "--force", str(cycle_dir), check=False)
            _git(self._baseline, "branch", "-D", cycle_branch, check=False)

    def _run_tests(self, cycle_dir: Path) -> bool:
        # shell=True: the test command is operator-supplied config, not agent input.
        proc = subprocess.run(
            self._config.test_command,
            shell=True,
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
        logger.info(
            "rsi_local_loop_complete", promotions=result.promotions, cycles=len(result.cycles)
        )
        return result
