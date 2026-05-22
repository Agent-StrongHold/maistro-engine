"""Shared program hyperagent helpers — used by program and missions routes."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from services import program_store as prog
from services.engine import get_engine
from services.pm_fleet import invoke_pm_agent, is_pm_poc_mode

from maistro.agents.hyperagent import (
    interview_status,
    propose_actions,
    propose_autonomous_actions,
    propose_work_item_suggestions,
)
from maistro.agents.pm_capabilities import is_autonomous
from maistro.agents.program_context import apply_guidance


def user_id_from_request(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    uid = user.get("id")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(uid)


def require_pm_poc() -> None:
    if not is_pm_poc_mode():
        raise HTTPException(
            status_code=404,
            detail=(
                "Program hyperagent only available in PM POC mode. "
                "Set HIVE_POC_MODE=pm and MAISTRO_POC_MODE=pm, then restart Hive."
            ),
        )


async def apply_guidance_and_pulse(
    user_id: str,
    text: str,
    *,
    max_pulse_actions: int = 2,
) -> dict[str, Any]:
    """Record guidance and optionally queue autonomous fleet work."""
    ctx = apply_guidance(prog.get_context(user_id), text)
    ctx = prog.save_context(ctx)

    queued: list[dict[str, str]] = []
    pulse_error: str | None = None
    if ctx.interview_complete and max_pulse_actions > 0:
        try:
            pulse_result = await run_program_pulse(user_id, max_actions=max_pulse_actions)
            queued = pulse_result.get("queued", [])
        except Exception as exc:
            pulse_error = "Fleet pulse skipped (engine unavailable)"

    out: dict[str, Any] = {
        "context": ctx.model_dump(mode="json"),
        "interview": interview_status(ctx),
        "proposed_actions": [a.as_dict() for a in propose_actions(ctx, max_actions=5)],
        "queued_tasks": queued,
    }
    if pulse_error:
        out["pulse_note"] = pulse_error
    if not ctx.interview_complete:
        out["message"] = (
            "Guidance saved. Complete the Program interview to enable autonomous fleet actions."
        )
    elif queued:
        out["message"] = f"Guidance saved — {len(queued)} autonomous task(s) queued."
    else:
        out["message"] = "Guidance saved — fleet will use this on the next pulse."
    return out


async def run_program_pulse(user_id: str, *, max_actions: int = 4) -> dict[str, Any]:
    """Autonomous-only fleet tick."""
    from datetime import UTC, datetime

    ctx = prog.get_context(user_id)
    if not ctx.interview_complete:
        return {
            "queued": [],
            "skipped": "interview_incomplete",
            "interview": interview_status(ctx),
        }

    actions = propose_autonomous_actions(ctx, max_actions=max_actions)
    suggestions = propose_work_item_suggestions(ctx, user_id)
    engine = get_engine()
    queued: list[dict[str, str]] = []

    if engine._queue is None:
        return {
            "queued": [],
            "proposed": [a.as_dict() for a in actions],
            "work_item_suggestions": [s.as_dict() for s in suggestions],
            "context": ctx.model_dump(mode="json"),
            "note": "Task engine not running",
        }

    for action in actions:
        if not is_autonomous(action.capability):
            continue
        try:
            task_type, description, agent_id = invoke_pm_agent(
                action.agent_id,
                action.capability,
                {
                    **action.payload,
                    "hyperagent_reason": action.reason,
                    "program": prog.context_dict(user_id),
                },
            )
            from maistro.agents.program_context import context_for_task

            rec = await engine.submit_task(
                agent_id,
                description,
                user_id=user_id,
                task_type=task_type,
                agent_id=agent_id,
                capability=action.capability,
                program_context=context_for_task(ctx),
            )
            queued.append(
                {
                    "task_id": rec.id,
                    "agent_id": agent_id,
                    "capability": action.capability,
                    "reason": action.reason,
                }
            )
        except Exception:
            continue

    now = datetime.now(UTC).isoformat()
    prog.save_context(ctx.model_copy(update={"last_pulse_at": now, "updated_at": now}))

    return {
        "queued": queued,
        "proposed": [a.as_dict() for a in actions],
        "work_item_suggestions": [s.as_dict() for s in suggestions],
        "context": ctx.model_dump(mode="json"),
    }
