"""In-memory task queue (Phase 1).

All task state is held in memory. A process restart loses all tasks.
Phase 2 will add PostgreSQL persistence via TaskRecord.
"""

from __future__ import annotations

import asyncio
import itertools
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog

from maistro.constants import DESCRIPTION_LOG_PREVIEW_LEN
from maistro.tasks.models import TaskCreate, TaskProgress, TaskResponse, TaskResult, TaskStatus
from maistro.tasks.status import can_transition

logger = structlog.get_logger()

# Maximum number of tasks stored in memory before pruning terminal tasks
MAX_TASK_STORE_SIZE = 10_000
# Prune down to this size when limit is hit
PRUNE_TARGET = 8_000

# Terminal statuses that can be pruned
_TERMINAL = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED})


class TaskQueue:
    """In-memory task queue with event-based notification."""

    def __init__(self) -> None:
        self._tasks: OrderedDict[str, TaskResponse] = OrderedDict()
        self._pending: asyncio.Queue[str] = asyncio.Queue()
        self._events: dict[str, asyncio.Event] = {}

    def _get_event(self, task_id: str) -> asyncio.Event:
        """Get or create an asyncio.Event for a task."""
        if task_id not in self._events:
            self._events[task_id] = asyncio.Event()
        return self._events[task_id]

    async def wait_for_update(self, task_id: str) -> None:
        """Wait until the task status or progress changes."""
        event = self._get_event(task_id)
        event.clear()
        await event.wait()

    def _notify(self, task_id: str) -> None:
        """Signal waiters that a task has been updated."""
        event = self._events.get(task_id)
        if event:
            event.set()

    def _maybe_prune(self) -> None:
        """Remove oldest terminal tasks when store exceeds max size."""
        if len(self._tasks) <= MAX_TASK_STORE_SIZE:
            return
        to_remove = []
        for tid, task in self._tasks.items():
            if len(self._tasks) - len(to_remove) <= PRUNE_TARGET:
                break
            if task.status in _TERMINAL:
                to_remove.append(tid)
        for tid in to_remove:
            del self._tasks[tid]
            self._events.pop(tid, None)
        if to_remove:
            logger.info("task_store_pruned", removed=len(to_remove), remaining=len(self._tasks))

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
        self._maybe_prune()
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
        elif status in _TERMINAL:
            task.completed_at = datetime.now(UTC)

        self._notify(task_id)
        return True

    def update_progress(self, task_id: str, progress: TaskProgress) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.progress = progress
            self._notify(task_id)

    def set_result(self, task_id: str, result: TaskResult) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.result = result
            self._notify(task_id)

    def cancel(self, task_id: str) -> bool:
        return self.update_status(task_id, TaskStatus.CANCELLED)

    async def next_task(self) -> str:
        """Block until a task is available, return its ID."""
        return await self._pending.get()

    def list_tasks(
        self,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[TaskResponse], str | None]:
        """Return a page of tasks with cursor-based pagination.

        Returns (items, next_cursor) where next_cursor is None if no more pages.
        """
        if cursor:
            # Skip until we find the cursor, then take limit
            found = False
            items: list[TaskResponse] = []
            for tid, task in self._tasks.items():
                if not found:
                    if tid == cursor:
                        found = True
                    continue
                items.append(task)
                if len(items) >= limit:
                    break
        else:
            items = list(itertools.islice(self._tasks.values(), limit))

        next_cursor = items[-1].task_id if len(items) == limit else None
        return items, next_cursor

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
