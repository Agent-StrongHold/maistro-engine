from __future__ import annotations

from fastapi import APIRouter

from models.schemas import Container

import stores

router = APIRouter(tags=["containers"])


@router.get("", response_model=list[Container])
def list_containers() -> list[Container]:
    return list(stores.containers.values())
