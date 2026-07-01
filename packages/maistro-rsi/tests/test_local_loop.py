"""Tests for the safe, capped, local self-improvement loop.

These exercise the ratchet logic with *stub* apply-patch callables (no LLM, no
gateway), so they're fast and deterministic: a promotion happens iff the cycle
both changed something and the test command passed, and each promotion advances
the baseline the next cycle builds on.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from maistro_rsi.local_loop import LocalRsiConfig, LocalRsiLoop
from maistro_rsi.protocols import MicroVmSandbox


def _git(cwd: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-c", "core.longpaths=true", *args], cwd=str(cwd), capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} rc={proc.returncode}: {proc.stderr.strip()}")


def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "rsi@test.local")
    _git(path, "config", "user.name", "RSI Test")
    (path / "value.txt").write_text("0\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _make_apply(writer) -> object:
    """Wrap a sync ``writer(workspace: Path)`` as an async ApplyPatchFn."""

    async def apply(sandbox: MicroVmSandbox, workspace: str) -> None:
        writer(Path(workspace))

    return apply


def test_green_change_promotes_and_ratchets(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "src")

    # Each cycle appends a line — always a real change, always "healthy".
    def bump(ws: Path) -> None:
        f = ws / "value.txt"
        f.write_text(f.read_text() + "x\n", encoding="utf-8")

    config = LocalRsiConfig(
        repo_path=str(repo),
        test_command="exit 0",
        work_root=str(tmp_path / "work"),
        max_cycles=3,
    )
    result = LocalRsiLoop(config, apply_patch=_make_apply(bump)).run()

    assert result.promotions == 3
    assert all(c.promoted for c in result.cycles)
    # Ratchet: the baseline accumulated one commit per promoted cycle.
    baseline = Path(config.work_root) / "baseline"
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(baseline), capture_output=True, text=True, check=True
    )
    # init + 3 RSI commits
    assert len(log.stdout.strip().splitlines()) == 4


def test_no_change_is_not_promoted(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "src")
    config = LocalRsiConfig(
        repo_path=str(repo),
        test_command="exit 0",
        work_root=str(tmp_path / "work"),
        max_cycles=2,
    )
    result = LocalRsiLoop(config, apply_patch=_make_apply(lambda ws: None)).run()

    assert result.promotions == 0
    assert all(not c.changed and not c.promoted for c in result.cycles)


def test_failing_tests_block_promotion(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "src")

    def bump(ws: Path) -> None:
        (ws / "value.txt").write_text("broken\n", encoding="utf-8")

    config = LocalRsiConfig(
        repo_path=str(repo),
        test_command="exit 1",  # never healthy
        work_root=str(tmp_path / "work"),
        max_cycles=2,
    )
    result = LocalRsiLoop(config, apply_patch=_make_apply(bump)).run()

    assert result.promotions == 0
    assert all(c.changed and not c.tests_passed and not c.promoted for c in result.cycles)


def test_respects_cycle_cap(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "src")
    config = LocalRsiConfig(
        repo_path=str(repo),
        test_command="exit 0",
        work_root=str(tmp_path / "work"),
        max_cycles=5,
    )
    result = LocalRsiLoop(config, apply_patch=_make_apply(lambda ws: None)).run()
    assert len(result.cycles) == 5


def test_source_repo_untouched(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "src")
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()

    def bump(ws: Path) -> None:
        (ws / "value.txt").write_text("changed\n", encoding="utf-8")

    config = LocalRsiConfig(
        repo_path=str(repo),
        test_command="exit 0",
        work_root=str(tmp_path / "work"),
        max_cycles=2,
    )
    LocalRsiLoop(config, apply_patch=_make_apply(bump)).run()

    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()
    branches = subprocess.run(
        ["git", "branch"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout
    assert head_after == head_before  # never committed to source
    assert "rsi" not in branches  # never branched the source
