from __future__ import annotations

from typing import Any

from maistro.types.config import AgentConfig


class PiAgentImporter:
    format = "pi"

    def detect(self, source: dict[str, object] | str) -> bool:
        return isinstance(source, dict) and (source.get("format") == "pi" or "pi_agent" in source)

    def to_agent_config(self, source: dict[str, object] | str) -> AgentConfig:
        if not isinstance(source, dict):
            raise ValueError("Pi agent source must be a mapping")
        payload: dict[str, Any] = dict(source.get("pi_agent") if isinstance(source.get("pi_agent"), dict) else source)
        models = payload.get("models") if isinstance(payload.get("models"), dict) else {}
        providers = payload.get("providers") if isinstance(payload.get("providers"), dict) else {}
        return AgentConfig(
            providers=providers,
            models=models,
            harness_runner="pi",
            harness_format=self.format,
            agents_dir=str(payload.get("agents_dir", "")),
        )
