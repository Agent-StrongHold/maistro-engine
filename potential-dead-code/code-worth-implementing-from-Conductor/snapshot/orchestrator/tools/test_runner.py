"""Test runner — executes project-configured test commands.

Assumptions:
- Exit code 0 means tests passed (standard Unix convention)
- Exit code != 0 means tests failed
- This works with pytest, jest, go test, cargo test, and most test frameworks

To customize pass/fail detection for non-standard test runners,
subclass TestRunner and override _interpret_result().
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from orchestrator.tools.shell import Shell, ShellResult

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    passed: bool
    summary: str
    raw: ShellResult
    tests_run: int = 0  # Parsed from output if possible
    tests_failed: int = 0


class TestRunner:
    """Run the project's configured test command.

    Exit code interpretation (configurable via success_codes):
        - 0: All tests passed
        - Non-zero: At least one test failed (or test framework error)

    Some test frameworks have special exit codes:
        - pytest: 0=pass, 1=fail, 2=interrupted, 3=internal, 4=usage, 5=no tests
        - jest: 0=pass, 1=fail
        - go test: 0=pass, 1=fail, 2=test not found
    """

    def __init__(
        self,
        shell: Shell,
        test_command: str,
        success_codes: set[int] | None = None,
    ) -> None:
        self._shell = shell
        self._command = test_command
        # Allow customizing what exit codes mean "success"
        # Default: only 0 is success
        self._success_codes = success_codes or {0}

    async def run(self) -> TestResult:
        """Execute the test command and interpret the result."""
        result = await self._shell.run(self._command)
        return self._interpret_result(result)

    def _interpret_result(self, result: ShellResult) -> TestResult:
        """Interpret shell result as test outcome. Override for custom logic."""
        passed = result.returncode in self._success_codes

        # Try to parse test counts from output (works for pytest, jest, etc.)
        tests_run, tests_failed = self._parse_test_counts(result.stdout + result.stderr)

        # Build a concise summary
        if passed:
            summary = f"Tests passed (exit {result.returncode})"
            if tests_run > 0:
                summary = f"Tests passed: {tests_run} tests run"
        elif result.timed_out:
            summary = "Tests timed out"
        else:
            # Take last 20 lines of combined output as summary
            lines = (result.stdout + "\n" + result.stderr).strip().split("\n")
            tail = "\n".join(lines[-20:])
            summary = f"Tests failed (exit {result.returncode}):\n{tail}"

        logger.info("Test result: %s", "PASS" if passed else "FAIL")
        return TestResult(
            passed=passed,
            summary=summary,
            raw=result,
            tests_run=tests_run,
            tests_failed=tests_failed,
        )

    @staticmethod
    def _parse_test_counts(output: str) -> tuple[int, int]:
        """Try to extract test counts from common test framework output.

        Returns (tests_run, tests_failed) or (0, 0) if unparseable.
        """
        # pytest: "5 passed, 2 failed"
        pytest_match = re.search(r"(\d+) passed", output)
        pytest_failed = re.search(r"(\d+) failed", output)
        if pytest_match:
            passed = int(pytest_match.group(1))
            failed = int(pytest_failed.group(1)) if pytest_failed else 0
            return (passed + failed, failed)

        # jest: "Tests: 2 passed, 1 failed, 3 total"
        jest_match = re.search(r"Tests:\s+(?:\d+ \w+,\s+)*(\d+) total", output)
        jest_failed = re.search(r"(\d+) failed", output)
        if jest_match:
            total = int(jest_match.group(1))
            failed = int(jest_failed.group(1)) if jest_failed else 0
            return (total, failed)

        # go test: "ok" or "FAIL"
        go_match = re.search(r"--- (PASS|FAIL):", output)
        if go_match:
            # Count test functions
            passes = len(re.findall(r"--- PASS:", output))
            fails = len(re.findall(r"--- FAIL:", output))
            return (passes + fails, fails)

        return (0, 0)
