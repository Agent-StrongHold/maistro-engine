"""Health check endpoint."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["health"])

_start_time = time.monotonic()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    uptime = time.monotonic() - _start_time
    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 1),
        "service": "maistro-engine",
        "version": "0.1.0",
    }
