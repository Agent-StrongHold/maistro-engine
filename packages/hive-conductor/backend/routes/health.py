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
    checks = {"api": True, "memory": True}
    return ReadyResponse(ready=all(checks.values()), checks=checks)
