"""WebSocket routes for real-time task/mission/DAG streaming."""

from __future__ import annotations

import stores
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


@router.websocket("/tasks/{task_id}")
async def stream_task(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    try:
        from services.engine import get_engine

        engine = get_engine()
        async for event in engine.iter_task_events(task_id):
            await websocket.send_json(event)
            if event["status"] in ("completed", "failed"):
                break
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        try:
            await websocket.close()
        except Exception as _exc:
            __import__("logging").getLogger("hive.routes.ws").warning(
                "error_swallowed file=%s line=%d: %s",
                "packages/hive-conductor/backend/routes/ws.py",
                30,
                _exc,
            )
            pass


@router.websocket("/dags/{dag_id}/run")
async def stream_dag_run(websocket: WebSocket, dag_id: str) -> None:
    """Run a DAG and stream node-by-node progress over WebSocket."""
    await websocket.accept()
    if dag_id not in stores.dags:
        await websocket.send_json({"error": "dag not found"})
        await websocket.close()
        return

    dag_data = stores.dags[dag_id]
    try:
        from services.graph_runner import execute_dag_streaming

        async for event in execute_dag_streaming(dag_data):
            await websocket.send_json(event)
            if event.get("status") in ("completed", "failed"):
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await websocket.send_json({"status": "failed", "error": str(exc)})
    finally:
        try:
            await websocket.close()
        except Exception as exc:
            import logging as _logging

            _logging.getLogger("hive.ws").debug(
                "ws_close_failed (already closed): %s",
                exc,
            )
