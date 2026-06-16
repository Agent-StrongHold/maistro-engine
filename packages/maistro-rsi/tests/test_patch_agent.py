from __future__ import annotations

import json
from pathlib import Path

import pytest

from maistro_rsi.campaign import CandidateRequest
from maistro_rsi.experiment import CommandMeasurement
from maistro_rsi.patch_agent import EvolvingToolLoopPatchProvider, ToolLoopPatchProvider


class FakeWorkspace:
    def __init__(self) -> None:
        self.content = "old"

    def read_file(self, path: str) -> str:
        return self.content

    def write_file(self, path: str, content: str) -> None:
        self.content = content

    def delete_file(self, path: str) -> None:
        self.content = ""

    def search(self, pattern: str, *, glob: str = "**/*.py") -> list[str]:
        return ["target.py"]

    def list_files(self, *, glob: str = "**/*", limit: int = 2000) -> list[str]:
        return ["target.py"]

    def diff(self) -> str:
        return "diff --git a/target.py b/target.py\n" if self.content == "new" else ""

    def close(self) -> None:
        pass

    @property
    def base_commit(self) -> str:
        return "a" * 40


def _request() -> CandidateRequest:
    baseline = CommandMeasurement("baseline", "pytest -q", 1, 1.0, "failed", "now")
    return CandidateRequest("campaign", 1, "fix it", "pytest -q", None, baseline, None, None)


@pytest.mark.asyncio
async def test_tool_loop_exports_workspace_diff_without_remote_git_tools() -> None:
    responses = iter(
        [
            json.dumps({"action": "write_file", "path": "target.py", "content": "new"}),
            json.dumps({"action": "finish", "summary": "fixed target"}),
        ]
    )

    async def llm_call(messages: str | list[dict[str, object]]) -> str:
        return next(responses)

    proposal = await ToolLoopPatchProvider(llm_call).propose(FakeWorkspace(), _request())

    assert proposal.summary == "fixed target"
    assert not hasattr(FakeWorkspace(), "run_command_result")


@pytest.mark.asyncio
async def test_tool_loop_rejects_git_metadata_write() -> None:
    async def llm_call(messages: str | list[dict[str, object]]) -> str:
        return json.dumps({"action": "write_file", "path": ".git/config", "content": "bad"})

    with pytest.raises(ValueError, match="Git metadata"):
        await ToolLoopPatchProvider(llm_call).propose(FakeWorkspace(), _request())


@pytest.mark.asyncio
async def test_evolving_tool_loop_persists_strategy_between_trials(tmp_path: Path) -> None:
    responses = iter(
        [
            "Inspect the failing parser before changing it.",
            json.dumps({"action": "write_file", "path": "target.py", "content": "new"}),
            json.dumps({"action": "finish", "summary": "fixed target"}),
        ]
    )

    async def llm_call(messages: str | list[dict[str, object]]) -> str:
        return next(responses)

    request = _request()
    request = CandidateRequest(
        request.campaign_id,
        request.iteration,
        request.objective,
        request.test_command,
        request.benchmark_command,
        request.baseline_test,
        request.baseline_benchmark,
        "Prior candidate failed parser tests.",
    )
    state_path = tmp_path / "evolved-strategy.txt"
    proposal = await EvolvingToolLoopPatchProvider(llm_call, state_path).propose(
        FakeWorkspace(), request
    )

    assert proposal.summary == "fixed target"
    assert state_path.read_text(encoding="utf-8").startswith("Inspect the failing parser")
