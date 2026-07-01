"""Test coverage as a fitness signal — a *substantial* gate plus a graded score.

Unlike the static code-quality metrics (which score a file in isolation),
coverage is a project-level, run-based measure: it needs the test suite executed
under instrumentation, and the meaningful quantity is the *delta* vs. the
baseline. A self-modification that quietly deletes tests or adds untested code
should be **rejected outright** — so coverage-not-dropping is a hard gate (the
most substantial form a signal can take), and the absolute coverage is also
offered as a graded score for ranking among candidates that pass.

Coverage measures real correctness *assurance*, not a proxy — which is why it
earns a veto where the shallow metrics (docstrings, style) only earn weight.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

from maistro_evolve.scorecard import GateResult, MeasureKind, SignalScore


def measure_coverage(
    repo_dir: str | Path,
    *,
    source: str = ".",
    pytest_args: str = "",
    timeout: int = 900,
) -> float | None:
    """Run the suite under coverage in ``repo_dir``; return total % covered (0..100).

    Returns None if coverage can't be produced (tool missing, no data) so the
    caller can treat coverage as unavailable rather than as 0% — which would
    falsely fail the gate.
    """
    cwd = str(repo_dir)
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                f"--source={source}",
                "-m",
                "pytest",
                *shlex.split(pytest_args),
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        # Even if some tests fail, coverage data may still exist — read it anyway.
        report = subprocess.run(
            [sys.executable, "-m", "coverage", "json", "-o", "-"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if report.returncode != 0 or not report.stdout.strip():
        return None
    try:
        return float(json.loads(report.stdout)["totals"]["percent_covered"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def coverage_gate(
    baseline_pct: float | None, candidate_pct: float | None, *, tolerance: float = 0.5
) -> GateResult:
    """Hard veto: the candidate must not drop coverage below baseline (minus a
    small tolerance for run-to-run noise). Unavailable coverage is not enforced."""
    if baseline_pct is None or candidate_pct is None:
        return GateResult("coverage_not_dropped", True, "coverage unavailable — gate not enforced")
    dropped = candidate_pct < baseline_pct - tolerance
    delta = candidate_pct - baseline_pct
    sign = "+" if delta >= 0 else ""
    return GateResult(
        "coverage_not_dropped",
        passed=not dropped,
        reason=f"{candidate_pct:.1f}% vs baseline {baseline_pct:.1f}% ({sign}{delta:.1f}, tol {tolerance})",
    )


def coverage_signal(
    baseline_pct: float | None, candidate_pct: float | None, weight: float
) -> SignalScore:
    """Absolute coverage as a graded score (0..1), with the delta in the rationale."""
    cand = candidate_pct or 0.0
    base = baseline_pct if baseline_pct is not None else cand
    delta = cand - base
    sign = "+" if delta >= 0 else ""
    return SignalScore(
        name="coverage",
        kind=MeasureKind.DERIVED,
        score=max(0.0, min(1.0, cand / 100.0)),
        weight=weight,
        rationale=f"line coverage {cand:.1f}% (baseline {base:.1f}%, {sign}{delta:.1f})",
        detail={"baseline": base, "candidate": cand, "delta": delta},
    )
