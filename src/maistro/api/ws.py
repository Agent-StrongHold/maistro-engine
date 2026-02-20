"""WebSocket streaming for real-time task progress."""

from __future__ import annotations

import asyncio
import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from maistro.config.settings import Settings, get_settings
from maistro.tasks.queue import TaskQueue, get_task_queue

router = APIRouter(tags=["streaming"])


def _verify_ws_token(token: str | None, settings: Settings) -> bool:
    """Verify WebSocket auth token against configured API keys."""
    if not settings.api_keys:
        return True  # Dev mode
    if not token:
        return False
    return any(
        hmac.compare_digest(token.encode(), key.encode())
        for key in settings.api_keys
    )


@router.websocket("/stream/{task_id}")
async def stream_task(
    websocket: WebSocket,
    task_id: str,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    token: str | None = Query(None),
) -> None:
    settings = get_settings()
    if not _verify_ws_token(token, settings):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    try:
        last_status = None
        last_progress = None

        while True:
            task = queue.get(task_id)
            if task is None:
                await websocket.send_json({"error": "Task not found"})
                break

            # Send update if status or progress changed
            current_status = task.status.value
            current_progress = task.progress.current if task.progress else ""

            if current_status != last_status or current_progress != last_progress:
                await websocket.send_json({
                    "task_id": task_id,
                    "phase": task.phase,
                    "status": current_status,
                    "message": current_progress,
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                last_status = current_status
                last_progress = current_progress

            # Stop streaming if task is terminal
            if current_status in ("completed", "failed", "cancelled"):
                if task.result:
                    await websocket.send_json({
                        "task_id": task_id,
                        "phase": "done",
                        "result": task.result.model_dump(),
                        "timestamp": datetime.now(UTC).isoformat(),
                    })
                break

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass
