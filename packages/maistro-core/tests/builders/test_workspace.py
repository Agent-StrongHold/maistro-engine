"""Tests for GitWorktreeWorkspace and WorkspaceContext — SPEC-200."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maistro.builders.errors import (
    DiffApplyError,
    UnconfirmedDiffApply,
    WorkspaceTeardownError,
)
from maistro.builders.workspace import (
    ApplyResult,
    GitWorktreeWorkspace,
    SandboxedShell,
    WorkspaceContext,
    WorkspaceStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws(tmp_path: Path, workspace_id: str = "abc123") -> GitWorktreeWorkspace:
    """Return an uninitialised workspace (create() not called)."""
    return GitWorktreeWorkspace(
        repo_root=tmp_path,
        base_ref="HEAD",
        workspace_id=workspace_id,
    )


def _mock_run_ok(*_args: object, **_kwargs: object) -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = b""
    m.stderr = b""
    return m


# ---------------------------------------------------------------------------
# GitWorktreeWorkspace — properties
# ---------------------------------------------------------------------------


class TestWorkspaceProperties:
    def test_branch_name_format(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="deadbeef")
        assert ws.branch == "builders/deadbeef"

    def test_root_is_under_workspace_root(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="abc")
        assert str(ws.root).endswith("maistro-ws-abc")

    def test_root_not_under_repo_root(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="xyz")
        assert not str(ws.root).startswith(str(tmp_path))

    def test_initial_status_is_active(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path)
        assert ws.status == WorkspaceStatus.ACTIVE

    def test_shell_raises_before_create(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path)
        with pytest.raises(RuntimeError, match="not initialised"):
            _ = ws.shell


# ---------------------------------------------------------------------------
# GitWorktreeWorkspace.create()
# ---------------------------------------------------------------------------


class TestWorkspaceCreate:
    def test_create_calls_git_worktree_add(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="t1")
        with patch("subprocess.run", return_value=_mock_run_ok()) as mock_run:
            ws.create()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "git"
        assert cmd[1] == "worktree"
        assert cmd[2] == "add"
        assert str(ws.root) in cmd

    def test_create_passes_branch_name(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="t2")
        with patch("subprocess.run", return_value=_mock_run_ok()) as mock_run:
            ws.create()
        cmd = mock_run.call_args[0][0]
        assert "-b" in cmd
        assert ws.branch in cmd

    def test_create_passes_base_ref(self, tmp_path: Path) -> None:
        ws = GitWorktreeWorkspace(tmp_path, base_ref="develop", workspace_id="t3")
        with patch("subprocess.run", return_value=_mock_run_ok()) as mock_run:
            ws.create()
        cmd = mock_run.call_args[0][0]
        assert "develop" in cmd

    def test_create_sets_shell(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path)
        with patch("subprocess.run", return_value=_mock_run_ok()):
            ws.create()
        assert isinstance(ws.shell, SandboxedShell)

    def test_create_cwd_is_repo_root(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="t4")
        with patch("subprocess.run", return_value=_mock_run_ok()) as mock_run:
            ws.create()
        kwargs = mock_run.call_args[1]
        assert Path(kwargs["cwd"]) == tmp_path.resolve()


# ---------------------------------------------------------------------------
# GitWorktreeWorkspace.teardown()
# ---------------------------------------------------------------------------


class TestWorkspaceTeardown:
    def test_teardown_calls_worktree_remove(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="td1")
        with patch("subprocess.run", return_value=_mock_run_ok()) as mock_run:
            ws.create()
            ws.teardown()
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert any("remove" in c for c in cmds)

    def test_teardown_idempotent(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path)
        with patch("subprocess.run", return_value=_mock_run_ok()):
            ws.create()
            ws.teardown()
            ws.teardown()  # second call must not raise

    def test_teardown_sets_status_torn_down(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path)
        with patch("subprocess.run", return_value=_mock_run_ok()):
            ws.create()
            ws.teardown()
        assert ws.status == WorkspaceStatus.TORN_DOWN

    def test_teardown_deletes_branch_by_default(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="td2")
        with patch("subprocess.run", return_value=_mock_run_ok()) as mock_run:
            ws.create()
            ws.teardown()
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert any("branch" in c and "-D" in c for c in cmds)

    def test_teardown_keep_branch_skips_delete(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="td3")
        with patch("subprocess.run", return_value=_mock_run_ok()) as mock_run:
            ws.create()
            ws.teardown(keep_branch=True)
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert not any("-D" in c for c in cmds)

    def test_teardown_failure_raises_workspace_teardown_error(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path)
        fail = MagicMock()
        fail.side_effect = [_mock_run_ok(), subprocess.CalledProcessError(1, [], stderr=b"err")]
        with patch("subprocess.run", side_effect=fail.side_effect):
            ws.create()
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, [], stderr=b"oops")
            with pytest.raises(WorkspaceTeardownError) as exc_info:
                ws.teardown()
        assert ws.status == WorkspaceStatus.TORN_DOWN  # status set even on failure
        assert "oops" in str(exc_info.value)


# ---------------------------------------------------------------------------
# GitWorktreeWorkspace — context manager
# ---------------------------------------------------------------------------


class TestWorkspaceContextManager:
    def test_context_manager_creates_and_tears_down(self, tmp_path: Path) -> None:
        with patch("subprocess.run", return_value=_mock_run_ok()) as mock_run:
            with GitWorktreeWorkspace(tmp_path, workspace_id="cm1") as ws:
                assert ws.status == WorkspaceStatus.ACTIVE
            assert ws.status == WorkspaceStatus.TORN_DOWN

    def test_context_manager_tears_down_on_exception(self, tmp_path: Path) -> None:
        with patch("subprocess.run", return_value=_mock_run_ok()):
            with pytest.raises(ValueError):
                with GitWorktreeWorkspace(tmp_path, workspace_id="cm2") as ws:
                    raise ValueError("deliberate")
        assert ws.status == WorkspaceStatus.TORN_DOWN

    def test_context_manager_returns_workspace(self, tmp_path: Path) -> None:
        with patch("subprocess.run", return_value=_mock_run_ok()):
            with GitWorktreeWorkspace(tmp_path, workspace_id="cm3") as ws:
                assert isinstance(ws, GitWorktreeWorkspace)


# ---------------------------------------------------------------------------
# GitWorktreeWorkspace.commit()
# ---------------------------------------------------------------------------


class TestWorkspaceCommit:
    def test_commit_sets_status_committed(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path)
        sha_result = MagicMock(stdout=b"abc123\n", returncode=0, stderr=b"")

        def _side(cmd, **kw):
            if "rev-parse" in cmd:
                return sha_result
            return _mock_run_ok()

        with patch("subprocess.run", side_effect=_side):
            ws.create()
            sha = ws.commit("test: add feature")
        assert ws.status == WorkspaceStatus.COMMITTED
        assert sha == "abc123"

    def test_commit_stages_all_files(self, tmp_path: Path) -> None:
        ws = _make_ws(tmp_path, workspace_id="co1")
        calls_seen = []

        def _side(cmd, **kw):
            calls_seen.append(cmd)
            if "rev-parse" in cmd:
                return MagicMock(stdout=b"sha\n", returncode=0, stderr=b"")
            return _mock_run_ok()

        with patch("subprocess.run", side_effect=_side):
            ws.create()
            ws.commit("msg")
        assert any("add" in c and "-A" in c for c in calls_seen)


# ---------------------------------------------------------------------------
# WorkspaceContext.apply_diff()
# ---------------------------------------------------------------------------


class TestApplyDiff:
    def _ws_with_diff(self, tmp_path: Path, diff_content: str) -> WorkspaceContext:
        ws = _make_ws(tmp_path)
        with patch("subprocess.run", return_value=_mock_run_ok()):
            ws.create()
        ctx = WorkspaceContext(ws)
        ctx.diff = lambda: diff_content  # type: ignore[method-assign]
        return ctx

    def test_unconfirmed_raises(self, tmp_path: Path) -> None:
        ctx = self._ws_with_diff(tmp_path, "diff --git a/f b/f\n--- a/f\n+++ b/f\n")
        with pytest.raises(UnconfirmedDiffApply):
            ctx.apply_diff(confirmed=False)

    def test_empty_diff_returns_zero_files(self, tmp_path: Path) -> None:
        ctx = self._ws_with_diff(tmp_path, "")
        result = ctx.apply_diff(confirmed=True)
        assert result.files_changed == 0
        assert result.diff == ""

    def test_whitespace_only_diff_returns_zero_files(self, tmp_path: Path) -> None:
        ctx = self._ws_with_diff(tmp_path, "   \n  ")
        result = ctx.apply_diff(confirmed=True)
        assert result.files_changed == 0

    def test_check_failure_raises_diff_apply_error(self, tmp_path: Path) -> None:
        ctx = self._ws_with_diff(
            tmp_path, "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-old\n+new\n"
        )
        fail = MagicMock(returncode=1, stderr=b"does not apply", stdout=b"")
        with patch("subprocess.run", return_value=fail):
            with pytest.raises(DiffApplyError) as exc_info:
                ctx.apply_diff(confirmed=True)
        assert "does not apply" in str(exc_info.value)

    def test_check_failure_real_repo_untouched(self, tmp_path: Path) -> None:
        ctx = self._ws_with_diff(tmp_path, "some diff content")
        apply_calls = []

        def _side(cmd, **kw):
            apply_calls.append(cmd)
            if "--check" in cmd:
                return MagicMock(returncode=1, stderr=b"fail", stdout=b"")
            return _mock_run_ok()

        with patch("subprocess.run", side_effect=_side), pytest.raises(DiffApplyError):
            ctx.apply_diff(confirmed=True)
        # git apply (without --check) must NOT have been called
        assert not any("apply" in c and "--check" not in c for c in apply_calls)

    def test_successful_apply_returns_result(self, tmp_path: Path) -> None:
        diff = "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-old\n+new\n"
        ctx = self._ws_with_diff(tmp_path, diff)
        with patch("subprocess.run", return_value=_mock_run_ok()):
            result = ctx.apply_diff(confirmed=True)
        assert isinstance(result, ApplyResult)
        assert result.files_changed >= 1
        assert result.diff == diff
