from __future__ import annotations

from fastapi import APIRouter

from models.schemas import Skill

import stores

router = APIRouter(tags=["skills"])


@router.get("", response_model=list[Skill])
def list_skills() -> list[Skill]:
    return list(stores.skills.values())
