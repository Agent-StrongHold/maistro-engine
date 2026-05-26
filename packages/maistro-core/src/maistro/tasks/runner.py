"""Task runner — pulls tasks from the queue and executes them via an injected executor."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from maistro.agents.types import ConductorOutput
from maistro.constants import WORKER_POLL_TIMEOUT
from maistro.tasks.models import TaskCreate, TaskProgress, TaskResult, TaskStatus
from maistro.tasks.progress_webhook import ProgressWebhookSink, payload_from_task
from maistro.tasks.queue import TaskQueue

logger = structlog.get_logger()

# Default number of concurrent task workers
DEFAULT_MAX_WORKERS = 4

# Type for the injected executor — takes a TaskCreate, returns ConductorOutput
TaskExecutor = Callable[[TaskCreate], Coroutine[Any, Any, ConductorOutput]]


class TaskRunner:
    """Background worker pool that processes tasks from the queue.

    The executor is injected at construction time, breaking the
    bidirectional coupling between tasks/ and agents/ packages.
    """

    def __init__(
        self,
        queue: TaskQueue,
        executor: TaskExecutor,
        max_workers: int = DEFAULT_MAX_WORKERS,
        progress_webhook: ProgressWebhookSink | None = None,
    ) -> None:
        self._queue = queue
        self._executor = executor
        self._max_workers = max_workers
        self._progress_webhook = progress_webhook
        self._running = False
        self._draining = False
        self._semaphore: asyncio.Semaphore | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._active_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        self._running = True
        self._semaphore = asyncio.Semaphore(self._max_workers)
        self._worker_task = asyncio.create_task(self._dispatcher_loop())
        await logger.ainfo("task_runner_started", max_workers=self._max_workers)

    async def stop(self, drain_timeout: float = 30.0) -> None:
        """Stop the runner, waiting for in-progress tasks to drain."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

        # Drain in-progress tasks with timeout
        if self._active_tasks:
            await logger.ainfo("draining_active_tasks", count=len(self._active_tasks))
            _, pending = await asyncio.wait(self._active_tasks, timeout=drain_timeout)
            for t in pending:
                t.cancel()
            if pending:
                await logger.awarning("tasks_cancelled_on_shutdown", count=len(pending))

        if self._progress_webhook:
            await self._progress_webhook.aclose()

        await logger.ainfo("task_runner_stopped")

    async def drain(self, timeout: int = 30) -> None:
        """Graceful shutdown: stop accepting new tasks, wait for current tasks."""
        self._draining = True
        self._running = False
        await logger.ainfo(
            "task_runner_draining", timeout=timeout, active_count=len(self._active_tasks)
        )

        if self._active_tasks:
            _, pending = await asyncio.wait(self._active_tasks, timeout=timeout)
            for t in pending:
                t.cancel()
            if pending:
                await logger.awarning("task_runner_drain_timeout", cancelled=len(pending))

        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

        if self._progress_webhook:
            await self._progress_webhook.aclose()

        self._draining = False
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
            t = asyncio.create_task(self._run_with_semaphore(task_id))
            self._active_tasks.add(t)
            t.add_done_callback(self._active_tasks.discard)

    async def _run_with_semaphore(self, task_id: str) -> None:
        """Execute a task and release the semaphore when done."""
        assert self._semaphore is not None
        try:
            await self._execute_task(task_id)
        except asyncio.CancelledError:
            # Graceful shutdown — mark task as failed rather than leaving it stuck
            await self._queue.update_status(task_id, TaskStatus.FAILED)
            self._queue.set_result(task_id, TaskResult(error="Task cancelled during shutdown"))
            await self._emit_progress_webhook(task_id)
        except Exception as exc:
            await logger.aexception("task_execution_failed", task_id=task_id)
            await self._queue.update_status(task_id, TaskStatus.FAILED)
            self._queue.set_result(task_id, TaskResult(error=str(exc)))
            await self._emit_progress_webhook(task_id)
        finally:
            self._semaphore.release()

    async def _emit_progress_webhook(self, task_id: str) -> None:
        if self._progress_webhook is None:
            return
        snap = self._queue.get(task_id)
        if snap is None:
            return
        try:
            await self._progress_webhook.notify(payload_from_task(snap))
        except Exception:
            await logger.adebug(
                "progress_webhook_notify_failed",
                task_id=task_id,
                exc_info=True,
            )

    async def _execute_task(self, task_id: str) -> None:
        task = self._queue.get(task_id)
        if task is None:
            return

        async with self._queue.claim(task_id):
            # Planning phase
            await self._queue.update_status(task_id, TaskStatus.PLANNING)
            self._queue.update_progress(
                task_id, TaskProgress(current="Analyzing task and creating plan...")
            )
            await self._emit_progress_webhook(task_id)

            request = TaskCreate(
                description=task.description,
                workspace=task.workspace,
                tier=task.tier,
                task_type=task.task_type,
                agent_id=task.agent_id,
                capability=task.capability,
                program_context=task.program_context,
                user_id=task.user_id or None,
            )

            # Run conductor (single-pass: plan + code in one LLM call)
            await self._queue.update_status(task_id, TaskStatus.CODING)
            self._queue.update_progress(
                task_id, TaskProgress(current="Generating implementation...")
            )
            await self._emit_progress_webhook(task_id)

            result = await self._executor(request)

            # Phase 1 is single-pass — transition to COMPLETED or FAILED directly
            if result.success:
                await self._queue.update_status(task_id, TaskStatus.COMPLETED)
                self._queue.set_result(
                    task_id,
                    TaskResult(
                        files_changed=result.code.files_changed if result.code else [],
                    ),
                )
                await self._emit_progress_webhook(task_id)
            else:
                await self._queue.update_status(task_id, TaskStatus.FAILED)
                self._queue.set_result(
                    task_id,
                    TaskResult(error=result.final_answer),
                )
                await self._emit_progress_webhook(task_id)
