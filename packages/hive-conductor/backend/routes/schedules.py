from __future__ import annotations

from fastapi import APIRouter

from models.schemas import Schedule

import stores

router = APIRouter(tags=["schedules"])


@router.get("", response_model=list[Schedule])
def list_schedules() -> list[Schedule]:
    return list(stores.schedules.values())
