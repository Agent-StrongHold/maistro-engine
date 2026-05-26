"""PM fleet helpers for Hive Conductor POC mode."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from maistro.agents.pm_fleet import (
    PM_FLEET,
    agent_status_for_user,
    build_task_description,
    fleet_card_dict,
    get_pm_def,
)
from models.schemas import Agent

_STATUS_TO_HIVE: dict[str, str] = {
    "idle": "idle",
    "running": "busy",
    "error": "error",
}


def is_pm_poc_mode() -> bool:
    return (
        os.getenv("MAISTRO_POC_MODE", os.getenv("HIVE_POC_MODE", "")).strip().lower() == "pm"
    )


def list_pm_agents(tasks: list[Any], *, user_id: str = "") -> list[Agent]:
    now = datetime.now(UTC)
    agents: list[Agent] = []
    for defn in PM_FLEET:
        raw_status = agent_status_for_user(defn, tasks)
        card = fleet_card_dict(defn, status=raw_status)
        agents.append(
            Agent(
                id=defn.name,
                name=defn.display_name,
                description=defn.tagline,
                tagline=defn.tagline,
                primary_capability=defn.primary_capability,
                primary_action_label=defn.primary_action_label,
                model="auto",
                status=_STATUS_TO_HIVE.get(raw_status, "idle"),  # type: ignore[arg-type]
                capabilities=card["capabilities"],
                skills=list(defn.capabilities),
                current_mission=None,
                tasks_completed=0,
                avg_response_time_ms=0.0,
                last_active=now,
                created_at=now,
                config={"user_id": user_id},
            )
        )
    return agents


def invoke_pm_agent(
    agent_id: str,
    capability: str,
    payload: dict[str, Any],
) -> tuple[str, str, str]:
    """Return (task_type, description, resolved_agent_id)."""
    defn = get_pm_def(agent_id)
    if defn is None:
        raise ValueError(f"Unknown PM agent: {agent_id}")
    task_type, description = build_task_description(agent_id, capability, payload)
    return task_type, description, defn.name
