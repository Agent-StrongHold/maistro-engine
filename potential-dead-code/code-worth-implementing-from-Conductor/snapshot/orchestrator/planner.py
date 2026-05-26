"""Planner agent — decomposes tasks into subtasks."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from orchestrator.gateway_client import GatewayClient
from orchestrator.utils import LLMParseError, parse_json_response

logger = logging.getLogger(__name__)


@dataclass
class Subtask:
    subtask_id: str
    description: str
    files_hint: list[str] = field(default_factory=list)
    estimated_complexity: str = "medium"  # trivial, simple, medium, complex, hard
    estimated_tokens: int = 2048
    feedback: list[str] = field(default_factory=list)

    def add_feedback(self, fb: str) -> None:
        self.feedback.append(fb)


@dataclass
class Plan:
    task_id: str
    original_request: str
    summary: str
    subtasks: list[Subtask]


class PlannerAgent:
    """Decomposes a user task into executable subtasks."""

    SYSTEM_PROMPT = """You are a task planner for an autonomous coding system.
Given a task description, break it into ordered subtasks.
Each subtask should be a single, well-scoped unit of work.

Respond with a JSON object:
{
  "summary": "brief plan summary",
  "subtasks": [
    {
      "description": "what to do",
      "files_hint": ["paths that might need changes"],
      "estimated_complexity": "trivial|simple|medium|complex|hard"
    }
  ]
}

If the task is simple enough to do in one step, return a single subtask.
Respond ONLY with valid JSON, no markdown fences."""

    def __init__(self, gateway: GatewayClient, layer0_content: str) -> None:
        self._gateway = gateway
        self._layer0 = layer0_content

    async def decompose(self, task: str) -> Plan:
        """Break a task into subtasks via the LLM."""
        task_id = uuid.uuid4().hex[:12]
        messages = [
            {"role": "system", "content": self._layer0 + "\n\n" + self.SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]

        result = await self._gateway.chat(messages, max_tokens=2048)

        try:
            data = parse_json_response(result.content)
        except LLMParseError:
            # Fallback: treat the whole task as a single subtask
            logger.warning("Could not parse plan JSON, using single-subtask fallback")
            data = {"summary": task[:100], "subtasks": [{"description": task}]}

        subtasks = []
        for i, st in enumerate(data.get("subtasks", [data])):
            subtasks.append(
                Subtask(
                    subtask_id=f"{task_id}-s{i}",
                    description=st.get("description", task),
                    files_hint=st.get("files_hint", []),
                    estimated_complexity=st.get("estimated_complexity", "medium"),
                )
            )

        plan = Plan(
            task_id=task_id,
            original_request=task,
            summary=data.get("summary", task[:100]),
            subtasks=subtasks,
        )
        logger.info("Plan %s: %d subtasks", task_id, len(subtasks))
        return plan
