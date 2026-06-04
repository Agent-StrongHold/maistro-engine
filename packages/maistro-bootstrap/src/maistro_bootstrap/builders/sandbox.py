"""Ephemeral git-worktree sandbox for the builders DAG (SPEC-200).

The sandbox creates a throwaway git worktree at /tmp/maistro-ws-{id}/,
gives the agent a SandboxedShell locked to that directory, and tears it
down on exit.  Nothing runs on the root filesystem.
"""

from __future__ import annotations

import contextlib
import logging
import re
import shlex
import subprocess
import tempfile
import warnings
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from maistro_bootstrap.builders.errors import (
    BlockedCommandError,
    CommandTimeoutError,
    OutputTruncatedWarning,
    SandboxEscapeError,
    WorkspaceTeardownError,
)

logger = logging.getLogger(__name__)

_OUTPUT_CAP = 1 * 1024 * 1024  # 1 MB
_DEFAULT_TIMEOUT = 30  # seconds

# Characters that enable shell injection regardless of the blocklist.
# Reject before any other check so the blocklist can't be bypassed via
# $(), backticks, semicolons, pipes, redirects, or newline smuggling.
_INJECTION_CHARS = re.compile(r"[;|&<>`$\\\n\r]|\$\(|\}\{")

_BLOCKED_PATTERNS = (
    "sudo",
    "su ",
    "su\t",
    "git push",
    "git force",
    "chmod 777",
    "chmod -R 777",
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){",  # fork bomb prefix
)

# Minimal environment passed to every subprocess — never inherit os.environ
# into LLM-authored commands to avoid leaking API keys, tokens, etc.
_SAFE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "TERM": "dumb",
}


@runtime_checkable
class BuilderSandbox(Protocol):
    """Interface shared by all sandbox implementations."""

    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> None: ...
    def run_command(self, cmd: str, *, timeout: int = _DEFAULT_TIMEOUT) -> str: ...
    def diff(self) -> str: ...
    def search(self, pattern: str, *, glob: str = "**/*.py") -> list[str]: ...


