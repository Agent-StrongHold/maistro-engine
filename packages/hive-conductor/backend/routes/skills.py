from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import stores
from fastapi import APIRouter, HTTPException
from models.schemas import Skill
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["skills"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=list[Skill])
def list_skills() -> list[Skill]:
    return list(stores.skills.values())


@router.get("/{skill_id}", response_model=Skill)
def get_skill(skill_id: str) -> Skill:
    if skill_id not in stores.skills:
        raise HTTPException(status_code=404, detail="skill not found")
    return stores.skills[skill_id]


class CreateSkillBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    version: str = "1.0.0"
    category: str = "general"
    author: str = "hive"
    parameters: list[dict] = []


@router.post("", response_model=Skill, status_code=201)
def create_skill(body: CreateSkillBody) -> Skill:
    sid = str(uuid4())
    skill = Skill(
        id=sid,
        name=body.name,
        description=body.description,
        version=body.version,
        category=body.category,
        author=body.author,
        enabled=True,
        usage_count=0,
        parameters=body.parameters,
    )
    stores.skills[sid] = skill
    return skill


class UpdateSkillBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    description: str | None = None
    version: str | None = None
    category: str | None = None
    author: str | None = None
    parameters: list[dict] | None = None
    enabled: bool | None = None


@router.put("/{skill_id}", response_model=Skill)
def update_skill(skill_id: str, body: UpdateSkillBody) -> Skill:
    if skill_id not in stores.skills:
        raise HTTPException(status_code=404, detail="skill not found")
    skill = stores.skills[skill_id]
    updates = body.model_dump(exclude_none=True)
    skill = skill.model_copy(update=updates)
    stores.skills[skill_id] = skill
    return skill


@router.delete("/{skill_id}", status_code=204)
def delete_skill(skill_id: str) -> None:
    if skill_id not in stores.skills:
        raise HTTPException(status_code=404, detail="skill not found")
    stores.skills.pop(skill_id)


@router.post("/scan")
def scan_skills() -> dict:
    return {"findings": [], "status": "clean"}


class ForgeSkillBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str


@router.post("/forge", response_model=Skill)
def forge_skill(body: ForgeSkillBody) -> Skill:
    sid = str(uuid4())
    skill = Skill(
        id=sid,
        name=f"forge-{sid[:8]}",
        description=body.description,
        version="0.1.0",
        category="generated",
        author="forge",
        enabled=True,
        usage_count=0,
        parameters=[],
    )
    stores.skills[sid] = skill
    return skill


@router.patch("/{skill_id}/toggle", response_model=Skill)
def toggle_skill(skill_id: str) -> Skill:
    if skill_id not in stores.skills:
        raise HTTPException(status_code=404, detail="skill not found")
    skill = stores.skills[skill_id]
    skill = skill.model_copy(update={"enabled": not skill.enabled})
    stores.skills[skill_id] = skill
    return skill
