"""Coder agent — generates code implementations via Ultra Think."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from orchestrator.gateway_client import GatewayClient
from orchestrator.planner import Subtask

logger = logging.getLogger(__name__)


@dataclass
class FileOperation:
    action: str  # CREATE, MODIFY, DELETE
    path: str
    content: str = ""


@dataclass
class CoderCandidate:
    candidate_id: str
    content: str
    file_ops: list[FileOperation] = field(default_factory=list)
    tokens_generated: int = 0
    generation_time_ms: float = 0.0


class CoderAgent:
    """Generates code implementations for subtasks."""

    SYSTEM_PROMPT = """You are a code generator for an autonomous coding system.

Given a subtask description, produce a solution as a sequence of file operations.
For each file:
1. State the file path
2. State whether it's CREATE, MODIFY, or DELETE
3. For CREATE/MODIFY: provide the complete file content

Use this format for each file (can have multiple):
<<<FILE: path/to/file.ext
ACTION: CREATE|MODIFY|DELETE
CONTENT:
... full file content here ...
>>>

Do not add explanations unless the task asks for documentation.
Be complete — provide full file contents, not diffs or partial snippets."""

    def __init__(
        self,
        gateway: GatewayClient,
        project_id: str,
        layer0_content: str,
        layer1_content: str,
    ) -> None:
        self._gateway = gateway
        self._project_id = project_id
        self._layer0 = layer0_content
        self._layer1 = layer1_content

    async def generate(
        self,
        subtask: Subtask,
        tier: int = 2,
        attempt: int = 0,
    ) -> list[CoderCandidate]:
        """Generate candidate implementations via Ultra Think."""
        # Build the prompt
        feedback_section = ""
        if subtask.feedback:
            feedback_section = "\n\n## Previous Attempts Feedback\n" + "\n".join(subtask.feedback)

        user_content = f"""## Task
{subtask.description}

## Relevant Files (hints)
{", ".join(subtask.files_hint) or "none provided"}
{feedback_section}"""

        messages = [
            {
                "role": "system",
                "content": self._layer0 + "\n\n" + self._layer1 + "\n\n" + self.SYSTEM_PROMPT,
            },
            {"role": "user", "content": user_content},
        ]

        result = await self._gateway.ultra_think(
            task_id=subtask.subtask_id,
            messages=messages,
            project_id=self._project_id,
            tier=tier,
            max_tokens=subtask.estimated_tokens,
        )

        candidates = []
        for c in result.get("candidates", []):
            file_ops = self._parse_file_ops(c.get("content", ""))
            candidates.append(
                CoderCandidate(
                    candidate_id=c.get("candidate_id", ""),
                    content=c.get("content", ""),
                    file_ops=file_ops,
                    tokens_generated=c.get("tokens_generated", 0),
                    generation_time_ms=c.get("generation_time_ms", 0),
                )
            )

        logger.info(
            "Coder generated %d candidates for %s (tier %d, attempt %d)",
            len(candidates),
            subtask.subtask_id,
            tier,
            attempt,
        )
        return candidates

    @staticmethod
    def _parse_file_ops(content: str) -> list[FileOperation]:
        """Extract file operations from the coder's response."""
        pattern = r"<<<FILE:\s*(.+?)\nACTION:\s*(CREATE|MODIFY|DELETE)\nCONTENT:\n(.*?)>>>"
        matches = re.findall(pattern, content, re.DOTALL)
        ops = []
        for path, action, file_content in matches:
            ops.append(
                FileOperation(
                    action=action.strip(),
                    path=path.strip(),
                    content=file_content.strip(),
                )
            )
        return ops
