"""In-memory task queue (Phase 1).

All task state is held in memory. A process restart loses all tasks.
Phase 2 will add PostgreSQL persistence via TaskRecord.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog

from maistro.constants import DESCRIPTION_LOG_PREVIEW_LEN
from maistro.tasks.models import TaskCreate, TaskProgress, TaskResponse, TaskResult, TaskStatus
from maistro.tasks.status import can_transition

logger = structlog.get_logger()


class TaskQueue:
    """In-memory task queue. Single-node only (Phase 1)."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskResponse] = {}
        self._pending: asyncio.Queue[str] = asyncio.Queue()

    async def submit(self, request: TaskCreate) -> TaskResponse:
        task_id = TaskResponse.new_id()
        task = TaskResponse(
            task_id=task_id,
            status=TaskStatus.QUEUED,
            description=request.description,
            workspace=request.workspace,
            tier=request.tier or 2,
            phase="queued",
            progress=TaskProgress(),
            created_at=datetime.now(UTC),
        )
        self._tasks[task_id] = task
        await self._pending.put(task_id)
        await logger.ainfo(
            "task_queued",
            task_id=task_id,
            description=request.description[:DESCRIPTION_LOG_PREVIEW_LEN],
        )
        return task

    def get(self, task_id: str) -> TaskResponse | None:
        return self._tasks.get(task_id)

    def update_status(self, task_id: str, status: TaskStatus) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning("update_status_missing_task", task_id=task_id, requested=status.value)
            return False
        if not can_transition(task.status, status):
            logger.warning(
                "invalid_state_transition",
                task_id=task_id,
                current=task.status.value,
                requested=status.value,
            )
            return False

        task.status = status
        task.phase = status.value

        if status == TaskStatus.PLANNING:
            task.started_at = datetime.now(UTC)
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            task.completed_at = datetime.now(UTC)

        return True

    def update_progress(self, task_id: str, progress: TaskProgress) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.progress = progress

    def set_result(self, task_id: str, result: TaskResult) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.result = result

    def cancel(self, task_id: str) -> bool:
        return self.update_status(task_id, TaskStatus.CANCELLED)

    async def next_task(self) -> str:
        """Block until a task is available, return its ID."""
        return await self._pending.get()

    def list_tasks(self, limit: int = 50) -> list[TaskResponse]:
        return list(self._tasks.values())[-limit:]

    @asynccontextmanager
    async def claim(self, task_id: str) -> AsyncIterator[TaskResponse]:
        """Context manager that transitions task through its lifecycle."""
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        try:
            yield task
        except Exception as exc:
            self.update_status(task_id, TaskStatus.FAILED)
            self.set_result(task_id, TaskResult(error=str(exc)))
            await logger.aexception("task_failed", task_id=task_id)
            raise


# Singleton — replaced by DI in production
_queue: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        _queue = TaskQueue()
    return _queue
