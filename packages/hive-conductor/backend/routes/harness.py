"""HarnessRunner-shaped inbound route for external orchestrators (SPEC-208)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from services import engine as engine_service
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["harness"])
_HARNESS_SCOPE = "harness:session"
_sessions: dict[str, dict[str, str]] = {}


class StartSessionBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    agent_id: str = ""
    workdir: str = ""


class StartSessionResponse(BaseModel):
    session_id: str


class SendBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    messages: list[dict]
    intent_hint: str = ""


async def _require_harness_scope(x_maistro_scope: str = Header(default="")) -> None:
    scopes = {scope.strip() for scope in x_maistro_scope.replace(",", " ").split() if scope.strip()}
    if _HARNESS_SCOPE not in scopes:
        raise HTTPException(status_code=403, detail="harness:session scope required")


@router.post("/sessions", response_model=StartSessionResponse)
async def start_session(
    body: StartSessionBody,
    scope: Annotated[None, Depends(_require_harness_scope)] = None,
) -> StartSessionResponse:
    session_id = uuid4().hex
    _sessions[session_id] = {"agent_id": body.agent_id, "workdir": body.workdir}
    return StartSessionResponse(session_id=session_id)


@router.post("/sessions/{session_id}/send")
async def send(
    session_id: str,
    body: SendBody,
    scope: Annotated[None, Depends(_require_harness_scope)] = None,
) -> dict:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="session not found")
    return await engine_service.route_request(
        body.messages,
        session_id=session_id,
        intent_hint=body.intent_hint,
    )


@router.get("/sessions/{session_id}/stream")
async def stream(
    session_id: str,
    scope: Annotated[None, Depends(_require_harness_scope)] = None,
) -> EventSourceResponse:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="session not found")

    async def events() -> AsyncIterator[dict[str, str]]:
        yield {"event": "ready", "data": session_id}

    return EventSourceResponse(events())


@router.delete("/sessions/{session_id}", status_code=204)
async def stop(session_id: str, scope: Annotated[None, Depends(_require_harness_scope)] = None) -> None:
    _sessions.pop(session_id, None)
