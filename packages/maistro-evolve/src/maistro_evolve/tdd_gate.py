"""TDD gate: verify a self-modification was test-driven, not rubber-stamped.

The self-improvement process is expected to be TDD, in one of three shapes:

  1. **test proposed then code** — a new test, red on baseline, green on candidate.
  2. **new code for an existing test** — a pre-existing *failing* test goes green.
  3. **improved test + improved code** — a strengthened test, red on baseline,
     green on candidate.

The unifying, un-gameable check is **red→green**: a candidate's changed tests
must *fail on the baseline code* and *pass on the candidate code*. A changed test
that already passes on baseline tests nothing new (vacuous); a code change with
no test change — and no previously-failing test now fixed — isn't test-driven.
Coverage-not-dropped (see coverage_gate) catches gross test deletion; this gate
catches the subtler "code first, rubber-stamp test" and "vacuous test" cases.

The predicate `tdd_gate()` is pure and takes a `TddEvidence` the loop fills in by
running the changed tests against each code state; `run_test_selection()` is the
subprocess helper that produces that evidence.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from maistro_evolve.scorecard import GateResult

_TEST_HINTS = ("test_", "_test.py", "/tests/", "conftest.py")


def changed_test_paths(changed_paths: list[str]) -> list[str]:
    """Filter a diff's changed paths down to the ones that are tests."""
    return [p for p in changed_paths if any(h in p.replace("\\", "/") for h in _TEST_HINTS)]


@dataclass
class TddEvidence:
    changed_tests: list[str] = field(default_factory=list)
    # Exit code of running the *changed* tests against each code state.
    baseline_changed_rc: int | None = None  # expect non-zero (red) when tests changed
    candidate_changed_rc: int | None = None  # expect zero (green)
    # Whole-suite failing counts, for the "fixed a pre-existing failing test" mode.
    baseline_suite_failures: int = 0
    candidate_suite_failures: int = 0


def tdd_gate(evidence: TddEvidence) -> GateResult:
    """Pass iff the change is genuinely test-driven (one of the three modes)."""
    ev = evidence
    if ev.changed_tests:
        if ev.baseline_changed_rc == 0:
            return GateResult(
                "tdd_red_green",
                False,
                "changed tests already pass on baseline — vacuous, not test-first",
            )
        if ev.candidate_changed_rc != 0:
            return GateResult(
                "tdd_red_green", False, "changed tests do not pass on the candidate"
            )
        return GateResult(
            "tdd_red_green",
            True,
            f"{len(ev.changed_tests)} changed test(s): red on baseline, green on candidate",
        )
    # No test change: only test-driven if it turned a previously-failing test green.
    if ev.candidate_suite_failures < ev.baseline_suite_failures:
        fixed = ev.baseline_suite_failures - ev.candidate_suite_failures
        return GateResult(
            "tdd_red_green", True, f"no new tests, but fixed {fixed} pre-existing failing test(s)"
        )
    return GateResult(
        "tdd_red_green",
        False,
        "code change with no test change and no previously-failing test fixed — not TDD",
    )


def run_test_selection(
    repo_dir: str | Path, selectors: list[str], *, timeout: int = 600
) -> tuple[int, str]:
    """Run pytest on specific files/selectors in ``repo_dir``; return (exit_code, output).

    Used by the loop to build TddEvidence: run the candidate's changed tests
    against a baseline checkout (expect non-zero) and the candidate (expect zero).
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *selectors],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, "test run failed to execute"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
