"""Bounded controller-side model tool loop for offline candidate workspaces."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maistro_evolve.instruction_optimizer import evolve_instruction
from maistro_rsi.campaign import CandidateProposal, CandidateRequest, ProposalWorkspace

LlmCall = Callable[[str | list[dict[str, Any]]], Awaitable[str]]
_RESULT_LIMIT = 32 * 1024


@dataclass(frozen=True)
class ToolLoopPatchProvider:
    """Drive a model through explicit tools without giving it credentials or host access."""

    llm_call: LlmCall
    max_rounds: int = 40
    strategy_guidance: str = ""

    async def propose(
        self, workspace: ProposalWorkspace, request: CandidateRequest
    ) -> CandidateProposal:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _request_prompt(request, self.strategy_guidance)},
        ]
        transcript: list[dict[str, object]] = []
        for _ in range(self.max_rounds):
            raw = await self.llm_call(messages)
            action = _parse_action(raw)
            transcript.append({"model": raw, "action": action})
            name = str(action.get("action", ""))
            if name == "finish":
                return CandidateProposal(
                    summary=str(action.get("summary", "")),
                    provider_transcript=tuple(transcript),
                )
            result = _run_action(workspace, action)
            messages.extend(
                [
                    {"role": "assistant", "content": json.dumps(action, ensure_ascii=True)},
                    {
                        "role": "user",
                        "content": "Tool result:\n" + result[-_RESULT_LIMIT:],
                    },
                ]
            )
        raise RuntimeError(f"Candidate provider exceeded its {self.max_rounds}-round budget")


@dataclass(frozen=True)
class EvolvingToolLoopPatchProvider:
    """Persist and evolve candidate strategy while keeping capabilities immutable."""

    llm_call: LlmCall
    state_path: Path
    max_rounds: int = 40

    async def propose(
        self, workspace: ProposalWorkspace, request: CandidateRequest
    ) -> CandidateProposal:
        guidance = self._load_guidance()
        if request.prior_feedback is not None:
            guidance = await evolve_instruction(
                current_instruction=guidance,
                feedback=request.prior_feedback,
                llm_call=self.llm_call,
            )
            self._save_guidance(guidance)
        return await ToolLoopPatchProvider(
            self.llm_call,
            max_rounds=self.max_rounds,
            strategy_guidance=guidance,
        ).propose(workspace, request)

    def _load_guidance(self) -> str:
        if not self.state_path.is_file():
            return ""
        return self.state_path.read_text(encoding="utf-8")

    def _save_guidance(self, guidance: str) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.state_path.name}.", dir=self.state_path.parent
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(guidance)
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(self.state_path)
        finally:
            temp.unlink(missing_ok=True)


_SYSTEM_PROMPT = """You are improving a codebase inside an offline VM.
You have no host access, credentials, network, push, or PR capability.
Respond with exactly one JSON object per turn and no markdown.
Allowed actions:
{"action":"read_file","path":"relative/path"}
{"action":"write_file","path":"relative/path","content":"complete replacement content"}
{"action":"delete_file","path":"relative/path"}
{"action":"search","pattern":"literal text","glob":"**/*.py"}
{"action":"list_files","glob":"**/*","limit":2000}
{"action":"finish","summary":"what changed and why"}
Inspect before editing and keep changes scoped. Maistro will export the patch, then run the fixed
test and benchmark commands in separate fresh evaluation VMs after you finish.
Never alter tests merely to make a failure disappear. Never touch .git metadata."""


def _request_prompt(request: CandidateRequest, strategy_guidance: str) -> str:
    benchmark = (
        f"\nFixed benchmark command: {request.benchmark_command}"
        if request.benchmark_command is not None
        else ""
    )
    benchmark_output = (
        f"\nBaseline benchmark output:\n{request.baseline_benchmark.output[-8000:]}"
        if request.baseline_benchmark is not None
        else ""
    )
    prior_feedback = (
        f"\nEvidence from the previous rejected candidate:\n{request.prior_feedback}"
        if request.prior_feedback is not None
        else ""
    )
    strategy = f"\nEvolved candidate strategy:\n{strategy_guidance}" if strategy_guidance else ""
    return (
        f"Campaign: {request.campaign_id}\n"
        f"Iteration: {request.iteration}\n"
        f"Objective: {request.objective}\n"
        f"Fixed test command: {request.test_command}"
        f"{benchmark}\n"
        f"Baseline test output:\n{request.baseline_test.output[-8000:]}"
        f"{benchmark_output}"
        f"{prior_feedback}"
        f"{strategy}"
    )


def _parse_action(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Candidate provider returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Candidate provider action must be a JSON object")
    return parsed


def _run_action(workspace: ProposalWorkspace, action: dict[str, object]) -> str:
    name = str(action.get("action", ""))
    if name == "read_file":
        return workspace.read_file(_path(action))
    if name == "write_file":
        path = _path(action)
        if ".git" in path.replace("\\", "/").split("/"):
            raise ValueError("Candidate provider may not write Git metadata")
        content = action.get("content")
        if not isinstance(content, str):
            raise ValueError("write_file requires string content")
        workspace.write_file(path, content)
        return f"wrote {path}"
    if name == "delete_file":
        path = _path(action)
        workspace.delete_file(path)
        return f"deleted {path}"
    if name == "search":
        pattern = action.get("pattern")
        glob = action.get("glob", "**/*.py")
        if not isinstance(pattern, str) or not isinstance(glob, str):
            raise ValueError("search requires string pattern and glob")
        return "\n".join(workspace.search(pattern, glob=glob))
    if name == "list_files":
        glob = action.get("glob", "**/*")
        limit = action.get("limit", 2000)
        if not isinstance(glob, str) or not isinstance(limit, int):
            raise ValueError("list_files requires a string glob and integer limit")
        return "\n".join(workspace.list_files(glob=glob, limit=limit))
    raise ValueError(f"Unsupported candidate provider action: {name!r}")


def _path(action: dict[str, object]) -> str:
    path = action.get("path")
    if not isinstance(path, str):
        raise ValueError("Tool action requires a string path")
    if ".git" in path.replace("\\", "/").split("/"):
        raise ValueError("Candidate provider may not access Git metadata")
    return path
