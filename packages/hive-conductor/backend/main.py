"""Hive Conductor FastAPI entrypoint: API + optional static SPA."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from config import get_settings
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from middleware.auth import AuthMiddleware
from pydantic import BaseModel, ConfigDict
from routes import (
    agents,
    audit,
    auth,
    chat,
    cli,
    containers,
    dags,
    health,
    install,
    mcp,
    memory,
    messages,
    missions,
    quotas,
    schedules,
    setup,
    skills,
    ws,
)
from routes import settings as settings_r
from services import engine as engine_service
from services import foundation as foundation_service
from services.ha_tools import get_all_confirms, get_pending_confirms, respond_confirm

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "frontend" / "dist"


class ConfirmResponseBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    response: str


_confirms_router = APIRouter(tags=["confirms"])


@_confirms_router.get("")
def list_confirms():
    return get_all_confirms()


@_confirms_router.get("/pending")
def list_pending():
    return get_pending_confirms()


@_confirms_router.post("/{confirm_id}/respond")
async def respond_to_confirm(confirm_id: str, body: ConfirmResponseBody):
    return await respond_confirm(confirm_id, body.response)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        await foundation_service.start_foundation(get_settings())
    except Exception:
        import stores
        stores.initialize_stores()
    try:
        await engine_service.start_engine(get_settings())
    except Exception:
        pass
    yield
    await engine_service.stop_engine()
    await foundation_service.stop_foundation()


def create_app() -> FastAPI:
    app = FastAPI(title="Hive Conductor", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/v1/auth")
    app.include_router(install.router, prefix="/v1/install")
    app.include_router(chat.router, prefix="/v1/chat")
    app.include_router(missions.router, prefix="/v1/tasks")
    app.include_router(schedules.router, prefix="/v1/schedules")
    app.include_router(skills.router, prefix="/v1/skills")
    app.include_router(agents.router, prefix="/v1/agents")
    app.include_router(mcp.router, prefix="/v1/mcp")
    app.include_router(cli.router, prefix="/v1/cli")
    app.include_router(containers.router, prefix="/v1/containers")
    app.include_router(memory.router, prefix="/v1/memory")
    app.include_router(settings_r.router, prefix="/v1/settings")
    app.include_router(ws.router, prefix="/v1/ws")
    app.include_router(setup.router, prefix="/v1/setup")
    app.include_router(dags.router, prefix="/v1/dags")
    app.include_router(messages.router, prefix="/v1/messages")
    app.include_router(audit.router, prefix="/v1/audit")
    app.include_router(quotas.router, prefix="/v1/quotas")
    app.include_router(_confirms_router, prefix="/v1/confirms")

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


app = create_app()
