"""Program hyperagent API — interview, guidance, proactive fleet pulse."""

from __future__ import annotations

import logging
from typing import Any

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


@router.get("/context")
@router.get("/cpntext")  # common typo alias
def get_program_context(request: Request) -> dict[str, Any]:
    require_pm_poc()
    uid = user_id_from_request(request)
    ctx = prog.get_context(uid)
    return {
        "context": ctx.model_dump(mode="json"),
        "interview": interview_status(ctx),
    }


class InterviewAnswerBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: str = Field(min_length=1, max_length=4000)


@router.post("/interview/answer")
async def post_interview_answer(body: InterviewAnswerBody, request: Request) -> dict[str, Any]:
    require_pm_poc()
    uid = user_id_from_request(request)
    ctx = prog.get_context(uid)
    ctx = apply_interview_answer(ctx, body.answer)
    ctx = prog.save_context(ctx)
    log_audit("program_interview", uid, detail={"step": ctx.interview_step})

    queued: list[dict[str, str]] = []
    if ctx.interview_complete:
        pulse_result = await run_program_pulse(uid, max_actions=2)
        queued = pulse_result.get("queued", [])

    return {
        "context": ctx.model_dump(mode="json"),
        "interview": interview_status(ctx),
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
