"""Hive Conductor FastAPI entrypoint: API + optional static SPA."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from config import get_settings
from routes import (
    agents,
    chat,
    cli,
    containers,
    health,
    install,
    mcp,
    memory,
    missions,
    schedules,
    skills,
    ws,
)
from routes import settings as settings_r
from services import engine as engine_service

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await engine_service.start_engine(get_settings())
    yield
    await engine_service.stop_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="Hive Conductor", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
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

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


app = create_app()
