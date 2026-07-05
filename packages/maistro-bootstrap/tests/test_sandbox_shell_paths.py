"""Path-escape hardening for the builders shell guard.

The agent's ``run_command`` tool must not be able to read files outside its
worktree — in particular the RSI scoring evidence the reviewer keeps at
``/run/reports/`` (RLPHD state, flagged patches). A bare absolute token
(``cat /run/reports/x``) was already blocked, but three literal-path forms
slipped through token inspection and are closed here:

* flag-glued long form  — ``--file=/etc/passwd``
* flag-glued short form  — ``grep -f/run/reports/x``
* interpreter string arg — ``python -c "open('/run/reports/x').read()"``

Token inspection fundamentally cannot see a path an interpreter *constructs*
at runtime (``open('/ru'+'n/reports/x')``); the real guarantee for the report
dir is the OS filesystem boundary (non-root agent user + a 0700 report dir),
added in the container-hardening pass. These tests lock in the literal-path
defense-in-depth layer, which stops the realistic cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maistro_bootstrap.builders.errors import SandboxEscapeError
from maistro_bootstrap.builders.sandbox import SandboxedShell


@pytest.fixture()
def shell(tmp_path: Path) -> SandboxedShell:
    return SandboxedShell(tmp_path)


# --- blocked: every literal absolute-path exfil form ------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "cat /run/reports/rlphd_state.json",  # bare absolute (already blocked)
        "cat /etc/passwd",
        "cat ../../../etc/passwd",  # dotdot traversal
        "cat --file=/etc/passwd",  # flag-glued, long form
        "cat --output=/run/reports/x.json",
        "grep -f/run/reports/x .",  # flag-glued, short form
        "python -c print(open('/run/reports/rlphd_state.json').read())",  # interpreter string
        "python -c open('/etc/passwd')",
    ],
)
def test_absolute_path_exfil_is_blocked(shell: SandboxedShell, cmd: str) -> None:
    with pytest.raises(SandboxEscapeError):
        shell.run(cmd)


def test_embedded_proc_environ_is_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(SandboxEscapeError):
        shell.run("python -c open('/proc/1/environ')")


# --- allowed: legitimate in-workspace usage must still run ------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "python -m pytest tests/",
        "grep pat src/f.py",
        "pytest -x --maxfail=1 tests/unit",
        "cat report.json",
        "git diff",
        "ls src/maistro",
    ],
)
def test_legitimate_relative_commands_are_allowed(
    shell: SandboxedShell, cmd: str, tmp_path: Path
) -> None:
    # Exercise the guard directly; the command need not succeed at the OS level,
    # only pass the path check without raising SandboxEscapeError.
    import shlex

    shell._check_paths(shlex.split(cmd))  # must not raise


def test_absolute_path_inside_workspace_is_allowed(shell: SandboxedShell, tmp_path: Path) -> None:
    # An absolute path that genuinely resolves *inside* the root is fine.
    inside = str(tmp_path / "src" / "f.py")
    shell._check_paths(["cat", inside])  # must not raise
