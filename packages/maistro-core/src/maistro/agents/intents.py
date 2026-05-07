"""Intent registry: static routing table mapping task_type to agent_name."""

from __future__ import annotations


class IntentRegistry:
    """Maps task types to agent names."""

    def __init__(self, routing_table: dict[str, str] | None = None) -> None:
        self._table = routing_table or {
            "code": "artificer",
            "code_gen": "mason",
            "automation": "warden-at-arms",
            "search": "ranger",
            "creative": "scribe",
            "reasoning": "artificer",
        }

    def get_agent_for_intent(self, task_type: str) -> str | None:
        return self._table.get(task_type)

    def resolve(self, task_type: str) -> str:
        """Return agent name or 'artificer' as default."""
        return self._table.get(task_type, "artificer")

    def register(self, task_type: str, agent_name: str) -> None:
        self._table[task_type] = agent_name
