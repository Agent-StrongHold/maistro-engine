"""Gated Jira work items — suggest, clarify, edit, confirm."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from services import program_store as prog
from services.engine import get_engine
from services.pm_fleet import invoke_pm_agent, is_pm_poc_mode

from maistro.agents.pm_capabilities import WORK_ITEM_LABELS, WorkItemType
from maistro.agents.work_items import (
    WorkItemDraft,
    apply_clarifying_answers,
    confirm_post_stub,
    suggest_work_item,
    update_draft_fields,
)
from routes.audit import log_audit

router = APIRouter(tags=["work-items"])
logger = logging.getLogger("hive.work_items")


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    uid = user.get("id")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(uid)


def _require_pm() -> None:
    if not is_pm_poc_mode():
        raise HTTPException(status_code=404, detail="Work items only available in PM POC mode")


def _load_draft(draft_id: str, user_id: str) -> WorkItemDraft:
    import stores

    raw = stores.work_item_drafts.get(draft_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft = WorkItemDraft.model_validate(raw)
    if draft.user_id != user_id:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


def _save_draft(draft: WorkItemDraft) -> WorkItemDraft:
    import stores

    stores.work_item_drafts[draft.id] = draft.model_dump(mode="json")
    return draft


def _list_drafts(user_id: str) -> list[WorkItemDraft]:
    import stores

    out: list[WorkItemDraft] = []
    for raw in stores.work_item_drafts.values():
        try:
            d = WorkItemDraft.model_validate(raw)
        except Exception:
            continue
        if d.user_id == user_id and d.status != "cancelled":
            out.append(d)
    return sorted(out, key=lambda d: d.updated_at, reverse=True)


class SuggestBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    work_type: WorkItemType
    reason: str = ""
    hint: str = ""
    parent_key: str = ""


@router.get("")
def list_work_items(request: Request) -> dict[str, Any]:
    _require_pm()
    uid = _user_id(request)
    drafts = _list_drafts(uid)
    return {"drafts": [d.as_dict() for d in drafts]}


@router.post("/suggest")
def suggest_work_item_route(body: SuggestBody, request: Request) -> dict[str, Any]:
    _require_pm()
    uid = _user_id(request)
    ctx = prog.get_context(uid)
    draft = suggest_work_item(
        uid,
        body.work_type,
        ctx,
        reason=body.reason or f"User requested {WORK_ITEM_LABELS[body.work_type]}",
        hint=body.hint,
        parent_key=body.parent_key,
    )
    _save_draft(draft)
    log_audit("work_item_suggest", uid, target=draft.id, detail={"work_type": body.work_type})
    return {"draft": draft.as_dict(), "message": "Review clarifying questions, edit fields, then confirm to post to Jira."}


@router.get("/{draft_id}")
def get_work_item(draft_id: str, request: Request) -> dict[str, Any]:
    _require_pm()
    return {"draft": _load_draft(draft_id, _user_id(request)).as_dict()}


class ClarifyBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answers: dict[str, str] = Field(default_factory=dict)


@router.post("/{draft_id}/clarify")
def clarify_work_item(draft_id: str, body: ClarifyBody, request: Request) -> dict[str, Any]:
    _require_pm()
    uid = _user_id(request)
    draft = apply_clarifying_answers(_load_draft(draft_id, uid), body.answers)
    draft = _save_draft(draft)
    return {"draft": draft.as_dict()}


class PatchFieldsBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str | None = None
    description: str | None = None
    project_key: str | None = None
    parent_key: str | None = None
    priority: str | None = None
    labels: list[str] | None = None
    assignee: str | None = None
    due_date: str | None = None


@router.patch("/{draft_id}")
def patch_work_item(draft_id: str, body: PatchFieldsBody, request: Request) -> dict[str, Any]:
    _require_pm()
    uid = _user_id(request)
    draft = _load_draft(draft_id, uid)
    if draft.status == "posted":
        raise HTTPException(status_code=400, detail="Already posted to Jira")
    updates = body.model_dump(exclude_none=True)
    draft = update_draft_fields(draft, updates)
    if draft.status == "clarifying" and draft.fields.summary and draft.fields.description:
        required_ok = all(
            not q.required or q.answer
            for q in draft.clarifying_questions
            if q.id not in ("summary", "description")
        )
        if required_ok:
            draft = draft.model_copy(update={"status": "ready"})
    draft = _save_draft(draft)
    return {"draft": draft.as_dict()}


@router.post("/{draft_id}/confirm")
async def confirm_work_item(draft_id: str, request: Request) -> dict[str, Any]:
    """User-approved post to Jira (stub) — only after clarify + edit."""
    _require_pm()
    uid = _user_id(request)
    draft = _load_draft(draft_id, uid)
    try:
        posted, result = confirm_post_stub(draft)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save_draft(posted)

    engine = get_engine()
    task_type, description, agent_id = invoke_pm_agent(
        posted.agent_id,
        posted.capability,
        {
            "title": posted.fields.summary,
            "summary": posted.fields.description,
            "program": prog.context_dict(uid),
            "jira_issue_key": result.get("issue_key"),
            "confirmed": True,
        },
    )
    prog_ctx = prog.context_dict(uid)
    prog_ctx["confirmed"] = True
    prog_ctx["jira_issue_key"] = result.get("issue_key")
    rec = await engine.submit_task(
        posted.agent_id,
        description,
        user_id=uid,
        task_type=task_type,
        agent_id=agent_id,
        capability=posted.capability,
        program_context=prog_ctx,
    )
    log_audit(
        "work_item_confirm",
        uid,
        target=posted.id,
        detail={"issue_key": result.get("issue_key"), "task_id": rec.id},
    )
    return {
        "draft": posted.as_dict(),
        "jira": result,
        "task_id": rec.id,
        "message": f"Posted {result.get('issue_key')} to Jira (stub).",
    }


@router.delete("/{draft_id}", status_code=204)
def cancel_work_item(draft_id: str, request: Request) -> None:
    _require_pm()
    uid = _user_id(request)
    draft = _load_draft(draft_id, uid)
    _save_draft(draft.model_copy(update={"status": "cancelled"}))
