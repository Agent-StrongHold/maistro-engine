"""Maistro Engine — FastAPI application entry point."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from maistro.api import chat_completions, health, models, tasks, webhooks, ws
from maistro.config.settings import Settings, get_settings
from maistro.tasks.queue import get_task_queue
from maistro.tasks.runner import TaskRunner

logger = structlog.get_logger()

_runner: TaskRunner | None = None


def _validate_startup(settings: Settings) -> None:
    """Fail-fast startup checks. Raises RuntimeError if critical config is missing."""
    if settings.require_auth and not settings.api_keys:
        raise RuntimeError(
            "CRITICAL: No API keys configured and REQUIRE_AUTH is true. "
            "Set API_KEYS env var or set REQUIRE_AUTH=false for local development."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start/stop the background task runner with the app lifecycle."""
    global _runner

    settings = get_settings()

    # Configure structlog — JSON in production, console in debug
    if settings.debug:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
    )

    # Fail-fast startup validation (CRIT-02)
    _validate_startup(settings)

    queue = get_task_queue()
    _runner = TaskRunner(queue)
    await _runner.start()
    await logger.ainfo("maistro_engine_started")

    # Register graceful shutdown handler (MAJ-11)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_graceful_shutdown(s)))

    yield

    if _runner:
        await _runner.stop()
    await logger.ainfo("maistro_engine_stopped")


async def _graceful_shutdown(sig: signal.Signals) -> None:
    """Handle shutdown signals with task draining."""
    await logger.ainfo("shutdown_signal_received", signal=sig.name)
    if _runner:
        await _runner.drain(timeout=30)


app = FastAPI(
    title="Maistro Engine",
    description="Software engineering department in a box",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware (MIN-03)
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Register routers
app.include_router(health.router)
app.include_router(tasks.router)
app.include_router(chat_completions.router)
app.include_router(models.router)
app.include_router(webhooks.router)
app.include_router(ws.router)
