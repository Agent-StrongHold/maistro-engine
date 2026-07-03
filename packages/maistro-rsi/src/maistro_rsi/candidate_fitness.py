"""Compose the fitness signals into one promotion decision for the RSI loop.

Gathers the *local* signals for a baseline→candidate pair (tests, coverage,
code-quality, assertion-strength, lint/type/security gates) and builds the
transparent `Scorecard`: gates first (any veto ⇒ reject), then priority-weighted
scores (`FitnessWeights`). Capability (benchmarks) and architecture-fit (LLM
judge) are *injected* when a gateway is available, so this module stays
runnable offline. `compose_scorecard()` is pure and takes already-gathered
`FitnessInputs`; `evaluate_candidate()` runs the tools to produce them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from maistro_evolve.assertion_strength import score_assertions
from maistro_evolve.code_quality import score_path
from maistro_evolve.coverage_gate import coverage_gate, coverage_signal, measure_coverage
from maistro_evolve.doc_regression import doc_regressions
from maistro_evolve.scorecard import (
    FitnessWeights,
    GateResult,
    MeasureKind,
    Scorecard,
    SignalScore,
    architecture_fit_signal,
    capability_signal,
    judge_signal,
    perf_signal,
)
from maistro_evolve.tdd_gate import (
    TddEvidence,
    changed_test_paths,
    count_net_new_tests,
    new_test_signal,
    red_green_signal,
    run_test_selection,
)

_TEST_HINTS = ("test_", "_test.py", "/tests/", "conftest.py")


def _is_test(path: str) -> bool:
    return any(h in path.replace("\\", "/") for h in _TEST_HINTS)


@dataclass
class FitnessInputs:
    tests_passed: bool
    test_reason: str = ""
    baseline_coverage: float | None = None
    candidate_coverage: float | None = None
    code_quality_composite: float | None = None
    code_quality_detail: str = ""
    assertion_score: float | None = None
    assertion_detail: str = ""
    tdd: TddEvidence = field(default_factory=TddEvidence)
    lint_gates: list[GateResult] = field(default_factory=list)
    capability: tuple[float, float] | None = None
    architecture_fit: object | None = None
    # Net-new ``test_*`` functions added by the candidate (drives the presence-
    # gated ``new_test`` signal together with the coverage delta).
    net_new_tests: int = 0
    # Symbols whose docstring lost material specificity — any entry vetoes.
    doc_regression_reasons: list[str] = field(default_factory=list)
    # LLM impact judge for a FEATURE/v2.0 change: (score 0..1, rationale). Injected
    # only when a judge gateway is available; absent otherwise.
    feature_judge: tuple[float, str] | None = None
    # Wall-clock timing for a PERF change: (baseline_seconds, candidate_seconds).
    perf: tuple[float, float] | None = None


def compose_scorecard(inp: FitnessInputs, weights: FitnessWeights | None = None) -> Scorecard:
    """Pure: assemble gates + priority-weighted scores into a Scorecard."""
    w = weights or FitnessWeights()
    gates = [
        GateResult(
            "tests_pass",
            inp.tests_passed,
            inp.test_reason or ("ok" if inp.tests_passed else "failed"),
        ),
        coverage_gate(inp.baseline_coverage, inp.candidate_coverage),
        GateResult(
            "no_doc_regression",
            not inp.doc_regression_reasons,
            "; ".join(inp.doc_regression_reasons) or "no docstring made vaguer",
        ),
        *inp.lint_gates,
    ]
    scores: list[SignalScore] = [red_green_signal(inp.tdd, w.red_green)]
    cov_delta = (
        inp.candidate_coverage - inp.baseline_coverage
        if inp.candidate_coverage is not None and inp.baseline_coverage is not None
        else None
    )
    nt = new_test_signal(inp.net_new_tests, cov_delta, w.new_test)
    if nt is not None:
        scores.append(nt)
    if inp.feature_judge is not None:
        scores.append(
            judge_signal(
                "feature_judge", inp.feature_judge[0], w.feature_judge, inp.feature_judge[1]
            )
        )
    if inp.perf is not None:
        scores.append(perf_signal(inp.perf[0], inp.perf[1], w.perf))
    if inp.capability is not None:
        scores.append(capability_signal(inp.capability[0], inp.capability[1], w.capability))
    if inp.assertion_score is not None:
        scores.append(
            SignalScore(
                "assertion_strength",
                MeasureKind.CALCULATED,
                inp.assertion_score,
                w.assertion_strength,
                inp.assertion_detail or "changed-test assertion strength",
            )
        )
    if inp.candidate_coverage is not None:
        scores.append(coverage_signal(inp.baseline_coverage, inp.candidate_coverage, w.coverage))
    if inp.architecture_fit is not None:
        scores.append(architecture_fit_signal(inp.architecture_fit, w.architecture_fit))
    if inp.code_quality_composite is not None:
        scores.append(
            SignalScore(
                "code_quality",
                MeasureKind.DERIVED,
                inp.code_quality_composite,
                w.code_quality,
                inp.code_quality_detail or "changed-source quality composite",
            )
        )
    return Scorecard(gates=gates, scores=scores)


def _run(cmd: str, cwd: Path, timeout: int = 900) -> tuple[bool, str]:
    try:
        # shell=True: `cmd` is operator-supplied test config, not agent/attacker input.
        proc = subprocess.run(  # nosemgrep
            cmd,
            shell=True,  # nosemgrep
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"test command errored: {exc}"
    tail = (proc.stdout + proc.stderr).strip()[-200:]
    return (
        proc.returncode == 0,
        f"exit {proc.returncode}: {tail}" if tail else f"exit {proc.returncode}",
    )


_LINT_TIMEOUT = 120


def _run_lint_tool(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    """Run a static tool, bounded by a timeout. Returns None if the tool is
    missing or wedges — so the gate is treated as unavailable (not a false
    rejection, and never an indefinite hang of LocalRsiLoop.run())."""
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), capture_output=True, text=True, timeout=_LINT_TIMEOUT
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if "No module named" in proc.stderr:
        return None
    return proc


def _lint_gates(cwd: Path, src_files: list[str]) -> list[GateResult]:
    """ruff / mypy / bandit-HIGH on the changed source files. A missing, errored,
    or timed-out tool yields no gate (unenforced) rather than a false rejection."""
    if not src_files:
        return []
    gates: list[GateResult] = []

    ruff = _run_lint_tool(
        [sys.executable, "-m", "ruff", "check", "--output-format", "json", *src_files], cwd
    )
    if ruff is not None:
        try:
            n = len(json.loads(ruff.stdout or "[]"))
        except json.JSONDecodeError:
            n = 0
        gates.append(GateResult("ruff_clean", n == 0, f"{n} lint violation(s)"))

    mypy = _run_lint_tool(
        [
            sys.executable,
            "-m",
            "mypy",
            "--ignore-missing-imports",
            "--no-error-summary",
            "--no-color-output",
            "--config-file",
            os.devnull,
            *src_files,
        ],
        cwd,
    )
    if mypy is not None:
        errs = sum(1 for ln in mypy.stdout.splitlines() if ": error:" in ln)
        gates.append(GateResult("mypy_clean", errs == 0, f"{errs} type error(s)"))

    bandit = _run_lint_tool([sys.executable, "-m", "bandit", "-f", "json", "-q", *src_files], cwd)
    if bandit is not None:
        try:
            results = json.loads(bandit.stdout or "{}").get("results", [])
        except json.JSONDecodeError:
            results = []
        high = [r for r in results if r.get("issue_severity") == "HIGH"]
        gates.append(
            GateResult("no_bandit_high", len(high) == 0, f"{len(high)} HIGH-severity finding(s)")
        )
    return gates


def _mean_quality(cwd: Path, src_files: list[str]) -> tuple[float | None, str]:
    composites = []
    for f in src_files:
        if (cwd / f).is_file():
            composites.append(score_path(cwd / f).composite)
    if not composites:
        return None, ""
    mean = sum(composites) / len(composites)
    return round(mean, 4), f"mean code-quality over {len(composites)} changed source file(s)"


def _doc_regressions(cwd: Path, baseline_ref: str, src_files: list[str]) -> list[str]:
    """Per changed source file, compare its docstrings against ``baseline_ref`` and
    collect any that lost material specificity (see ``doc_regression``). A file
    absent on baseline (all-new) has no baseline docstrings, so never regresses."""
    reasons: list[str] = []
    for rel in src_files:
        try:
            candidate = (cwd / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        base = subprocess.run(
            ["git", "show", f"{baseline_ref}:{rel}"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )
        if base.returncode != 0:
            continue
        reasons += [f"{rel}::{r}" for r in doc_regressions(base.stdout, candidate)]
    return reasons


def _mean_assertion(cwd: Path, test_files: list[str]) -> tuple[float | None, str]:
    scores = []
    for f in test_files:
        if (cwd / f).is_file():
            s = score_assertions(cwd / f).score
            if s is not None:
                scores.append(s)
    if not scores:
        return None, ""
    mean = sum(scores) / len(scores)
    return round(mean, 4), f"mean assertion strength over {len(scores)} changed test file(s)"


def _red_green_evidence(
    cwd: Path, baseline_ref: str, src: list[str], tests: list[str], timeout: int
) -> TddEvidence:
    """Fill TddEvidence by running the candidate's changed tests against the
    baseline source: revert the changed source files to ``baseline_ref`` in the
    worktree (keeping the candidate's tests), run those tests (expect RED), then
    restore the candidate source. Green-on-candidate is the plain run.
    """
    if not tests:
        return TddEvidence()
    cand_rc, _ = run_test_selection(cwd, tests, timeout=timeout)
    base_rc: int | None = None
    if src:
        try:
            subprocess.run(
                ["git", "checkout", baseline_ref, "--", *src],
                cwd=str(cwd),
                check=True,
                capture_output=True,
                text=True,
            )
            base_rc, _ = run_test_selection(cwd, tests, timeout=timeout)
        except (OSError, subprocess.CalledProcessError):
            base_rc = None
        finally:
            subprocess.run(
                ["git", "checkout", "HEAD", "--", *src],
                cwd=str(cwd),
                capture_output=True,
                text=True,
            )
    return TddEvidence(
        changed_tests=tests, baseline_changed_rc=base_rc, candidate_changed_rc=cand_rc
    )


def evaluate_candidate(
    candidate_dir: str | Path,
    changed_files: list[str],
    *,
    test_command: str,
    coverage_source: str = ".",
    coverage_pytest_args: str = "",
    baseline_coverage: float | None = None,
    baseline_ref: str | None = None,
    weights: FitnessWeights | None = None,
    tdd: TddEvidence | None = None,
    capability: tuple[float, float] | None = None,
    architecture_fit: object | None = None,
    feature_judge: tuple[float, str] | None = None,
    perf: tuple[float, float] | None = None,
    timeout: int = 900,
) -> Scorecard:
    """Run the local signals for a candidate and compose the Scorecard.

    ``feature_judge`` (score, rationale) and ``perf`` (baseline_s, candidate_s) are
    injected by callers that have a judge gateway / timing harness; without them
    those signals are simply absent (composite renormalises over present signals).
    """
    cwd = Path(candidate_dir)
    src = [f for f in changed_files if f.endswith(".py") and not _is_test(f)]
    tests = changed_test_paths(changed_files)

    tests_passed, test_reason = _run(test_command, cwd, timeout)
    cand_cov = measure_coverage(cwd, source=coverage_source, pytest_args=coverage_pytest_args)
    cq, cq_detail = _mean_quality(cwd, src)
    astr, astr_detail = _mean_assertion(cwd, tests)
    if tdd is None:
        tdd = (
            _red_green_evidence(cwd, baseline_ref, src, tests, timeout)
            if baseline_ref
            else TddEvidence(changed_tests=tests)
        )
    net_new = count_net_new_tests(cwd, baseline_ref, tests) if (baseline_ref and tests) else 0
    doc_reasons = _doc_regressions(cwd, baseline_ref, src) if baseline_ref else []

    inputs = FitnessInputs(
        tests_passed=tests_passed,
        test_reason=test_reason,
        baseline_coverage=baseline_coverage,
        candidate_coverage=cand_cov,
        code_quality_composite=cq,
        code_quality_detail=cq_detail,
        assertion_score=astr,
        assertion_detail=astr_detail,
        tdd=tdd,
        lint_gates=_lint_gates(cwd, src),
        capability=capability,
        architecture_fit=architecture_fit,
        net_new_tests=net_new,
        doc_regression_reasons=doc_reasons,
        feature_judge=feature_judge,
        perf=perf,
    )
    return compose_scorecard(inputs, weights)
