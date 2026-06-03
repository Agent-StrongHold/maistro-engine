"""Builders safety layer — ephemeral workspace + sandboxed shell (SPEC-200).

GitWorktreeWorkspace  — git worktree in /tmp, destroyed on exit.
SandboxedShell        — subprocess executor locked to workspace root.
WorkspaceContext      — ties workspace + shell + diff application together.

Usage
-----
    with GitWorktreeWorkspace(repo_root=Path("."), base_ref="HEAD") as ws:
        ctx = WorkspaceContext(ws)
        result = ctx.shell.run(["pytest", "-q"])
        diff = ctx.diff()
        ctx.apply_diff(confirmed=True)   # only after human reviews diff
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
import time
import uuid
import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from maistro.builders.errors import (
    BlockedCommandError,
    CommandTimeoutError,
    DiffApplyError,
    OutputTruncatedWarning,
    SandboxEscapeError,
    UnconfirmedDiffApply,
    WorkspaceTeardownError,
)

_WORKSPACE_ROOT = Path(os.environ.get("MAISTRO_WORKSPACE_ROOT", "/tmp"))
_MAX_OUTPUT_BYTES = 1024 * 1024  # 1 MB


# ---------------------------------------------------------------------------
# WorkspaceStatus
# ---------------------------------------------------------------------------


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    COMMITTED = "committed"
    TORN_DOWN = "torn_down"


# ---------------------------------------------------------------------------
# ShellResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShellResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float


# ---------------------------------------------------------------------------
# SandboxedShell
# ---------------------------------------------------------------------------


class SandboxedShell:
    """Subprocess executor locked to a workspace root.

    All commands run with cwd=root. Path arguments that resolve outside root
    raise SandboxEscapeError before the subprocess is launched.
    """

    _BLOCKED_EXECUTABLES: frozenset[str] = frozenset({"sudo", "su"})

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _check_blocked(self, cmd: list[str]) -> None:
        if not cmd:
            return
        executable = Path(cmd[0]).name
        if executable in self._BLOCKED_EXECUTABLES:
            raise BlockedCommandError(cmd)
        if executable == "git" and len(cmd) > 1 and cmd[1] == "push":
            raise BlockedCommandError(cmd)
        if executable == "chmod" and any(arg in ("777", "a+rwx") for arg in cmd[1:]):
            raise BlockedCommandError(cmd)

    def _resolve_if_path(self, arg: str) -> Path | None:
        """Interpret arg as a path if it looks like one; return resolved Path or None."""
        p = Path(arg)
        if p.is_absolute():
            return p.resolve()
        if arg.startswith(".") or "/" in arg:
            return (self._root / p).resolve()
        return None

    def _check_paths(self, cmd: list[str]) -> None:
        for arg in cmd[1:]:
            resolved = self._resolve_if_path(arg)
            if resolved is None:
                continue
            try:
                resolved.relative_to(self._root)
            except ValueError:
                raise SandboxEscapeError(arg, self._root) from None

    # ------------------------------------------------------------------
    # Output handling
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_output(data: bytes) -> tuple[bytes, int]:
        if len(data) <= _MAX_OUTPUT_BYTES // 2:
            return data, 0
        keep = _MAX_OUTPUT_BYTES // 2
        half = keep // 2
        dropped = len(data) - keep
        return data[:half] + b"\n[...output truncated...]\n" + data[-half:], dropped

    def _decode_outputs(self, stdout: bytes, stderr: bytes) -> tuple[str, str]:
        total = len(stdout) + len(stderr)
        if total > _MAX_OUTPUT_BYTES:
            stdout, so_dropped = self._truncate_output(stdout)
            stderr, se_dropped = self._truncate_output(stderr)
            dropped = so_dropped + se_dropped
            if dropped > 0:
                warnings.warn(OutputTruncatedWarning(dropped), stacklevel=3)
        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        cmd: list[str],
        *,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> ShellResult:
        """Run cmd inside the sandbox. Raises on escape, block, or timeout."""
        self._check_blocked(cmd)
        self._check_paths(cmd)

        t0 = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._root),
                capture_output=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise CommandTimeoutError(cmd, timeout) from None

        stdout, stderr = self._decode_outputs(result.stdout, result.stderr)
        return ShellResult(
            returncode=result.returncode,
            stdout=stdout,
            stderr=stderr,
            elapsed_seconds=time.monotonic() - t0,
        )


# ---------------------------------------------------------------------------
# GitWorktreeWorkspace
# ---------------------------------------------------------------------------


class GitWorktreeWorkspace:
    """Ephemeral git worktree in /tmp (or MAISTRO_WORKSPACE_ROOT).

    Always use as a context manager so teardown is guaranteed:

        with GitWorktreeWorkspace(repo_root, base_ref="HEAD") as ws:
            ctx = WorkspaceContext(ws)
            ...
    """

    def __init__(
        self,
        repo_root: Path,
        *,
        base_ref: str = "HEAD",
        workspace_id: str | None = None,
    ) -> None:
        self._repo_root = repo_root.resolve()
        self._id = workspace_id or uuid.uuid4().hex[:12]
        self._branch = f"builders/{self._id}"
        self._root = _WORKSPACE_ROOT / f"maistro-ws-{self._id}"
        self._base_ref = base_ref
        self._status = WorkspaceStatus.ACTIVE
        self._shell: SandboxedShell | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def root(self) -> Path:
        return self._root

    @property
    def branch(self) -> str:
        return self._branch

    @property
    def status(self) -> WorkspaceStatus:
        return self._status

    @property
    def shell(self) -> SandboxedShell:
        if self._shell is None:
            raise RuntimeError(
                "Workspace not initialised — call create() or use as context manager"
            )
        return self._shell

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(self) -> None:
        """Create the git worktree at self.root."""
        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                str(self._root),
                "-b",
                self._branch,
                self._base_ref,
            ],
            cwd=str(self._repo_root),
            check=True,
            capture_output=True,
        )
        self._shell = SandboxedShell(self._root)

    def teardown(self, *, keep_branch: bool = False) -> None:
        """Remove the git worktree and (optionally) its branch. Idempotent."""
        if self._status == WorkspaceStatus.TORN_DOWN:
            return
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(self._root)],
                cwd=str(self._repo_root),
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise WorkspaceTeardownError(
                self._root, exc.stderr.decode("utf-8", errors="replace")
            ) from exc
        finally:
            self._status = WorkspaceStatus.TORN_DOWN

        if not keep_branch:
            subprocess.run(
                ["git", "branch", "-D", self._branch],
                cwd=str(self._repo_root),
                capture_output=True,
            )

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    def diff(self) -> str:
        """Unified diff of the worktree's HEAD vs base_ref."""
        result = subprocess.run(
            ["git", "diff", self._base_ref, "HEAD"],
            cwd=str(self._root),
            capture_output=True,
            check=True,
        )
        return result.stdout.decode("utf-8", errors="replace")

    def commit(self, message: str) -> str:
        """Stage all changes, commit, return SHA."""
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(self._root),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(self._root),
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(self._root),
            capture_output=True,
            check=True,
        )
        self._status = WorkspaceStatus.COMMITTED
        return result.stdout.decode().strip()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> GitWorktreeWorkspace:
        self.create()
        return self

    def __exit__(self, *_: object) -> None:

        with contextlib.suppress(WorkspaceTeardownError):
            self.teardown()


