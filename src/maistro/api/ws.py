"""WebSocket streaming for real-time task progress."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from maistro.config.settings import get_settings
from maistro.security.secret_equal import secret_equal
from maistro.tasks.models import TaskResponse
from maistro.tasks.queue import TaskQueue, get_task_queue

logger = structlog.get_logger()

router = APIRouter(tags=["streaming"])

WS_SESSION_TIMEOUT = 3600

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


class WSProgressMessage(BaseModel):
    task_id: str
    phase: str | None
    status: str
    message: str
    timestamp: str


class WSResultMessage(BaseModel):
    task_id: str
    phase: str = "done"
    result: dict
    timestamp: str


class WSErrorMessage(BaseModel):
    error: str


def _has_state_changed(
    task: TaskResponse, last_status: str | None, last_progress: str | None
) -> tuple[bool, str, str]:
    """Check if status or progress changed. Returns (changed, status, progress)."""
    current_status = task.status.value
    current_progress = task.progress.current if task.progress else ""
    changed = current_status != last_status or current_progress != last_progress
    return changed, current_status, current_progress


def _build_progress_message(task_id: str, task: TaskResponse) -> WSProgressMessage:
    return WSProgressMessage(
        task_id=task_id,
        phase=task.phase,
        status=task.status.value,
        message=task.progress.current if task.progress else "",
        timestamp=datetime.now(UTC).isoformat(),
    )


def _build_result_message(task_id: str, task: TaskResponse) -> WSResultMessage | None:
    if task.result is None:
        return None
    return WSResultMessage(
        task_id=task_id,
        result=task.result.model_dump(),
        timestamp=datetime.now(UTC).isoformat(),
    )


def _is_terminal(status: str) -> bool:
    return status in _TERMINAL_STATUSES


@router.websocket("/stream/{task_id}")
async def stream_task(
    websocket: WebSocket,
    task_id: str,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    token: str | None = Query(None),
) -> None:
    settings = get_settings()
    if settings.api_keys:
        if not token or not any(secret_equal(token, key) for key in settings.api_keys):
            await websocket.close(code=4001, reason="Unauthorized")
            return

    await websocket.accept()

    try:
        async with asyncio.timeout(WS_SESSION_TIMEOUT):
            last_status: str | None = None
            last_progress: str | None = None

            while True:
                task = queue.get(task_id)
                if task is None:
                    await websocket.send_json(WSErrorMessage(error="Task not found").model_dump())
                    break

                changed, current_status, current_progress = _has_state_changed(
                    task, last_status, last_progress
                )
                if changed:
                    await websocket.send_json(_build_progress_message(task_id, task).model_dump())
                    last_status = current_status
                    last_progress = current_progress

                if _is_terminal(current_status):
                    result_msg = _build_result_message(task_id, task)
                    if result_msg:
                        await websocket.send_json(result_msg.model_dump())
                    break

                try:
                    await asyncio.wait_for(queue.wait_for_update(task_id), timeout=5.0)
                except TimeoutError:
                    pass

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected", task_id=task_id)
    except TimeoutError:
        logger.warning("ws_session_timeout", task_id=task_id)
        try:
            await websocket.close(code=4008, reason="Session timeout")
        except Exception:
            pass
    except Exception:
        logger.exception("ws_unexpected_error", task_id=task_id)
        try:
            await websocket.close(code=4500, reason="Internal error")
        except Exception:
            pass
