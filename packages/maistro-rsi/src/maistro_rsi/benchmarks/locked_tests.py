"""Locked test suite benchmark.

Runs a frozen test directory that RSI is forbidden from modifying (enforced by
campaign protected_paths). Outputs a final JSON line the campaign store can
parse: {"fidelity": "real", "score": float, "passed": int, "failed": int}.

Score is pass_rate = passed / (passed + failed). Zero when no tests ran.

Usage (as benchmark_command in a campaign):
    python -m maistro_rsi.benchmarks.locked_tests packages/maistro-core/tests
    python -m maistro_rsi.benchmarks.locked_tests packages/maistro-core/tests -x --tb=short
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

_PASS_RE = re.compile(r"(\d+) passed")
_FAIL_RE = re.compile(r"(\d+) failed")
_ERROR_RE = re.compile(r"(\d+) error")


def _parse_counts(output: str) -> tuple[int, int]:
    passed = int(m.group(1)) if (m := _PASS_RE.search(output)) else 0
    failed = int(m.group(1)) if (m := _FAIL_RE.search(output)) else 0
    failed += int(m.group(1)) if (m := _ERROR_RE.search(output)) else 0
    return passed, failed


def run(test_path: str, extra_args: list[str]) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-q", "--tb=no", "--no-header"]
        + extra_args,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    passed, failed = _parse_counts(output)
    total = passed + failed
    score = round(passed / total, 6) if total > 0 else 0.0

    # Print JSON as the last line so _real_benchmark_score can parse it.
    # Always exits 0: this is a quality-score benchmark, not a pass/fail gate.
    # The campaign's test_command is the hard gate; this measures improvement.
    print(
        json.dumps(
            {
                "fidelity": "real",
                "score": score,
                "passed": passed,
                "failed": failed,
                "total": total,
            }
        )
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python -m maistro_rsi.benchmarks.locked_tests <test_path> [pytest_args...]",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(run(sys.argv[1], sys.argv[2:]))
