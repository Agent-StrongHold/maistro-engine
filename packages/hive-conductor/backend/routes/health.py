from __future__ import annotations

import time
from datetime import UTC, datetime

from config import get_settings
from fastapi import APIRouter
from models.schemas import HealthResponse, ReadyResponse

_START = time.monotonic()
_STARTED_AT = datetime.now(UTC).isoformat()

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    uptime = time.monotonic() - _START
    try:
        from services.foundation import get_foundation
        f = get_foundation()
        vault_enabled = f.vault_available
        state_enabled = f.state_available
        privilege_available = f.privilege_available
        reactor_available = f.reactor_available
    except RuntimeError:
        vault_enabled = False
        state_enabled = False
        privilege_available = False
        reactor_available = False
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": uptime,
        "started_at": _STARTED_AT,
        "router_model": settings.chat_default_model,
        "vault_enabled": vault_enabled,
        "state_enabled": state_enabled,
        "privilege_enabled": privilege_available,
        "reactor_enabled": reactor_available,
    }


@router.get("/health/ready")
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
