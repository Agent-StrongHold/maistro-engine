"""Tests for the builders sandbox safety layer (SPEC-200)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maistro_bootstrap.builders.agent_loop import AgentLoopConfig, TurnRunner
from maistro_bootstrap.builders.errors import (
    BlockedCommandError,
    CommandTimeoutError,
    SandboxEscapeError,
)
from maistro_bootstrap.builders.sandbox import (
    BuilderSandbox,
    LocalWorktreeSandbox,
    SandboxedShell,
)
from maistro_bootstrap.builders.session import BuilderSession


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def shell(tmp_root: Path) -> SandboxedShell:
    return SandboxedShell(tmp_root)


@pytest.fixture()
def sandbox(tmp_root: Path) -> LocalWorktreeSandbox:
    return LocalWorktreeSandbox(tmp_root)


# ---------------------------------------------------------------------------
# SandboxedShell — blocklist
# ---------------------------------------------------------------------------


def test_sudo_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(BlockedCommandError, match="sudo"):
        shell.run("sudo whoami")


def test_git_push_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(BlockedCommandError, match="git push"):
        shell.run("git push origin main")


def test_chmod_777_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(BlockedCommandError, match="chmod 777"):
        shell.run("chmod 777 /etc")


def test_rm_root_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(BlockedCommandError):
        shell.run("rm -rf /")


# ---------------------------------------------------------------------------
# SandboxedShell — path escape
# ---------------------------------------------------------------------------


def test_absolute_path_escape_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(SandboxEscapeError):
        shell.run("cat /etc/passwd")


def test_dotdot_escape_blocked(tmp_root: Path) -> None:
    sub = tmp_root / "sub"
    sub.mkdir()
    locked = SandboxedShell(sub)
    with pytest.raises(SandboxEscapeError):
        locked.run("cat ../secret.txt")


def test_safe_command_executes(shell: SandboxedShell) -> None:
    out = shell.run("echo maistro")
    assert "maistro" in out


def test_timeout_raises(shell: SandboxedShell) -> None:
    with pytest.raises(CommandTimeoutError):
        shell.run("sleep 10", timeout=1)


# ---------------------------------------------------------------------------
# LocalWorktreeSandbox — file operations
# ---------------------------------------------------------------------------


def test_write_and_read_file(sandbox: LocalWorktreeSandbox) -> None:
    sandbox.write_file("hello.txt", "world")
    assert sandbox.read_file("hello.txt") == "world"


def test_write_creates_parent_dirs(sandbox: LocalWorktreeSandbox) -> None:
    sandbox.write_file("a/b/c.txt", "nested")
    assert sandbox.read_file("a/b/c.txt") == "nested"


def test_read_nonexistent_raises(sandbox: LocalWorktreeSandbox) -> None:
    with pytest.raises(FileNotFoundError):
        sandbox.read_file("missing.txt")


def test_write_escape_blocked(sandbox: LocalWorktreeSandbox) -> None:
    with pytest.raises(SandboxEscapeError):
        sandbox.write_file("../escape.txt", "bad")


def test_read_escape_blocked(sandbox: LocalWorktreeSandbox) -> None:
    with pytest.raises(SandboxEscapeError):
        sandbox.read_file("../../etc/passwd")


# ---------------------------------------------------------------------------
# LocalWorktreeSandbox — search
# ---------------------------------------------------------------------------


def test_search_finds_pattern(sandbox: LocalWorktreeSandbox) -> None:
    sandbox.write_file("code.py", "def my_func(): pass")
    matches = sandbox.search("my_func")
    assert "code.py" in matches


def test_search_returns_empty_when_no_match(sandbox: LocalWorktreeSandbox) -> None:
    sandbox.write_file("code.py", "x = 1")
    assert sandbox.search("definitely_not_here") == []


def test_search_glob_filters(sandbox: LocalWorktreeSandbox) -> None:
    sandbox.write_file("a.py", "needle")
    sandbox.write_file("b.txt", "needle")
    py_matches = sandbox.search("needle", glob="**/*.py")
    txt_matches = sandbox.search("needle", glob="**/*.txt")
    assert "a.py" in py_matches
    assert "b.txt" not in py_matches
    assert "b.txt" in txt_matches


# ---------------------------------------------------------------------------
# LocalWorktreeSandbox — diff (no git repo — falls back gracefully)
# ---------------------------------------------------------------------------


def test_diff_returns_string(sandbox: LocalWorktreeSandbox) -> None:
    result = sandbox.diff()
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_local_worktree_sandbox_implements_protocol(sandbox: LocalWorktreeSandbox) -> None:
    assert isinstance(sandbox, BuilderSandbox)


# ---------------------------------------------------------------------------
# BuilderSession
# ---------------------------------------------------------------------------


def test_session_add_and_clear(sandbox: LocalWorktreeSandbox) -> None:
    session = BuilderSession(sandbox=sandbox)
    session.add_user("hello")
    session.add_assistant("hi")
    assert len(session.messages) == 2
    session.clear_history()
    assert session.messages == []


# ---------------------------------------------------------------------------
# TurnRunner — no LLM configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_runner_no_llm(sandbox: LocalWorktreeSandbox) -> None:
    session = BuilderSession(sandbox=sandbox)
    runner = TurnRunner(session=session, config=AgentLoopConfig())
    result = await runner.execute_turn(messages=[{"role": "user", "content": "hi"}])
    assert "no LLM" in result["content"]


# ---------------------------------------------------------------------------
# TurnRunner — stubbed LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_runner_with_stub_llm(sandbox: LocalWorktreeSandbox) -> None:
    session = BuilderSession(sandbox=sandbox)
    runner = TurnRunner(session=session, config=AgentLoopConfig())

    def _stub_llm(messages: list, **kwargs: object) -> dict:
        return {"content": "stub response", "stop_reason": "end_turn"}

    runner.set_llm(_stub_llm)
    result = await runner.execute_turn(messages=[{"role": "user", "content": "write hello.py"}])
    assert result["content"] == "stub response"
    assert session.messages[-1]["role"] == "assistant"
