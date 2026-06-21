from __future__ import annotations

from maistro.skills.parser import parse_skill_file
from maistro.types.skill import SkillDefinition


class ClaudeCodeSkillImporter:
    format = "claude_code_skill"

    def detect(self, source: dict[str, object] | str) -> bool:
        return isinstance(source, str) and source.startswith("---\n") and "description:" in source

    def to_skill_definitions(self, source: dict[str, object] | str) -> list[SkillDefinition]:
        if not isinstance(source, str):
            raise ValueError("Claude Code skill source must be SKILL.md text")
        skill = parse_skill_file(source, source="claude_code")
        if skill is None:
            raise ValueError("invalid Claude Code SKILL.md")
        return [skill]
