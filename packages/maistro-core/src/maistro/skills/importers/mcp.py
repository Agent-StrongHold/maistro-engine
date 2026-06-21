from __future__ import annotations

from typing import Any

from maistro.types.skill import SkillDefinition


class MCPSkillImporter:
    format = "mcp_manifest"

    def detect(self, source: dict[str, object] | str) -> bool:
        return isinstance(source, dict) and isinstance(source.get("tools"), list)

    def to_skill_definitions(self, source: dict[str, object] | str) -> list[SkillDefinition]:
        if not isinstance(source, dict):
            raise ValueError("MCP source must be a mapping")
        skills: list[SkillDefinition] = []
        raw_tools = source.get("tools")
        tools = raw_tools if isinstance(raw_tools, list) else []
        for raw_tool in tools:
            if not isinstance(raw_tool, dict):
                continue
            tool: dict[str, Any] = raw_tool
            name = str(tool.get("name", ""))
            description = str(tool.get("description", ""))
            schema: dict[str, Any] = (
                tool.get("inputSchema")
                if isinstance(tool.get("inputSchema"), dict)
                else {"type": "object", "properties": {}}
            )
            if name and description:
                skills.append(SkillDefinition(name=name, description=description, parameters=schema, source="mcp_manifest"))
        if not skills:
            raise ValueError("MCP manifest contained no importable tools")
        return skills
