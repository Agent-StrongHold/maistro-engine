"""WebSocket routes for real-time task/mission streaming."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.engine import get_engine

router = APIRouter(tags=["websocket"])


@router.websocket("/tasks/{task_id}")
async def stream_task(websocket: WebSocket, task_id: str) -> None:
    """Stream task status events until the task reaches a terminal state."""
    await websocket.accept()
    engine = get_engine()
    try:
        async for event in engine.iter_task_events(task_id):
            await websocket.send_json(event)
            if event["status"] in ("completed", "failed"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
