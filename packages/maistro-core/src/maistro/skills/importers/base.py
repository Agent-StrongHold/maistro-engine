from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from maistro.types.skill import SkillDefinition


class SkillImporter(Protocol):
    format: str

    def detect(self, source: dict[str, object] | str) -> bool: ...

    def to_skill_definitions(self, source: dict[str, object] | str) -> list[SkillDefinition]: ...


@dataclass
class ImporterRegistry:
    importers: list[SkillImporter] = field(default_factory=list)

    def register(self, importer: SkillImporter) -> None:
        self.importers.append(importer)

    def import_skills(
        self,
        source: dict[str, object] | str,
        *,
        import_format: str | None = None,
    ) -> list[SkillDefinition]:
        for importer in self.importers:
            if import_format is not None and importer.format != import_format:
                continue
            if import_format is not None or importer.detect(source):
                return importer.to_skill_definitions(source)
        raise ValueError("no skill importer matched source")
