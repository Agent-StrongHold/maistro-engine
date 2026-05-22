"""WebSocket streaming for real-time task progress."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from maistro.config.settings import Settings, get_settings
from maistro.tasks.models import TaskResponse
from maistro.tasks.queue import TaskQueue, get_task_queue
from maistro_server.api.auth import resolve_token_principal

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
    result: dict[str, Any]
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


def _ws_owner_id(token: str | None, settings: Settings) -> str | None:
    """Return user_id for WS stream, or None when auth fails."""
    if not settings.api_keys:
        return "dev"
    if not token:
        return None
    principal = resolve_token_principal(token, settings)
    return principal.user_id if principal else None


@router.websocket("/stream/{task_id}")
async def stream_task(
    websocket: WebSocket,
    task_id: str,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
    token: str | None = Query(None),
) -> None:
    owner_id = _ws_owner_id(token, settings)
    if owner_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    try:
        async with asyncio.timeout(WS_SESSION_TIMEOUT):
            last_status: str | None = None
            last_progress: str | None = None

            while True:
                task = queue.get(task_id, user_id=owner_id)
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

                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(queue.wait_for_update(task_id), timeout=5.0)

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected", task_id=task_id)
    except TimeoutError:
        logger.warning("ws_session_timeout", task_id=task_id)
        with contextlib.suppress(Exception):
            await websocket.close(code=4008, reason="Session timeout")
    except Exception:
        logger.exception("ws_unexpected_error", task_id=task_id)
        with contextlib.suppress(Exception):
            await websocket.close(code=4500, reason="Internal error")
