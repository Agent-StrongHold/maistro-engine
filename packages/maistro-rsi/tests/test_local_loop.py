"""Tests for the safe, capped, local self-improvement loop.

These exercise the ratchet logic with *stub* apply-patch callables (no LLM, no
gateway), so they're fast and deterministic: a promotion happens iff the cycle
both changed something and the test command passed, and each promotion advances
the baseline the next cycle builds on.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import ClassVar

import pytest

import maistro_rsi.local_loop as local_loop
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

    async def apply(sandbox: MicroVmSandbox, workspace: str, model: str | None = None) -> None:
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


class _FakeResponsesCallable:
    """Stands in for ResponsesAPICallable: records the model it was built with
    and immediately ends the turn."""

    built_models: ClassVar[list] = []

    def __init__(
        self,
        *,
        model=None,
        temperature=None,
        reasoning_effort=None,
        timeout=None,
        prompt_cache=False,
    ):
        type(self).built_models.append(model)

    def __call__(self, messages, *, tools=None, max_tokens=None):
        return {"content": "done", "stop_reason": "end_turn"}


@pytest.mark.asyncio
async def test_apply_patch_cycle_model_used_when_factory_model_unset(tmp_path, monkeypatch):
    """ApplyPatchFn's third arg (the quota-burn scheduler's per-cycle pick)
    reaches the builders LLM wiring when no explicit factory model was given."""
    import maistro_bootstrap.builders.responses_callable as rc

    _FakeResponsesCallable.built_models = []
    monkeypatch.setattr(rc, "ResponsesAPICallable", _FakeResponsesCallable)

    apply_fn = local_loop.make_builders_apply_patch("do a thing")
    await apply_fn(None, str(tmp_path), "groq/kimi-k2")

    assert _FakeResponsesCallable.built_models == ["groq/kimi-k2"]


@pytest.mark.asyncio
async def test_apply_patch_factory_model_beats_cycle_model(tmp_path, monkeypatch):
    """An explicit factory model (e.g. the CLI's --model) is a hard override."""
    import maistro_bootstrap.builders.responses_callable as rc

    _FakeResponsesCallable.built_models = []
    monkeypatch.setattr(rc, "ResponsesAPICallable", _FakeResponsesCallable)

    apply_fn = local_loop.make_builders_apply_patch("do a thing", model="cli-override")
    await apply_fn(None, str(tmp_path), "groq/kimi-k2")

    assert _FakeResponsesCallable.built_models == ["cli-override"]


# ---------------------------------------------------------------------------
# Inner tool-budget exhaustion: resume with context, never echo the sentinel
# ---------------------------------------------------------------------------


def test_resume_transcript_only_on_max_turns_with_transcript() -> None:
    transcript = [{"role": "user", "content": "task"}]
    # The one continue case: budget stop with a transcript to resume from.
    resumed = local_loop._resume_transcript({"stop_reason": "max_turns", "messages": transcript})
    assert resumed == transcript
    assert resumed is not transcript  # a copy — caller may mutate freely
    # The agent chose to finish: done, whatever else the result carries.
    assert local_loop._resume_transcript({"stop_reason": "stop", "messages": transcript}) is None
    # Budget stop but no transcript handed back (injected fakes, older
    # runners): ending the cycle beats poisoning the context.
    assert local_loop._resume_transcript({"stop_reason": "max_turns"}) is None
    assert local_loop._resume_transcript({"stop_reason": "max_turns", "messages": []}) is None


class _ToolHungryResponsesCallable:
    """Fake LLM whose model always wants another tool call: every execute_turn
    exhausts TurnRunner's inner budget, so the outer loop must keep resuming."""

    calls: ClassVar[list[list[dict]]] = []

    def __init__(self, **kwargs):
        pass

    def __call__(self, messages, *, tools=None, max_tokens=None):
        type(self).calls.append([dict(m) for m in messages])
        n = len(type(self).calls)
        return {
            "content": [{"type": "tool_use", "id": f"t{n}", "name": "no_such_tool", "input": {}}],
            "stop_reason": "tool_use",
        }


@pytest.mark.asyncio
async def test_exhausted_tool_budget_resumes_with_transcript_not_sentinel(tmp_path, monkeypatch):
    """The live failure this pins: TurnRunner's "(max turns reached)" sentinel
    was echoed back as the agent's own words, so the model believed it had
    announced running out of turns and quit — every cycle logged "agent made
    no change". The next turn must instead RESUME from the real transcript."""
    import maistro_bootstrap.builders.responses_callable as rc

    _ToolHungryResponsesCallable.calls = []
    monkeypatch.setattr(rc, "ResponsesAPICallable", _ToolHungryResponsesCallable)

    apply_fn = local_loop.make_builders_apply_patch("do a thing", max_agent_turns=2)
    await apply_fn(None, str(tmp_path), "some-model")

    from maistro_bootstrap.builders.agent_loop import AgentLoopConfig

    calls = _ToolHungryResponsesCallable.calls
    # Two outer turns, each spending the full inner budget — the run kept
    # working instead of quitting early.
    inner_budget = AgentLoopConfig().max_turns
    assert len(calls) == 2 * inner_budget

    # THE invariant: the internal sentinel never reaches the model as speech.
    for call in calls:
        for message in call:
            assert "(max turns reached)" not in str(message.get("content"))

    # Outer turn 2 resumed from the FULL transcript: seed (system + task) plus
    # one assistant/tool_result pair per inner turn — not a 4-message reset
    # around a sentinel.
    resume_call = calls[inner_budget]
    assert len(resume_call) == 2 + 2 * inner_budget
    assert resume_call[0]["role"] == "system"
    assert resume_call[-1]["role"] == "user"  # unanswered tool results
    assert resume_call[-1]["content"][0]["type"] == "tool_result"
