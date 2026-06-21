"""Single export path for maistro agents (SPEC-208)."""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from maistro.types.config import AgentConfig
from maistro.types.skill import SkillDefinition

MCP_MANIFEST_VERSION = "2025-06-18"


@dataclass(frozen=True)
class ExportBundle:
    mcp_manifest: dict[str, object]
    skill_md: str


def export_agent(agent: AgentConfig, skills: list[SkillDefinition]) -> ExportBundle:
    """Export an agent as an MCP manifest plus a parseable SKILL.md descriptor."""

    tools = [
        {
            "name": skill.name,
            "description": skill.description,
            "inputSchema": skill.parameters,
        }
        for skill in skills
    ]
    manifest: dict[str, object] = {
        "schemaVersion": MCP_MANIFEST_VERSION,
        "name": "maistro-agent",
        "description": "Exported maistro agent skills as MCP tools.",
        "harness": agent.harness_runner or "native",
        "tools": tools,
    }
    primary = skills[0] if skills else None
    skill_name = _safe_skill_name(primary.name if primary else "maistro_agent")
    frontmatter = {
        "name": skill_name,
        "description": "Exported maistro agent bundle",
        "groups": ["maistro", "export"],
        "parameters": {"type": "object", "properties": {}},
        "trust_tier": "t2",
    }
    body = [
        "# Exported maistro agent",
        "",
        f"Harness: `{agent.harness_runner or 'native'}`.",
        "",
        "## Exported MCP tools",
    ]
    body.extend(f"- `{tool['name']}`: {tool['description']}" for tool in tools)
    skill_md = f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n" + "\n".join(body) + "\n"
    return ExportBundle(mcp_manifest=manifest, skill_md=skill_md)


def _safe_skill_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"skill_{cleaned}" if cleaned else "maistro_agent"
    return cleaned[:51]
