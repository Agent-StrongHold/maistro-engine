"""Agent loop for the builders interactive session."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maistro_bootstrap.builders.session import BuilderSession

logger = logging.getLogger(__name__)


@dataclass
class AgentLoopConfig:
    """Tunable parameters for the agent loop."""

    max_turns: int = 10
    max_tokens: int = 8192
    model: str = "claude-sonnet-4-6"
    system_prompt: str = (
        "You are a precise coding assistant working inside an isolated git worktree. "
        "Use the provided tools to read files, write changes, and run commands. "
        "Always confirm destructive actions before executing them. "
        "Never access paths outside the workspace root."
    )
    tool_definitions: list[dict[str, Any]] = field(default_factory=list)


def _make_sandbox_tools(session: BuilderSession) -> list[dict[str, Any]]:
    """Return Anthropic-format tool definitions that delegate to the sandbox."""
    return [
        {
            "name": "read_file",
            "description": "Read a file from the sandbox workspace.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative file path"}},
                "required": ["path"],
            },
        },
        {
            "name": "write_file",
            "description": "Write content to a file in the sandbox workspace.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "run_command",
            "description": "Run a shell command inside the sandbox (dangerous commands are blocked).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "timeout": {"type": "integer", "default": 30},
                },
                "required": ["cmd"],
            },
        },
        {
            "name": "diff",
            "description": "Return a git diff of all changes made so far in the sandbox.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "search",
            "description": "Search files in the workspace for a pattern.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "glob": {"type": "string", "default": "**/*.py"},
                },
                "required": ["pattern"],
            },
        },
    ]


def _dispatch_tool(session: BuilderSession, name: str, inputs: dict[str, Any]) -> str:
    sandbox = session.sandbox
    try:
        if name == "read_file":
            return sandbox.read_file(inputs["path"])
        if name == "write_file":
            sandbox.write_file(inputs["path"], inputs["content"])
            return f"wrote {inputs['path']}"
        if name == "run_command":
            return sandbox.run_command(inputs["cmd"], timeout=inputs.get("timeout", 30))
        if name == "diff":
            return sandbox.diff()
        if name == "search":
            matches = sandbox.search(inputs["pattern"], glob=inputs.get("glob", "**/*.py"))
            return json.dumps(matches)
    except Exception as exc:
        return f"[tool error] {exc}"
    return f"[unknown tool] {name}"


class TurnRunner:
    """Executes one agent turn: sends messages to the LLM, handles tool calls."""

    def __init__(self, session: BuilderSession, config: AgentLoopConfig) -> None:
        self._session = session
        self._config = config
        self._llm: Callable[..., dict[str, Any]] | None = None

    def set_llm(self, llm: Callable[..., dict[str, Any]]) -> None:
        self._llm = llm

    async def execute_turn(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if self._llm is None:
            return {"content": "(no LLM configured)", "stop_reason": "end_turn"}

        tools = _make_sandbox_tools(self._session)
        full_messages = list(messages)

        for _ in range(self._config.max_turns):
            result = self._llm(
                full_messages,
                tools=tools,
                max_tokens=self._config.max_tokens,
            )

            if result.get("stop_reason") != "tool_use":
                self._session.add_assistant(result.get("content", ""))
                return result

            # Tool use loop
            tool_results = []
            content = result.get("content", "")
            # content may be a list of blocks when tools fire
            blocks = content if isinstance(content, list) else []
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_out = _dispatch_tool(self._session, block["name"], block.get("input", {}))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": tool_out,
                        }
                    )
                    logger.debug("tool=%s result_len=%d", block["name"], len(tool_out))

            full_messages.append({"role": "assistant", "content": blocks})
            full_messages.append({"role": "user", "content": tool_results})

        return {"content": "(max turns reached)", "stop_reason": "max_turns"}
