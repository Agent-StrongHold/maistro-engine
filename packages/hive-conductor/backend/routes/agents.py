from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import stores

logger = logging.getLogger("hive.agents")
from fastapi import APIRouter, HTTPException, Request
from models.schemas import Agent
from pydantic import BaseModel, ConfigDict

from maistro.agents.pm_capabilities import CAPABILITY_TO_WORK_ITEM, is_gated

from routes.audit import log_audit
from services.engine import get_engine
from services.pm_fleet import invoke_pm_agent, is_pm_poc_mode, list_pm_agents

router = APIRouter(tags=["agents"])


def _now() -> datetime:
    return datetime.now(UTC)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    return str(user.get("id") or user.get("username") or "dev")


def _build_invoke_context(user_id: str) -> dict[str, Any]:
    """Build program_context with credentials for agent invocation."""
    from services import program_store as prog, user_credentials as cred_svc
    try:
        from maistro.agents.program_context import context_for_task
        ctx = prog.get_context(user_id)
        pctx = context_for_task(ctx)
    except Exception:
        pctx = {}
    # Inject Atlassian PATs
    store = cred_svc.get_credential_store()
    if store:
        pats: dict[str, str | None] = {}
        for pid, key in [("atlassian_server_jira", "jira"), ("confluence", "confluence")]:
            try:
                if store.has_secret(user_id, pid):
                    pats[key] = store.use_secret(user_id, pid, lambda s: s)
            except Exception:
                pass
        if pats:
            pctx["atlassian_pats"] = pats
    return pctx


@router.get("", response_model=list[Agent])
def list_agents(request: Request) -> list[Agent]:
    if is_pm_poc_mode():
        engine = get_engine()
        uid = _user_id(request)
        raw_tasks = []
        if engine._queue is not None:
            items, _ = engine._queue.list_tasks(limit=200, user_id=uid)
            raw_tasks = items
        return list_pm_agents(raw_tasks, user_id=uid)
    return list(stores.agents.values())


@router.get("/{agent_id}", response_model=Agent)
def get_agent(agent_id: str, request: Request) -> Agent:
    if is_pm_poc_mode():
        for agent in list_agents(request):
            if agent.id == agent_id:
                return agent
        raise HTTPException(status_code=404, detail="agent not found")
    if agent_id not in stores.agents:
        raise HTTPException(status_code=404, detail="agent not found")
    return stores.agents[agent_id]


class InvokeBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    capability: str
    payload: dict[str, Any] = {}


@router.post("/{agent_id}/invoke")
async def invoke_agent(agent_id: str, body: InvokeBody, request: Request) -> dict[str, Any]:
    if not is_pm_poc_mode():
        raise HTTPException(status_code=404, detail="Agent invoke only available in PM POC mode")
    if is_gated(body.capability):
        work_type = CAPABILITY_TO_WORK_ITEM.get(body.capability, "work item")
        raise HTTPException(
            status_code=403,
            detail=(
                f"Capability '{body.capability}' posts to Jira. "
                f"Use POST /v1/work-items/suggest with work_type '{work_type}' "
                "— clarify, edit, then confirm."
            ),
        )
    uid = _user_id(request)
    # Execute directly via the same tool execution the chat uses — real data, no queue
    from services.chat_completion import _execute_tool
    result = await _execute_tool(body.capability, body.payload, uid)
    log_audit(
        "agent_invoke",
        uid,
        target=agent_id,
        detail={"capability": body.capability, "result_keys": list(result.keys()) if isinstance(result, dict) else []},
    )
    return {"status": "completed", "capability": body.capability, "result": result}


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
    if is_pm_poc_mode():
        raise HTTPException(status_code=403, detail="PM fleet is read-only in POC mode")
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
    if is_pm_poc_mode():
        raise HTTPException(status_code=403, detail="PM fleet is read-only in POC mode")
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
    if is_pm_poc_mode():
        raise HTTPException(status_code=403, detail="PM fleet is read-only in POC mode")
    if agent_id not in stores.agents:
        raise HTTPException(status_code=404, detail="agent not found")
    stores.agents.pop(agent_id)
    log_audit("agent_delete", "system", target=agent_id)


@router.post("/{agent_id}/scan")
def scan_agent(agent_id: str) -> dict:
    if is_pm_poc_mode():
        from maistro.agents.pm_fleet import get_pm_def

        if get_pm_def(agent_id) is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return {"findings": [], "status": "clean"}
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
    if is_pm_poc_mode():
        raise HTTPException(status_code=403, detail="PM fleet is read-only in POC mode")
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=6))  # nosec B311 — display-only id suffix; UUID4 is the actual identity
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