# ---------------------------------------------------------------------------
# ApplyResult + WorkspaceContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApplyResult:
    files_changed: int
    diff: str


class WorkspaceContext:
    """Coordinator: workspace + shell + diff-to-real-repo application."""

    def __init__(self, workspace: GitWorktreeWorkspace) -> None:
        self._ws = workspace

    @property
    def workspace(self) -> GitWorktreeWorkspace:
        return self._ws

    @property
    def shell(self) -> SandboxedShell:
        return self._ws.shell

    def diff(self) -> str:
        return self._ws.diff()

    def apply_diff(self, *, confirmed: bool) -> ApplyResult:
        """Apply the sandbox diff to the real repo.

        Runs `git apply --check` first. The real repo is never touched if
        the check fails or confirmed is False.
        """
        if not confirmed:
            raise UnconfirmedDiffApply()

        diff_text = self.diff()
        if not diff_text.strip():
            return ApplyResult(files_changed=0, diff="")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, encoding="utf-8"
        ) as f:
            f.write(diff_text)
            patch_path = Path(f.name)

        try:
            check = subprocess.run(
                ["git", "apply", "--check", str(patch_path)],
                cwd=str(self._ws._repo_root),
                capture_output=True,
            )
            if check.returncode != 0:
                raise DiffApplyError(check.stderr.decode("utf-8", errors="replace"))

            subprocess.run(
                ["git", "apply", str(patch_path)],
                cwd=str(self._ws._repo_root),
                check=True,
                capture_output=True,
            )
        finally:
            patch_path.unlink(missing_ok=True)

        files_changed = diff_text.count("\ndiff --git ")
        return ApplyResult(files_changed=max(files_changed, 1), diff=diff_text)
