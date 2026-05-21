from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import stores
from fastapi import APIRouter, HTTPException
from models.schemas import Agent
from pydantic import BaseModel, ConfigDict

from routes.audit import log_audit

router = APIRouter(tags=["agents"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=list[Agent])
def list_agents() -> list[Agent]:
    return list(stores.agents.values())


@router.get("/{agent_id}", response_model=Agent)
def get_agent(agent_id: str) -> Agent:
    if agent_id not in stores.agents:
        raise HTTPException(status_code=404, detail="agent not found")
    return stores.agents[agent_id]


class CreateAgentBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    model: str = "gpt-4.1"
    capabilities: list[str] = []
    skills: list[str] = []
    config: dict = {}


@router.post("", response_model=Agent, status_code=201)
def create_agent(body: CreateAgentBody) -> Agent:
    aid = str(uuid4())
    t = _now()
    agent = Agent(
        id=aid,
        name=body.name,
        description=body.description,
        model=body.model,
        status="idle",
        capabilities=body.capabilities,
        skills=body.skills,
        current_mission=None,
        tasks_completed=0,
        avg_response_time_ms=0.0,
        last_active=t,
        created_at=t,
        config=body.config,
    )
    stores.agents[aid] = agent
    log_audit("agent_create", "system", target=aid, detail={"name": body.name})
    return agent


class UpdateAgentBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    description: str | None = None
    model: str | None = None
    capabilities: list[str] | None = None
    skills: list[str] | None = None
    config: dict | None = None
    status: str | None = None


@router.put("/{agent_id}", response_model=Agent)
def update_agent(agent_id: str, body: UpdateAgentBody) -> Agent:
    if agent_id not in stores.agents:
        raise HTTPException(status_code=404, detail="agent not found")
    agent = stores.agents[agent_id]
    updates = body.model_dump(exclude_none=True)
    agent = agent.model_copy(update=updates)
    stores.agents[agent_id] = agent
    log_audit("agent_update", "system", target=agent_id, detail=updates)
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str) -> None:
    if agent_id not in stores.agents:
        raise HTTPException(status_code=404, detail="agent not found")
    stores.agents.pop(agent_id)
    log_audit("agent_delete", "system", target=agent_id)


@router.post("/{agent_id}/scan")
def scan_agent(agent_id: str) -> dict:
    if agent_id not in stores.agents:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"findings": [], "status": "clean"}


class ForgeAgentBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str
    strategy: str = "react"
    model: str = "gpt-4.1"


@router.post("/forge", response_model=Agent)
def forge_agent(body: ForgeAgentBody) -> Agent:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    aid = str(uuid4())
    t = _now()
    agent = Agent(
        id=aid,
        name=f"forge-{suffix}",
        description=body.description,
        model=body.model,
        status="idle",
        capabilities=[],
        skills=[],
        current_mission=None,
        tasks_completed=0,
        avg_response_time_ms=0.0,
        last_active=t,
        created_at=t,
        config={"strategy": body.strategy, "role": "worker"},
    )
    stores.agents[aid] = agent
    return agent
