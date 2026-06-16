"""Trusted-development CampaignWorkspace backed by a git worktree.

WARNING: executes commands on the host with the caller's permissions.
Use only for trusted local development. Switch to IsolatedBuilderSandbox
(isolated_workspace_factory) when running untrusted model-generated code.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

from maistro.sandbox.protocol import ExecResult

_BLOCKED = ("git push", "git force", "sudo", "rm -rf /", "mkfs", ":(){")
_COMMIT_SHA_LEN = 40


class WorktreeCampaignWorkspace:
    """CampaignWorkspace implemented as a throwaway git worktree.

    A fresh worktree is created at a temp path for each workspace instance.
    The incumbent patch is applied on top of the pinned base commit before any
    provider action runs. diff() captures every workspace change relative to
    the base commit so the campaign store gets an accurate candidate patch.
    """

    isolation_tier: str = "trusted-worktree"
    backend_name: str = "git-worktree"

    def __init__(
        self,
        root: Path,
        repo_root: Path,
        base_commit: str,
        git_version: str,
    ) -> None:
        self._root = root
        self._repo_root = repo_root
        self._base_commit = base_commit
        self._git_version = git_version
        self._closed = False

    @classmethod
    def create(
        cls,
        *,
        patch: str | None = None,
        base_commit: str | None = None,
        base_ref: str | None = None,
        repo_root: Path | None = None,
    ) -> WorktreeCampaignWorkspace:
        """Create a throwaway worktree and optionally apply a patch on top."""
        resolved_root = repo_root or _find_repo_root()

        rev = _resolve_rev(resolved_root, base_commit=base_commit, base_ref=base_ref)

        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="maistro-rsi-wt-"))
        try:
            _run(
                ["git", "worktree", "add", "--detach", str(tmp), rev],
                cwd=resolved_root,
            )

            if patch and patch.strip():
                patch_path = tmp / ".maistro-candidate.patch"
                patch_path.write_text(patch, encoding="utf-8")
                try:
                    _run(
                        ["git", "apply", "--binary", "--whitespace=nowarn", str(patch_path)],
                        cwd=tmp,
                    )
                finally:
                    patch_path.unlink(missing_ok=True)

            resolved_commit = _run(["git", "rev-parse", "HEAD"], cwd=tmp).strip()
            git_version = _run(["git", "--version"]).strip()

            return cls(tmp, resolved_root, resolved_commit, git_version)
        except Exception:
            _prune_worktree(resolved_root, tmp)
            raise

    @property
    def base_commit(self) -> str:
        return self._base_commit

    @property
    def git_version(self) -> str:
        return self._git_version

    def read_file(self, path: str) -> str:
        self._require_open()
        return self._safe_path(path).read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> None:
        self._require_open()
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def delete_file(self, path: str) -> None:
        self._require_open()
        self._safe_path(path).unlink(missing_ok=True)

    def run_command_result(self, cmd: str, *, timeout: int = 30) -> ExecResult:
        import sys as _sys

        self._require_open()
        lowered = cmd.lower()
        for blocked in _BLOCKED:
            if blocked in lowered:
                raise ValueError(f"Blocked command in worktree mode: {blocked!r}")
        try:
            argv = shlex.split(cmd)
        except ValueError as exc:
            raise ValueError(f"Invalid command: {exc}") from exc
        # On Windows, 'python' in PATH may resolve to the Microsoft Store stub
        # rather than the active venv. Always use sys.executable for reliability.
        if argv and argv[0] in ("python", "python3"):
            argv[0] = _sys.executable
        started = _monotonic()
        result = subprocess.run(
            argv,
            cwd=self._root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=self._env(),
        )
        duration_ms = int((_monotonic() - started) * 1000)
        return ExecResult(result.returncode, result.stdout, result.stderr, duration_ms)

    def search(self, pattern: str, *, glob: str = "**/*.py") -> list[str]:
        self._require_open()
        return [
            str(p.relative_to(self._root))
            for p in self._root.glob(glob)
            if p.is_file() and ".git" not in p.parts
            and pattern in p.read_text(encoding="utf-8", errors="ignore")
        ]

    def list_files(self, *, glob: str = "**/*", limit: int = 2000) -> list[str]:
        self._require_open()
        results = []
        for p in self._root.glob(glob):
            if len(results) >= limit:
                break
            if p.is_file() and ".git" not in p.parts:
                results.append(str(p.relative_to(self._root)))
        return results

    def diff(self) -> str:
        self._require_open()
        subprocess.run(
            ["git", "add", "--intent-to-add", "--all", "--", "."],
            cwd=self._root,
            capture_output=True,
        )
        result = subprocess.run(
            [
                "git", "diff", "--binary", "--no-ext-diff", "--no-textconv",
                self._base_commit, "--",
            ],
            cwd=self._root,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _prune_worktree(self._repo_root, self._root)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("WorktreeCampaignWorkspace is closed")

    def _safe_path(self, path: str) -> Path:
        parsed = Path(path)
        if parsed.is_absolute() or ".." in parsed.parts or ".git" in parsed.parts:
            raise ValueError(f"Unsafe workspace path: {path!r}")
        return self._root / parsed

    # Packages whose source is part of the RSI harness, not the target under test.
    # Adding them to PYTHONPATH would shadow the installed versions and break imports
    # for benchmark and harness modules not yet committed to the worktree.
    _HARNESS_PACKAGES = frozenset({"maistro-rsi", "maistro-evolve", "maistro-registry"})

    def _env(self) -> dict[str, str]:
        import sys
        env = dict(os.environ)
        # Ensure commands resolve to the active Python (venv), not system stubs.
        venv_bin = str(Path(sys.executable).parent)
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
        # Add only target (non-harness) packages to PYTHONPATH so RSI-modified code
        # takes precedence over installed packages, while harness packages (locked_tests,
        # quarantine, experiment, etc.) come from installed site-packages.
        src_dirs = [
            str(p)
            for p in self._root.glob("packages/*/src")
            if p.is_dir() and p.parent.name not in self._HARNESS_PACKAGES
        ]
        if src_dirs:
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = os.pathsep.join(src_dirs + ([existing] if existing else []))
        return env


def _find_repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Not inside a git repository")
    return Path(result.stdout.strip())


def _resolve_rev(root: Path, *, base_commit: str | None, base_ref: str | None) -> str:
    if base_commit:
        return base_commit
    if base_ref:
        for candidate in (f"origin/{base_ref}", base_ref):
            result = subprocess.run(
                ["git", "rev-parse", "--verify", candidate],
                cwd=root,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        raise RuntimeError(f"Could not resolve base ref {base_ref!r}")
    return _run(["git", "rev-parse", "HEAD"], cwd=root).strip()


def _run(cmd: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed {cmd[0]!r}: {(result.stderr or result.stdout)[:500]}"
        )
    return result.stdout


def _prune_worktree(repo_root: Path, worktree_path: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo_root,
        capture_output=True,
    )
    shutil.rmtree(worktree_path, ignore_errors=True)


def _monotonic() -> float:
    import time
    return time.monotonic()
