"""Health check endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter

from maistro.api.schemas import HealthResponse

router = APIRouter(tags=["health"])

_start_time = time.monotonic()


@router.get("/health")
async def health_check() -> HealthResponse:
    from maistro.main import APP_VERSION

    uptime = time.monotonic() - _start_time
    return HealthResponse(
        status="ok",
        uptime_seconds=round(uptime, 1),
        service="maistro-engine",
        version=APP_VERSION,
    )
