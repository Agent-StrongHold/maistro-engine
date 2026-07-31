"""Program hyperagent API — interview, guidance, proactive fleet pulse.

The interview (GET /context, POST /interview/answer) resolves an optional
`workspace_id` query param to that workspace's own `ProgramContext` (keyed
by project_id) and persona-specific interview script (use_case) --
Persona/Workspace system. A user with two pm_fleet-persona workspaces (or a
pm_fleet workspace alongside a content_creator one) gets two independent
interviews instead of one shared global one. Omitting `workspace_id` --
every caller before this change, and any caller not yet workspace-aware --
keeps the exact pre-existing behavior: project_id="default",
use_case="pm_fleet". Guidance/pulse remain on the global "default" project;
scoping those to a workspace is out of scope here.
"""

from __future__ import annotations

import logging
from typing import Any

import stores
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from services import program_store as prog
from services.program_hyperagent import (
    apply_guidance_and_pulse,
    require_pm_poc,
    run_program_pulse,
    user_id_from_request,
)

from maistro.agents.hyperagent import interview_status
from maistro.agents.program_context import apply_interview_answer
from routes.audit import log_audit

router = APIRouter(tags=["program"])
logger = logging.getLogger("hive.program")


def _resolve_program_scope(user_id: str, workspace_id: str | None) -> tuple[str, str]:
    """Map an optional workspace_id to (project_id, use_case). Falls back to
    the pre-Phase-B default ("default", "pm_fleet") when no workspace_id is
    given, it doesn't resolve to a real workspace, or the requester isn't a
    member of it -- so a caller can never read/steer another workspace's
    interview scope by guessing an id it doesn't belong to."""
    if workspace_id:
        workspace = stores.workspaces.get(workspace_id)
        if workspace is not None and any(m.user_id == user_id for m in workspace.members):
            return workspace_id, workspace.persona_template_id
    return "default", "pm_fleet"


@router.get("/context")
@router.get("/cpntext")  # common typo alias
def get_program_context(request: Request, workspace_id: str | None = None) -> dict[str, Any]:
    require_pm_poc()
    uid = user_id_from_request(request)
    project_id, use_case = _resolve_program_scope(uid, workspace_id)
    ctx = prog.get_context(uid, project_id)
    return {
        "context": ctx.model_dump(mode="json"),
        "interview": interview_status(ctx, use_case=use_case),
    }


class InterviewAnswerBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: str = Field(min_length=1, max_length=4000)


@router.post("/interview/answer")
async def post_interview_answer(
    body: InterviewAnswerBody, request: Request, workspace_id: str | None = None
) -> dict[str, Any]:
    require_pm_poc()
    uid = user_id_from_request(request)
    project_id, use_case = _resolve_program_scope(uid, workspace_id)
    ctx = prog.get_context(uid, project_id)
    ctx = apply_interview_answer(ctx, body.answer, use_case=use_case)
    ctx = prog.save_context(ctx)
    log_audit(
        "program_interview", uid, detail={"step": ctx.interview_step, "workspace_id": workspace_id}
    )

    queued: list[dict[str, str]] = []
    if ctx.interview_complete:
        pulse_result = await run_program_pulse(uid, max_actions=2)
        queued = pulse_result.get("queued", [])

    return {
        "context": ctx.model_dump(mode="json"),
        "interview": interview_status(ctx, use_case=use_case),
        "queued_tasks": queued,
    }


class GuidanceBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1, max_length=8000)
    task_id: str | None = None


@router.post("/guidance")
async def post_guidance(body: GuidanceBody, request: Request) -> dict[str, Any]:
    """Human guidance for the meta hyperagent — learns and may trigger fleet work."""
    require_pm_poc()
    uid = user_id_from_request(request)
    log_audit("program_guidance", uid, target=body.task_id, detail={"chars": len(body.text)})
    result = await apply_guidance_and_pulse(uid, body.text.strip())
    return {"ok": True, "task_id": body.task_id, **result}


class PulseBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_actions: int = Field(default=3, ge=1, le=8)


@router.post("/pulse")
async def post_pulse(body: PulseBody, request: Request) -> dict[str, Any]:
    """Proactive fleet tick — queue autonomous agent work only."""
    require_pm_poc()
    uid = user_id_from_request(request)
    return await run_program_pulse(uid, max_actions=body.max_actions)
