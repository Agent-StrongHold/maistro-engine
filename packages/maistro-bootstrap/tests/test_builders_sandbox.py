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


@pytest.mark.ac("SPEC-200/AC-2")
def test_absolute_path_escape_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(SandboxEscapeError):
        shell.run("cat /etc/passwd")


@pytest.mark.ac("SPEC-200/AC-2")
def test_dotdot_escape_blocked(tmp_root: Path) -> None:
    sub = tmp_root / "sub"
    sub.mkdir()
    locked = SandboxedShell(sub)
    with pytest.raises(SandboxEscapeError):
        locked.run("cat ../secret.txt")


@pytest.mark.ac("SPEC-201/AC-3")
def test_safe_command_executes(shell: SandboxedShell) -> None:
    out = shell.run("echo maistro")
    assert "maistro" in out


def test_timeout_raises(shell: SandboxedShell) -> None:
    with pytest.raises(CommandTimeoutError):
        shell.run("sleep 10", timeout=1)


def test_command_substitution_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(BlockedCommandError, match="metacharacters"):
        shell.run("echo $(whoami)")


def test_pipe_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(BlockedCommandError, match="metacharacters"):
        shell.run("cat /etc/passwd | grep root")


def test_semicolon_injection_blocked(shell: SandboxedShell) -> None:
    with pytest.raises(BlockedCommandError, match="metacharacters"):
        shell.run("echo hello; sudo whoami")


def test_env_does_not_contain_os_environ(
    shell: SandboxedShell, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_API_KEY", "super-secret-value")
    out = shell.run("echo nodump")
    assert "super-secret-value" not in out


def test_run_argv_blocks_absolute_path_escape(shell: SandboxedShell) -> None:
    with pytest.raises(SandboxEscapeError):
        shell.run_argv(["cat", "/etc/passwd"])


def test_run_argv_blocks_dotdot_path_escape(tmp_root: Path) -> None:
    sub = tmp_root / "sub"
    sub.mkdir()
    locked = SandboxedShell(sub)
    with pytest.raises(SandboxEscapeError):
        locked.run_argv(["cat", "../secret.txt"])


def test_run_argv_blocks_dangerous_command(shell: SandboxedShell) -> None:
    with pytest.raises(BlockedCommandError, match="git push"):
        shell.run_argv(["git", "push", "origin", "main"])


# ---------------------------------------------------------------------------
# LocalWorktreeSandbox — file operations
# ---------------------------------------------------------------------------


@pytest.mark.ac("SPEC-201/AC-7")
@pytest.mark.ac("SPEC-201/AC-8")
def test_write_and_read_file(sandbox: LocalWorktreeSandbox) -> None:
    sandbox.write_file("hello.txt", "world")
    assert sandbox.read_file("hello.txt") == "world"


def test_edit_file_replaces_unique_string(sandbox: LocalWorktreeSandbox) -> None:
    sandbox.write_file("m.py", "a = 1\nb = 2\nc = 3\n")
    out = sandbox.edit_file("m.py", "b = 2", "b = 22")
    assert "1 replacement" in out
    assert sandbox.read_file("m.py") == "a = 1\nb = 22\nc = 3\n"


def test_edit_file_missing_string_raises(sandbox: LocalWorktreeSandbox) -> None:
    sandbox.write_file("m.py", "a = 1\n")
    with pytest.raises(ValueError, match="not found"):
        sandbox.edit_file("m.py", "z = 9", "z = 10")


def test_edit_file_ambiguous_string_raises(sandbox: LocalWorktreeSandbox) -> None:
    sandbox.write_file("m.py", "x = 1\nx = 1\n")
    with pytest.raises(ValueError, match="appears 2 times"):
        sandbox.edit_file("m.py", "x = 1", "x = 2")


def test_edit_file_escape_blocked(sandbox: LocalWorktreeSandbox) -> None:
    with pytest.raises(SandboxEscapeError):
        sandbox.edit_file("../escape.txt", "a", "b")


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


@pytest.mark.parametrize("glob", ["../*.py", "../../**/*.py", "/tmp/*.py"])
def test_search_glob_cannot_read_outside_sandbox(tmp_root: Path, glob: str) -> None:
    root = tmp_root / "root"
    root.mkdir()
    (tmp_root / "secret.py").write_text("needle", encoding="utf-8")
    sandbox = LocalWorktreeSandbox(root)

    with pytest.raises(SandboxEscapeError):
        sandbox.search("needle", glob=glob)


# ---------------------------------------------------------------------------
# LocalWorktreeSandbox — diff (no git repo — falls back gracefully)
# ---------------------------------------------------------------------------


def test_diff_returns_string(sandbox: LocalWorktreeSandbox) -> None:
    result = sandbox.diff()
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.ac("SPEC-201/AC-6")
def test_local_worktree_sandbox_implements_protocol(sandbox: LocalWorktreeSandbox) -> None:
    assert isinstance(sandbox, BuilderSandbox)


# ---------------------------------------------------------------------------
# BuilderSession
# ---------------------------------------------------------------------------


@pytest.mark.ac("SPEC-201/AC-4")
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
@pytest.mark.ac("SPEC-201/AC-1")
@pytest.mark.ac("SPEC-201/AC-2")
async def test_turn_runner_no_llm(sandbox: LocalWorktreeSandbox) -> None:
    session = BuilderSession(sandbox=sandbox)
    runner = TurnRunner(session=session, config=AgentLoopConfig())
    result = await runner.execute_turn(messages=[{"role": "user", "content": "hi"}])
    # With no gateway configured, LiteLLMCallable returns a stub message.
    assert "LiteLLM" in result["content"] or "no LLM" in result["content"]


# ---------------------------------------------------------------------------
# TurnRunner — stubbed LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.ac("SPEC-201/AC-5")
@pytest.mark.ac("SPEC-201/AC-9")
async def test_turn_runner_with_stub_llm(sandbox: LocalWorktreeSandbox) -> None:
    session = BuilderSession(sandbox=sandbox)
    runner = TurnRunner(session=session, config=AgentLoopConfig())

    def _stub_llm(messages: list, **kwargs: object) -> dict:
        return {"content": "stub response", "stop_reason": "end_turn"}

    runner.set_llm(_stub_llm)
    result = await runner.execute_turn(messages=[{"role": "user", "content": "write hello.py"}])
    assert result["content"] == "stub response"
    assert session.messages[-1]["role"] == "assistant"
