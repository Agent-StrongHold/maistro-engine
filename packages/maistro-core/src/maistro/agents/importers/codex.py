from __future__ import annotations

from maistro.types.config import AgentConfig


class CodexAgentImporter:
    format = "codex"

    def detect(self, source: dict[str, object] | str) -> bool:
        if isinstance(source, str):
            return "AGENTS.md" in source or "<INSTRUCTIONS>" in source
        return source.get("format") == "codex"

    def to_agent_config(self, source: dict[str, object] | str) -> AgentConfig:
        agents_dir = ""
        if isinstance(source, dict):
            agents_dir = str(source.get("agents_dir", ""))
        return AgentConfig(harness_runner="codex", harness_format=self.format, agents_dir=agents_dir)
