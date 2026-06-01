"""Tests for Shell — security and functionality."""

from __future__ import annotations

import pytest
from pathlib import Path

from orchestrator.tools.shell import Shell


@pytest.fixture
def shell(tmp_path: Path) -> Shell:
    return Shell(tmp_path, timeout=5)


class TestCommandExecution:
    """Basic command execution tests."""

    @pytest.mark.asyncio
    async def test_simple_command(self, shell: Shell):
        """Basic command should execute and return output."""
        result = await shell.run("echo hello")
        assert result.returncode == 0
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_multiword_output(self, shell: Shell):
        """Command with multiple words should work."""
        result = await shell.run("echo hello world")
        assert result.returncode == 0
        assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_command_with_exit_code(self, shell: Shell):
        """Command exit codes should be captured."""
        result = await shell.run("false")
        assert result.returncode != 0

    @pytest.mark.asyncio
    async def test_success_exit_code(self, shell: Shell):
        """Successful command should have exit code 0."""
        result = await shell.run("true")
        assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_stderr_captured(self, shell: Shell):
        """Stderr should be captured separately."""
        result = await shell.run("ls nonexistent_file_xyz")
        assert result.returncode != 0
        assert result.stderr  # Some error message

    @pytest.mark.asyncio
    async def test_command_not_found(self, shell: Shell):
        """Nonexistent command should return error result."""
        result = await shell.run("this_command_does_not_exist_xyz")
        assert result.returncode != 0
        assert (
            "not found" in result.stderr.lower()
            or "syntax" in result.stderr.lower()
            or result.returncode == -1
        )


class TestSecurityMeasures:
    """Security: Command execution safety."""

    @pytest.mark.asyncio
    async def test_no_shell_expansion(self, shell: Shell, tmp_path: Path):
        """Shell metacharacters should not be interpreted."""
        # If using shell=True, this would create a file
        await shell.run("echo test > should_not_create.txt")
        # With shell=False via shlex, this will fail or not create the file
        assert not (tmp_path / "should_not_create.txt").exists()

    @pytest.mark.asyncio
    async def test_pipe_not_interpreted(self, shell: Shell, tmp_path: Path):
        """Pipe characters should not be interpreted."""
        result = await shell.run("echo test | cat")
        # With shell=False, '|' and 'cat' are literal arguments
        # Either it fails or outputs the literal '|'
        assert "|" in result.stdout or result.returncode != 0

    @pytest.mark.asyncio
    async def test_invalid_syntax_handled(self, shell: Shell):
        """Invalid command syntax should return error, not crash."""
        result = await shell.run('echo "unterminated')
        assert result.returncode == -1
        assert "syntax" in result.stderr.lower()


class TestTimeout:
    """Timeout handling tests."""

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self):
        """Long-running command should be killed on timeout."""
        shell = Shell("/tmp", timeout=1)
        result = await shell.run("sleep 10", timeout=1)
        assert result.timed_out
        assert result.returncode == -1

    @pytest.mark.asyncio
    async def test_short_command_does_not_timeout(self):
        """Quick command should not timeout."""
        shell = Shell("/tmp", timeout=10)
        result = await shell.run("echo quick", timeout=5)
        assert not result.timed_out
        assert result.returncode == 0


class TestOutputHandling:
    """Output handling tests."""

    @pytest.mark.asyncio
    async def test_captures_stdout(self, shell: Shell):
        """Standard output should be captured."""
        result = await shell.run("seq 1 10")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) == 10
        assert lines[0] == "1"
        assert lines[-1] == "10"

    @pytest.mark.asyncio
    async def test_empty_output_handled(self, shell: Shell):
        """Command with no output should not fail."""
        result = await shell.run("true")
        assert result.returncode == 0
        assert result.stdout == ""

    @pytest.mark.asyncio
    async def test_large_output_handled(self, shell: Shell):
        """Large output should be captured (may be truncated)."""
        result = await shell.run("seq 1 5000")
        assert result.returncode == 0
        assert len(result.stdout) > 0
        # Verify some content exists
        assert "1" in result.stdout


class TestWorkingDirectory:
    """Working directory tests."""

    @pytest.mark.asyncio
    async def test_runs_in_cwd(self, tmp_path: Path):
        """Commands should run in the specified working directory."""
        shell = Shell(tmp_path, timeout=5)

        # Create a file in the temp dir
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        # List should show the file
        result = await shell.run("ls")
        assert result.returncode == 0
        assert "test.txt" in result.stdout
