"""Sandbox adapters for live-testable builder sessions."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast


@dataclass(frozen=True)
class SandboxCommandResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float


class BuilderSandbox(Protocol):
    """Minimum sandbox interface consumed by the session loop."""

    def read_file(self, path: str) -> str: ...

    def write_file(self, path: str, content: str) -> None: ...

    def search(self, query: str) -> list[str]: ...

    def run_command(self, argv: list[str], *, timeout: float) -> SandboxCommandResult: ...

    def diff(self) -> str: ...


class LocalWorktreeSandbox:
    """Live-testable sandbox rooted at a repo/worktree path.

    This backend is the fast v1 substrate. It validates path containment and
    exposes the same narrow interface the future container/Kata backend should
    implement.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, path: str) -> Path:
        resolved = (self._root / path).resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError:
            raise ValueError(f"path escapes builder sandbox: {path}") from None
        return resolved

    def read_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def search(self, query: str) -> list[str]:
        matches: list[str] = []
        for path in self._root.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if query in text:
                matches.append(str(path.relative_to(self._root)))
        return matches[:50]

    def run_command(self, argv: list[str], *, timeout: float) -> SandboxCommandResult:
        if not argv:
            raise ValueError("run_command requires argv")
        started = time.monotonic()
        result = subprocess.run(
            argv,
            cwd=str(self._root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return SandboxCommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_seconds=time.monotonic() - started,
        )

    def diff(self) -> str:
        result = subprocess.run(
            ["git", "diff", "--"],
            cwd=str(self._root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return result.stderr
        return result.stdout


class BuildersWorkspaceSandbox:
    """Adapter around maistro-core's SPEC-200 worktree safety layer."""

    def __init__(self, repo_root: Path, *, base_ref: str = "HEAD") -> None:
        from maistro.builders.workspace import (  # type: ignore[import-untyped]
            GitWorktreeWorkspace,
            WorkspaceContext,
        )

        self._workspace = GitWorktreeWorkspace(repo_root=repo_root, base_ref=base_ref)
        self._workspace.create()
        self._context = WorkspaceContext(self._workspace)
        self._local = LocalWorktreeSandbox(self._workspace.root)

    @property
    def root(self) -> Path:
        return cast(Path, self._workspace.root)

    def close(self) -> None:
        self._workspace.teardown()

    def read_file(self, path: str) -> str:
        return self._local.read_file(path)

    def write_file(self, path: str, content: str) -> None:
        self._local.write_file(path, content)

    def search(self, query: str) -> list[str]:
        return self._local.search(query)

    def run_command(self, argv: list[str], *, timeout: float) -> SandboxCommandResult:
        result = self._context.shell.run(argv, timeout=timeout)
        return SandboxCommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_seconds=result.elapsed_seconds,
        )

    def diff(self) -> str:
        return cast(str, self._context.diff())
