"""Maistro Engine — FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from maistro.api import chat_completions, health, models, tasks, webhooks, ws
from maistro.tasks.queue import get_task_queue
from maistro.tasks.runner import TaskRunner

logger = structlog.get_logger()

_runner: TaskRunner | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start/stop the background task runner with the app lifecycle."""
    global _runner

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
    )

    queue = get_task_queue()
    _runner = TaskRunner(queue)
    await _runner.start()
    await logger.ainfo("maistro_engine_started")

    yield

    if _runner:
        await _runner.stop()
    await logger.ainfo("maistro_engine_stopped")


app = FastAPI(
    title="Maistro Engine",
    description="Software engineering department in a box",
    version="0.1.0",
    lifespan=lifespan,
)

# Register routers
app.include_router(health.router)
app.include_router(tasks.router)
app.include_router(chat_completions.router)
app.include_router(models.router)
app.include_router(webhooks.router)
app.include_router(ws.router)
