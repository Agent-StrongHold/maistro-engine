"""Health check endpoints — liveness and readiness probes."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from maistro.config.settings import Settings, get_settings

router = APIRouter(tags=["health"])

_start_time = time.monotonic()


async def _check_postgres(settings: Settings) -> dict[str, Any]:
    """Check PostgreSQL connectivity."""
    try:
        import asyncpg
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=settings.db.host,
                port=settings.db.port,
                user=settings.db.user,
                password=settings.db.password,
                database=settings.db.name,
            ),
            timeout=3.0,
        )
        await conn.close()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:100]}


async def _check_docker() -> dict[str, Any]:
    """Check Docker daemon reachability."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "info", "--format", "{{.ServerVersion}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        if proc.returncode == 0:
            return {"status": "ok", "version": stdout.decode().strip()}
        return {"status": "error", "detail": "docker info failed"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:100]}


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Basic liveness probe — process is running."""
    uptime = time.monotonic() - _start_time
    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 1),
        "service": "maistro-engine",
        "version": "0.1.0",
    }


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Liveness probe — process is alive."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Readiness probe — checks all dependencies."""
    postgres = await _check_postgres(settings)
    docker = await _check_docker()

    all_ok = postgres["status"] == "ok" and docker["status"] == "ok"

    from fastapi.responses import JSONResponse

    result = {
        "status": "ok" if all_ok else "degraded",
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
        "checks": {
            "postgres": postgres,
            "docker": docker,
        },
    }

    if not all_ok:
        return JSONResponse(content=result, status_code=503)
    return result
