"""Task runner — pulls tasks from the queue and executes them via the conductor."""

from __future__ import annotations

import asyncio
import contextlib

import structlog

from maistro.agents.conductor import run_task
from maistro.constants import WORKER_POLL_TIMEOUT
from maistro.tasks.models import TaskCreate, TaskProgress, TaskResult, TaskStatus
from maistro.tasks.queue import TaskQueue

logger = structlog.get_logger()

# Default number of concurrent task workers
DEFAULT_MAX_WORKERS = 4


class TaskRunner:
    """Background worker pool that processes tasks from the queue."""

    def __init__(self, queue: TaskQueue, max_workers: int = DEFAULT_MAX_WORKERS) -> None:
        self._queue = queue
        self._max_workers = max_workers
        self._running = False
        self._semaphore: asyncio.Semaphore | None = None
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._running = True
        self._semaphore = asyncio.Semaphore(self._max_workers)
        self._worker_task = asyncio.create_task(self._dispatcher_loop())
        await logger.ainfo("task_runner_started", max_workers=self._max_workers)

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
        await logger.ainfo("task_runner_stopped")

    async def _dispatcher_loop(self) -> None:
        """Dispatch tasks to workers, limited by semaphore."""
        while self._running:
            try:
                task_id = await asyncio.wait_for(
                    self._queue.next_task(), timeout=WORKER_POLL_TIMEOUT
                )
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            assert self._semaphore is not None
            await self._semaphore.acquire()
            asyncio.create_task(self._run_with_semaphore(task_id))

    async def _run_with_semaphore(self, task_id: str) -> None:
        """Execute a task and release the semaphore when done."""
        assert self._semaphore is not None
        try:
            await self._execute_task(task_id)
        except Exception:
            await logger.aexception("task_execution_failed", task_id=task_id)
        finally:
            self._semaphore.release()

    async def _execute_task(self, task_id: str) -> None:
        task = self._queue.get(task_id)
        if task is None:
            return

        async with self._queue.claim(task_id):
            # Planning phase
            self._queue.update_status(task_id, TaskStatus.PLANNING)
            self._queue.update_progress(
                task_id, TaskProgress(current="Analyzing task and creating plan...")
            )

            # Build a TaskCreate from the stored task data
            request = TaskCreate(
                description=task.description,
                workspace=task.workspace,
                tier=task.tier,
            )

            # Run the conductor
            self._queue.update_status(task_id, TaskStatus.CODING)
            self._queue.update_progress(
                task_id, TaskProgress(current="Generating implementation...")
            )

            result = await run_task(request)

            # Process result — walk through remaining phases
            if result.success:
                # CODING → REVIEWING
                self._queue.update_status(task_id, TaskStatus.REVIEWING)
                self._queue.update_progress(
                    task_id, TaskProgress(current="Reviewing implementation...")
                )

                # REVIEWING → TESTING
                self._queue.update_status(task_id, TaskStatus.TESTING)
                self._queue.update_progress(
                    task_id, TaskProgress(current="Running tests...")
                )

                # TESTING → COMPLETED
                self._queue.update_status(task_id, TaskStatus.COMPLETED)
                self._queue.set_result(
                    task_id,
                    TaskResult(
                        files_changed=result.code.files_changed if result.code else [],
                        review_score=result.review.score if result.review else None,
                    ),
                )
            else:
                self._queue.update_status(task_id, TaskStatus.FAILED)
                self._queue.set_result(
                    task_id,
                    TaskResult(error=result.final_answer),
                )
