from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from models.schemas import Mission, MissionStep

import stores

router = APIRouter(tags=["missions"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=list[Mission])
def list_missions() -> list[Mission]:
    return list(stores.missions.values())


@router.get("/{mission_id}", response_model=Mission)
def get_mission(mission_id: str) -> Mission:
    if mission_id not in stores.missions:
        raise HTTPException(status_code=404, detail="mission not found")
    return stores.missions[mission_id]


@router.get("/{mission_id}/steps", response_model=list[MissionStep])
def get_steps(mission_id: str) -> list[MissionStep]:
    return list(stores.mission_steps.get(mission_id, []))


class CreateMissionBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""


@router.post("", response_model=Mission)
def create_mission(body: CreateMissionBody) -> Mission:
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
    return m
