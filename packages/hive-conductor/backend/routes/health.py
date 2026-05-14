from __future__ import annotations

import time

from fastapi import APIRouter
from models.schemas import HealthResponse, ReadyResponse

_START = time.monotonic()

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0", uptime_seconds=time.monotonic() - _START)


@router.get("/health/ready", response_model=ReadyResponse)
def ready() -> ReadyResponse:
    try:
        from services.foundation import get_foundation
        f = get_foundation()
        checks = {
            "api": True,
            "vault": f.vault_available,
            "state": f.state_available,
            "privilege": f.privilege_available,
            "reactor": f.reactor_available,
        }
    except RuntimeError:
        checks = {"api": True, "vault": False, "state": False, "privilege": False, "reactor": False}
    return ReadyResponse(ready=checks["api"], checks=checks)