class SandboxedShell:
    """Subprocess executor locked to a root directory.

    Blocks dangerous commands and detects path-escape attempts before
    any command reaches the OS.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _check_paths(self, tokens: list[str]) -> None:
        """Raise SandboxEscapeError if any token resolves outside the root."""
        for token in tokens:
            candidate = self._root / token
            try:
                candidate.resolve().relative_to(self._root)
            except ValueError:
                raise SandboxEscapeError(
                    f"Path escape detected: {token!r} escapes sandbox root {self._root}"
                ) from None

    def run(self, cmd: str, *, timeout: int = _DEFAULT_TIMEOUT) -> str:
        # 1. Reject shell-injection metacharacters before anything else.
        if _INJECTION_CHARS.search(cmd):
            raise BlockedCommandError(
                f"Shell metacharacters not allowed in sandbox commands: {cmd!r}"
            )

        # 2. Blocklist check on the lowercased raw string.
        cmd_lower = cmd.lower()
        for pattern in _BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                raise BlockedCommandError(f"Blocked command: {pattern!r} in {cmd!r}")

        # 3. Parse with shlex for correct quoted-token handling, then check paths.
        try:
            tokens = shlex.split(cmd)
        except ValueError as exc:
            raise BlockedCommandError(f"Unparseable command: {exc}") from exc
        self._check_paths(tokens)

        try:
            result = subprocess.run(
                cmd,
                shell=True,  # nosec B602 — shell=True is intentional; injection
                # is prevented above by metachar rejection + shlex parse
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=timeout,
                # Minimal env — never inherit os.environ into LLM-authored commands.
                env={**_SAFE_ENV, "HOME": str(self._root)},
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandTimeoutError(f"Command timed out after {timeout}s: {cmd!r}") from exc

        out = (result.stdout or "") + (result.stderr or "")
        if len(out) > _OUTPUT_CAP:
            warnings.warn(
                f"Output truncated to {_OUTPUT_CAP // 1024}KB",
                OutputTruncatedWarning,
                stacklevel=2,
            )
            out = out[:_OUTPUT_CAP]
        return out


class GitWorktreeWorkspace:
    """Context manager that creates an ephemeral git worktree.

    Usage::

        with GitWorktreeWorkspace(repo_root=Path("/my/repo")) as ws:
            out = ws.shell.run("pytest -q")
            patch = ws.diff()
    """

    def __init__(self, repo_root: Path, *, base_ref: str = "HEAD") -> None:
        self._repo_root = repo_root.resolve()
        self._base_ref = base_ref
        self._branch: str | None = None
        self._path: Path | None = None
        self._shell: SandboxedShell | None = None

    @property
    def path(self) -> Path:
        if self._path is None:
            raise RuntimeError("Workspace not entered")
        return self._path

    @property
    def shell(self) -> SandboxedShell:
        if self._shell is None:
            raise RuntimeError("Workspace not entered")
        return self._shell

    def __enter__(self) -> GitWorktreeWorkspace:
        uid = uuid4().hex[:12]
        self._branch = f"builders/{uid}"
        self._path = Path(tempfile.mkdtemp(prefix=f"maistro-ws-{uid}-"))
        subprocess.run(  # nosec B603
            [
                "git",
                "worktree",
                "add",
                str(self._path),
                "-b",
                self._branch,
                self._base_ref,
            ],
            cwd=self._repo_root,
            check=True,
            capture_output=True,
        )
        self._shell = SandboxedShell(self._path)
        logger.info("worktree created path=%s branch=%s", self._path, self._branch)
        return self

    def __exit__(self, *_: object) -> None:
        if self._path is None:
            return
        try:
            subprocess.run(  # nosec B603
                ["git", "worktree", "remove", "--force", str(self._path)],
                cwd=self._repo_root,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise WorkspaceTeardownError(f"Worktree removal failed: {exc}") from exc
        finally:
            with contextlib.suppress(Exception):
                import shutil

                shutil.rmtree(self._path, ignore_errors=True)
        logger.info("worktree removed path=%s", self._path)

    def diff(self) -> str:
        result = subprocess.run(  # nosec B603
            ["git", "diff"],
            cwd=self._path,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def commit(self, message: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=self._path, check=True, capture_output=True)  # nosec B603
        result = subprocess.run(  # nosec B603
            ["git", "commit", "-m", message],
            cwd=self._path,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()


class LocalWorktreeSandbox:
    """Sandbox implementation backed by a GitWorktreeWorkspace.

    Implements the BuilderSandbox protocol — the TUI and agent loop use
    this interface; they never touch the host filesystem directly.
    """

    def __init__(self, repo_root: Path, *, base_ref: str = "HEAD") -> None:
        self._repo_root = repo_root.resolve()
        self._base_ref = base_ref
        self._ws: GitWorktreeWorkspace | None = None
        self._shell: SandboxedShell | None = None

    def __enter__(self) -> LocalWorktreeSandbox:
        self._ws = GitWorktreeWorkspace(self._repo_root, base_ref=self._base_ref)
        self._ws.__enter__()
        self._shell = self._ws.shell
        return self

    def __exit__(self, *args: object) -> None:
        if self._ws is not None:
            with contextlib.suppress(WorkspaceTeardownError):
                self._ws.__exit__(*args)

    def _require_shell(self) -> SandboxedShell:
        if self._shell is None:
            # Lazy: create a shell on the repo root if not used as context manager
            self._shell = SandboxedShell(self._repo_root)
        return self._shell

    def _resolve(self, path: str) -> Path:
        root = self._ws.path if self._ws else self._repo_root
        resolved = (root / path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            raise SandboxEscapeError(f"Path {path!r} escapes sandbox root") from None
        return resolved

    def read_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def run_command(self, cmd: str, *, timeout: int = _DEFAULT_TIMEOUT) -> str:
        return self._require_shell().run(cmd, timeout=timeout)

    def diff(self) -> str:
        if self._ws:
            return self._ws.diff()
        result = subprocess.run(  # nosec B603
            ["git", "diff"],
            cwd=self._repo_root,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def search(self, pattern: str, *, glob: str = "**/*.py") -> list[str]:
        root = self._ws.path if self._ws else self._repo_root
        matches = []
        for p in root.glob(glob):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                if pattern in text:
                    matches.append(str(p.relative_to(root)))
            except OSError:
                pass
        return matches
