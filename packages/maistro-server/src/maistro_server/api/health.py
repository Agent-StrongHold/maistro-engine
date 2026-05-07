"""Health check endpoints — liveness and readiness probes."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from maistro_server.api.schemas import HealthResponse
from maistro.config.settings import Settings, get_settings

router = APIRouter(tags=["health"])

_start_time = time.monotonic()


class ProbeResult(BaseModel):
    status: str  # "ok" or "error"
    latency_ms: float = 0
    detail: str = ""


class DetailedHealthResponse(BaseModel):
    status: str  # "ok", "degraded", "unhealthy"
    uptime_seconds: float
    service: str
    version: str
    checks: dict[str, ProbeResult]


async def _check_postgres(settings: Settings) -> ProbeResult:
    """Check PostgreSQL connectivity."""
    try:
        import asyncpg  # type: ignore[import-untyped]

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
        return ProbeResult(status="ok")
    except Exception as exc:
        return ProbeResult(status="error", detail=str(exc)[:100])


async def _check_docker() -> ProbeResult:
    """Probe Docker daemon availability."""
    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "info",
            "--format",
            "{{.ServerVersion}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        latency = (time.monotonic() - t0) * 1000
        if proc.returncode == 0:
            return ProbeResult(status="ok", latency_ms=round(latency, 1))
        return ProbeResult(
            status="error", latency_ms=round(latency, 1), detail="docker info failed"
        )
    except FileNotFoundError:
        return ProbeResult(status="error", detail="docker binary not found")
    except TimeoutError:
        return ProbeResult(status="error", detail="docker probe timed out")
    except Exception as exc:
        return ProbeResult(status="error", detail=str(exc)[:200])


@router.get("/health")
async def health_check() -> HealthResponse:
    """Lightweight liveness probe."""
    from maistro_server.main import APP_VERSION

    uptime = time.monotonic() - _start_time
    return HealthResponse(
        status="ok",
        uptime_seconds=round(uptime, 1),
        service="maistro-engine",
        version=APP_VERSION,
    )


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Unconditional liveness — Kubernetes liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready", response_model=None)
async def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DetailedHealthResponse | JSONResponse:
    """Readiness probe — checks Docker, Postgres, and LLM circuit breaker."""
    from maistro.agents.circuit_breaker import llm_circuit
    from maistro_server.main import APP_VERSION

    uptime = time.monotonic() - _start_time
    docker_result = await _check_docker()
    postgres_result = await _check_postgres(settings)

    circuit_state = llm_circuit.state
    llm_result = ProbeResult(
        status="ok" if circuit_state == "closed" else "error",
        detail=f"circuit={circuit_state}",
    )

    checks = {
        "docker": docker_result,
        "postgres": postgres_result,
        "llm_provider": llm_result,
    }
    all_ok = all(c.status == "ok" for c in checks.values())

    result = DetailedHealthResponse(
        status="ok" if all_ok else "degraded",
        uptime_seconds=round(uptime, 1),
        service="maistro-engine",
        version=APP_VERSION,
        checks=checks,
    )

    if not all_ok:
        return JSONResponse(content=result.model_dump(), status_code=503)
    return result
