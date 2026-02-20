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
from maistro.tasks.queue import TaskQueue, get_task_queue

logger = structlog.get_logger()

router = APIRouter(tags=["streaming"])

# Maximum WebSocket session duration (1 hour)
WS_SESSION_TIMEOUT = 3600


# --- WebSocket message schemas (Item 34) ---

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


@router.websocket("/stream/{task_id}")
async def stream_task(
    websocket: WebSocket,
    task_id: str,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    token: str | None = Query(None),
) -> None:
    # Authenticate before accepting
    settings = get_settings()
    if settings.api_keys:
        if not token or not any(secret_equal(token, key) for key in settings.api_keys):
            await websocket.close(code=4001, reason="Unauthorized")
            return

    await websocket.accept()

    try:
        async with asyncio.timeout(WS_SESSION_TIMEOUT):
            last_status = None
            last_progress = None

            while True:
                task = queue.get(task_id)
                if task is None:
                    msg = WSErrorMessage(error="Task not found")
                    await websocket.send_json(msg.model_dump())
                    break

                # Send update if status or progress changed
                current_status = task.status.value
                current_progress = task.progress.current if task.progress else ""

                if current_status != last_status or current_progress != last_progress:
                    msg = WSProgressMessage(
                        task_id=task_id,
                        phase=task.phase,
                        status=current_status,
                        message=current_progress,
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                    await websocket.send_json(msg.model_dump())
                    last_status = current_status
                    last_progress = current_progress

                # Stop streaming if task is terminal
                if current_status in ("completed", "failed", "cancelled"):
                    if task.result:
                        result_msg = WSResultMessage(
                            task_id=task_id,
                            result=task.result.model_dump(),
                            timestamp=datetime.now(UTC).isoformat(),
                        )
                        await websocket.send_json(result_msg.model_dump())
                    break

                # Wait for event signal instead of polling
                try:
                    await asyncio.wait_for(queue.wait_for_update(task_id), timeout=5.0)
                except TimeoutError:
                    # Periodic heartbeat check even without updates
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
