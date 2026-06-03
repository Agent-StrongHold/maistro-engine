"""Tests for SandboxedShell — SPEC-200 safety invariants."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from maistro.builders.errors import (
    BlockedCommandError,
    CommandTimeoutError,
    OutputTruncatedWarning,
    SandboxEscapeError,
)
from maistro.builders.workspace import _MAX_OUTPUT_BYTES, SandboxedShell, ShellResult


@pytest.fixture()
def shell(tmp_path: Path) -> SandboxedShell:
    return SandboxedShell(tmp_path)


# ---------------------------------------------------------------------------
# Blocked commands
# ---------------------------------------------------------------------------


class TestBlockedCommands:
    def test_sudo_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(BlockedCommandError) as exc_info:
            shell.run(["sudo", "apt", "install", "vim"])
        assert exc_info.value.cmd[0] == "sudo"

    def test_su_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(BlockedCommandError):
            shell.run(["su", "-", "root"])

    def test_git_push_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(BlockedCommandError) as exc_info:
            shell.run(["git", "push", "origin", "main"])
        assert exc_info.value.cmd[:2] == ["git", "push"]

    def test_git_push_force_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(BlockedCommandError):
            shell.run(["git", "push", "--force"])

    def test_chmod_777_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(BlockedCommandError):
            shell.run(["chmod", "777", "file.py"])

    def test_chmod_a_plus_rwx_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(BlockedCommandError):
            shell.run(["chmod", "a+rwx", "file.py"])

    def test_chmod_755_allowed(self, shell: SandboxedShell, tmp_path: Path) -> None:
        (tmp_path / "script.sh").write_text("#!/bin/sh\n")
        result = shell.run(["chmod", "755", "script.sh"])
        assert result.returncode == 0

    def test_git_other_subcommands_allowed(self, shell: SandboxedShell) -> None:
        result = shell.run(["git", "status"])
        # returncode may be non-zero if not a git repo, but no BlockedCommandError
        assert isinstance(result, ShellResult)

    def test_git_pull_not_blocked(self, shell: SandboxedShell) -> None:
        # pull is allowed; escape hatch is through the HITL diff review
        try:
            shell.run(["git", "pull"])
        except BlockedCommandError:
            pytest.fail("git pull should not be blocked")
        except Exception:
            pass  # other errors (not a git repo, etc.) are fine


# ---------------------------------------------------------------------------
# Path escape detection
# ---------------------------------------------------------------------------


class TestPathEscape:
    def test_absolute_path_outside_root_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(SandboxEscapeError) as exc_info:
            shell.run(["cat", "/etc/passwd"])
        assert exc_info.value.arg == "/etc/passwd"
        assert exc_info.value.root == shell.root

    def test_relative_dotdot_escape_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(SandboxEscapeError):
            shell.run(["cat", "../../etc/passwd"])

    def test_dotdot_in_nested_path_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(SandboxEscapeError):
            shell.run(["ls", "../outside"])

    def test_path_inside_root_allowed(self, shell: SandboxedShell, tmp_path: Path) -> None:
        (tmp_path / "safe.txt").write_text("ok")
        result = shell.run(["cat", "./safe.txt"])
        assert result.returncode == 0

    def test_absolute_path_inside_root_allowed(self, shell: SandboxedShell, tmp_path: Path) -> None:
        inner = tmp_path / "inner.txt"
        inner.write_text("ok")
        result = shell.run(["cat", str(inner)])
        assert result.returncode == 0

    def test_plain_filename_allowed(self, shell: SandboxedShell, tmp_path: Path) -> None:
        (tmp_path / "plain.txt").write_text("ok")
        result = shell.run(["cat", "plain.txt"])
        assert result.returncode == 0

    def test_root_slash_blocked(self, shell: SandboxedShell) -> None:
        with pytest.raises(SandboxEscapeError):
            shell.run(["ls", "/"])

    def test_error_includes_offending_arg(self, shell: SandboxedShell) -> None:
        with pytest.raises(SandboxEscapeError) as exc_info:
            shell.run(["ls", "/tmp"])
        assert "/tmp" in exc_info.value.arg or str(exc_info.value.root) in str(exc_info.value)


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    def test_timeout_raises_command_timeout_error(self, shell: SandboxedShell) -> None:
        with pytest.raises(CommandTimeoutError) as exc_info:
            shell.run(["sleep", "10"], timeout=0.05)
        assert exc_info.value.timeout == 0.05

    def test_timeout_error_includes_command(self, shell: SandboxedShell) -> None:
        with pytest.raises(CommandTimeoutError) as exc_info:
            shell.run(["sleep", "10"], timeout=0.05)
        assert "sleep" in exc_info.value.cmd

    def test_fast_command_completes(self, shell: SandboxedShell) -> None:
        result = shell.run(["echo", "hello"], timeout=5.0)
        assert result.returncode == 0
        assert "hello" in result.stdout


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class TestOutput:
    def test_stdout_captured(self, shell: SandboxedShell) -> None:
        result = shell.run(["echo", "hello world"])
        assert "hello world" in result.stdout

    def test_stderr_captured(self, shell: SandboxedShell, tmp_path: Path) -> None:
        result = shell.run(["cat", "nonexistent_file_xyz.txt"])
        assert result.returncode != 0
        assert result.stderr  # error message goes to stderr

    def test_elapsed_seconds_positive(self, shell: SandboxedShell) -> None:
        result = shell.run(["echo", "x"])
        assert result.elapsed_seconds >= 0.0

    def test_output_truncation_emits_warning(self, shell: SandboxedShell, tmp_path: Path) -> None:
        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * (_MAX_OUTPUT_BYTES + 1))
        with pytest.warns(OutputTruncatedWarning):
            shell.run(["cat", str(big)])

    def test_output_under_limit_no_warning(self, shell: SandboxedShell) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", OutputTruncatedWarning)
            shell.run(["echo", "small"])


# ---------------------------------------------------------------------------
# CWD enforcement
# ---------------------------------------------------------------------------


class TestCwdEnforcement:
    def test_cwd_is_always_root(self, tmp_path: Path) -> None:
        shell = SandboxedShell(tmp_path)
        result = shell.run(["pwd"])
        assert result.stdout.strip() == str(tmp_path.resolve())

    def test_different_roots_are_independent(self, tmp_path: Path) -> None:
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        shell_a = SandboxedShell(root_a)
        shell_b = SandboxedShell(root_b)
        assert shell_a.run(["pwd"]).stdout.strip() == str(root_a)
        assert shell_b.run(["pwd"]).stdout.strip() == str(root_b)
