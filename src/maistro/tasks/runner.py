"""Task runner — pulls tasks from the queue and executes them via the conductor."""

from __future__ import annotations

import asyncio
import contextlib

import structlog

from maistro.agents.conductor import run_task
from maistro.tasks.models import TaskCreate, TaskProgress, TaskResult, TaskStatus
from maistro.tasks.queue import TaskQueue

logger = structlog.get_logger()


class TaskRunner:
    """Background worker that processes tasks from the queue."""

    def __init__(self, queue: TaskQueue) -> None:
        self._queue = queue
        self._running = False
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        await logger.ainfo("task_runner_started")

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
        await logger.ainfo("task_runner_stopped")

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                task_id = await asyncio.wait_for(self._queue.next_task(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            await self._execute_task(task_id)

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
