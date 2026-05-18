from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import stores
from fastapi import APIRouter, HTTPException, Request
from models.schemas import Mission, MissionStep
from pydantic import BaseModel, ConfigDict
from services.engine import get_engine

from routes.audit import log_audit

router = APIRouter(tags=["missions"])


def _now() -> datetime:
    return datetime.now(UTC)


def _task_to_mission(rec: object) -> Mission:
    """Convert a TaskRecord from EngineService into a hive Mission."""
    return Mission(
        id=rec.id,  # type: ignore[attr-defined]
        name=rec.name,  # type: ignore[attr-defined]
        description=rec.description,  # type: ignore[attr-defined]
        status=rec.mission_status,  # type: ignore[attr-defined]
        priority="medium",
        created_at=rec.created_at,  # type: ignore[attr-defined]
        updated_at=rec.completed_at or rec.started_at or rec.created_at,  # type: ignore[attr-defined]
        started_at=rec.started_at,  # type: ignore[attr-defined]
        completed_at=rec.completed_at,  # type: ignore[attr-defined]
        progress=rec.progress,  # type: ignore[attr-defined]
    )


@router.get("", response_model=list[Mission])
def list_missions() -> list[Mission]:
    engine = get_engine()
    if engine.is_configured or engine._queue is not None:
        tasks = engine.list_tasks()
        if tasks:
            return [_task_to_mission(t) for t in tasks]
    return list(stores.missions.values())


@router.get("/{mission_id}", response_model=Mission)
def get_mission(mission_id: str) -> Mission:
    engine = get_engine()
    if engine.is_configured or engine._queue is not None:
        rec = engine.get_task(mission_id)
        if rec is not None:
            return _task_to_mission(rec)
    if mission_id not in stores.missions:
        raise HTTPException(status_code=404, detail="mission not found")
    return stores.missions[mission_id]


@router.get("/{mission_id}/steps", response_model=list[MissionStep])
def get_steps(mission_id: str) -> list[MissionStep]:
    engine = get_engine()
    if engine.is_configured or engine._queue is not None:
        rec = engine.get_task(mission_id)
        if rec is not None:
            # Synthesise step list from current task phase
            step_status = "running" if rec.mission_status == "running" else rec.mission_status  # type: ignore[attr-defined]
            step: MissionStep | None = None
            current = rec.current_step  # type: ignore[attr-defined]
            if current:
                step = MissionStep(
                    id=f"{mission_id}-step-1",
                    mission_id=mission_id,
                    name=current,
                    description=current,
                    status=step_status,
                    order=1,
                )
            return [step] if step else []
    return list(stores.mission_steps.get(mission_id, []))


class CreateMissionBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""


@router.post("", response_model=Mission)
async def create_mission(body: CreateMissionBody) -> Mission:
    engine = get_engine()
    if engine.is_configured or engine._queue is not None:
        rec = await engine.submit_task(body.name, body.description or body.name)
        log_audit("mission_create", "system", target=rec.id, detail={"name": body.name})
        return _task_to_mission(rec)

    # Fallback: in-memory stub (dev mode without maistro-core)
    mid = str(uuid4())[:12]
    t = _now()
    m = Mission(
        id=mid,
        name=body.name,
        description=body.description or body.name,
        status="pending",
        priority="medium",
        created_at=t,
        updated_at=t,
        progress=0.0,
        steps_total=0,
        steps_completed=0,
    )
    stores.missions[mid] = m
    stores.mission_steps[mid] = []
    log_audit("mission_create", "system", target=mid, detail={"name": body.name})
    return m


class UpdateMissionStatusBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str


_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


@router.patch("/{mission_id}/status", response_model=Mission)
def update_mission_status(
    mission_id: str,
    body: UpdateMissionStatusBody,
    request: Request,
) -> Mission:
    if mission_id not in stores.missions:
        raise HTTPException(status_code=404, detail="mission not found")
    m = stores.missions[mission_id]
    m.status = body.status  # type: ignore[assignment]
    m.updated_at = _now()
    if body.status in _TERMINAL_STATUSES:
        m.completed_at = _now()
        m.progress = 1.0 if body.status == "completed" else m.progress
        _revoke_task_elevation(request, mission_id)
    stores.missions[mission_id] = m
    log_audit("mission_status", "system", target=mission_id, detail={"status": body.status})
    return m


def _revoke_task_elevation(request: Request, task_id: str) -> None:
    session_id = request.cookies.get("hive_session")
    if not session_id:
        return
    try:
        from routes.auth import revoke_task_elevation

        revoke_task_elevation(session_id, task_id)
    except Exception:
        pass
