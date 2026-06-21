from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from maistro.types.config import AgentConfig


class AgentImporter(Protocol):
    format: str

    def detect(self, source: dict[str, object] | str) -> bool: ...

    def to_agent_config(self, source: dict[str, object] | str) -> AgentConfig: ...


@dataclass
class ImporterRegistry:
    importers: list[AgentImporter] = field(default_factory=list)

    def register(self, importer: AgentImporter) -> None:
        self.importers.append(importer)

    def import_agent(
        self,
        source: dict[str, object] | str,
        *,
        import_format: str | None = None,
    ) -> AgentConfig:
        for importer in self.importers:
            if import_format is not None and importer.format != import_format:
                continue
            if import_format is not None or importer.detect(source):
                return importer.to_agent_config(source)
        raise ValueError("no agent importer matched source")
