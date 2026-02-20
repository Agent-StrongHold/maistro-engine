"""Maistro Engine — FastAPI application entry point."""

from __future__ import annotations

import importlib.metadata
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from maistro.api import chat_completions, health, models, tasks, webhooks, ws
from maistro.api.schemas import ErrorDetail, ErrorResponse
from maistro.tasks.queue import get_task_queue
from maistro.tasks.runner import TaskRunner
from maistro.tools.sandbox.server import cleanup_all_containers

logger = structlog.get_logger()

_runner: TaskRunner | None = None

# Single source of truth for version — read from installed package metadata
try:
    APP_VERSION = importlib.metadata.version("maistro")
except importlib.metadata.PackageNotFoundError:
    APP_VERSION = "0.1.0-dev"


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
    await logger.ainfo("maistro_engine_started", version=APP_VERSION)

    yield

    if _runner:
        await _runner.stop()
    await cleanup_all_containers()
    await logger.ainfo("maistro_engine_stopped")


app = FastAPI(
    title="Maistro Engine",
    description="Software engineering department in a box",
    version=APP_VERSION,
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Wrap HTTPException in consistent error envelope."""
    request_id = uuid.uuid4().hex[:12]
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                type="http_error",
                message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                request_id=request_id,
            ),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions — log and return structured JSON."""
    request_id = uuid.uuid4().hex[:12]
    logger.exception(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(
                type="internal_error",
                message="Internal server error",
                request_id=request_id,
            ),
        ).model_dump(),
    )


# Register routers
app.include_router(health.router)
app.include_router(tasks.router)
app.include_router(chat_completions.router)
app.include_router(models.router)
app.include_router(webhooks.router)
app.include_router(ws.router)
