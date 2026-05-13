from __future__ import annotations

from fastapi import APIRouter, HTTPException

from models.schemas import Agent

import stores

router = APIRouter(tags=["agents"])


@router.get("", response_model=list[Agent])
def list_agents() -> list[Agent]:
    return list(stores.agents.values())


@router.get("/{agent_id}", response_model=Agent)
def get_agent(agent_id: str) -> Agent:
    if agent_id not in stores.agents:
        raise HTTPException(status_code=404, detail="agent not found")
    return stores.agents[agent_id]
