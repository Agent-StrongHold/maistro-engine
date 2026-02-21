"""Task API endpoints — CRUD for engineering tasks."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from maistro.api.auth import RequireAuth
from maistro.tasks.models import TaskCreate, TaskResponse
from maistro.tasks.queue import TaskQueue, get_task_queue

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    request: TaskCreate,
    _auth: RequireAuth,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
) -> dict[str, str]:
    task = await queue.submit(request)
    return {"task_id": task.task_id, "status": task.status.value}


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    _auth: RequireAuth,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
) -> TaskResponse:
    task = queue.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/result")
async def get_task_result(
    task_id: str,
    _auth: RequireAuth,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
) -> TaskResponse:
    task = queue.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    _auth: RequireAuth,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
) -> dict[str, bool]:
    cancelled = await queue.cancel(task_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Cannot cancel task in current state")
    return {"cancelled": True}


@router.get("")
async def list_tasks(
    _auth: RequireAuth,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    limit: int = 50,
    offset: int = 0,
) -> list[TaskResponse]:
    """List tasks with pagination."""
    return await queue.list_tasks(limit=limit, offset=offset)
