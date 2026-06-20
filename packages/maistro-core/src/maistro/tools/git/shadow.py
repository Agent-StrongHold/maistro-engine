"""Shadow git workspace for atomic agent-edit rollback (SPEC-254 / ADR-049)."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "maistro-shadow",
    "GIT_AUTHOR_EMAIL": "shadow@maistro.local",
    "GIT_COMMITTER_NAME": "maistro-shadow",
    "GIT_COMMITTER_EMAIL": "shadow@maistro.local",
}


def _run(args: list[str], cwd: Path) -> str:
    import os

    env = {**os.environ, **_GIT_ENV}
    result = subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    )
    return result.stdout


@dataclass(frozen=True)
class PrCandidate:
    branch: str
    base: str
    squashed_diff: str
    files_changed: list[str]


@dataclass
class ShadowGitWorkspace:
    workspace_ref: Path
    base_sha: str

    def commit_edit(self, files: dict[str, str], message: str) -> str:
        for rel_path, content in files.items():
            full_path = self.workspace_ref / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            _run(["add", rel_path], cwd=self.workspace_ref)
        _run(["commit", "-m", message], cwd=self.workspace_ref)
        return _run(["rev-parse", "HEAD"], cwd=self.workspace_ref).strip()

    def diff_against_base(self) -> str:
        return _run(["diff", self.base_sha, "HEAD"], cwd=self.workspace_ref)

    def produce_pr_candidate(self, base: str, branch: str) -> PrCandidate:
        _run(["branch", branch], cwd=self.workspace_ref)
        squashed_diff = _run(["diff", f"{base}..HEAD"], cwd=self.workspace_ref)
        files_changed_raw = _run(["diff", "--name-only", f"{base}..HEAD"], cwd=self.workspace_ref)
        files_changed = [line for line in files_changed_raw.splitlines() if line]
        return PrCandidate(
            branch=branch, base=base, squashed_diff=squashed_diff, files_changed=files_changed
        )

    def discard(self) -> None:
        shutil.rmtree(self.workspace_ref, ignore_errors=True)


def create_shadow_workspace(root: Path, task_id: str) -> ShadowGitWorkspace:
    workspace_ref = root / task_id
    workspace_ref.mkdir(parents=True, exist_ok=True)
    _run(["init"], cwd=workspace_ref)
    _run(["commit", "--allow-empty", "-m", "shadow workspace base"], cwd=workspace_ref)
    base_sha = _run(["rev-parse", "HEAD"], cwd=workspace_ref).strip()
    return ShadowGitWorkspace(workspace_ref=workspace_ref, base_sha=base_sha)
