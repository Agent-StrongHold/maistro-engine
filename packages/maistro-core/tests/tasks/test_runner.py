"""Tests for maistro.tasks.runner — TaskRunner (worker pool over TaskQueue)."""

from __future__ import annotations

import asyncio

import pytest

from maistro.agents.types import CodeOutput, ConductorOutput
from maistro.tasks.models import TaskCreate, TaskResult, TaskStatus
from maistro.tasks.queue import TaskQueue
from maistro.tasks.runner import TaskRunner


async def success_executor(_request: TaskCreate) -> ConductorOutput:
    return ConductorOutput(
        success=True,
        code=CodeOutput(files_changed=["a.py"], description="changed a file"),
        final_answer="done",
    )


async def failure_executor(_request: TaskCreate) -> ConductorOutput:
    return ConductorOutput(success=False, final_answer="boom")


async def raising_executor(_request: TaskCreate) -> ConductorOutput:
    raise RuntimeError("executor blew up")


class FakeWebhook:
    def __init__(self, *, fail: bool = False) -> None:
        self.notified: list[object] = []
        self.closed = False
        self._fail = fail

    async def notify(self, payload: object) -> None:
        if self._fail:
            raise RuntimeError("webhook unreachable")
        self.notified.append(payload)

    async def aclose(self) -> None:
        self.closed = True


async def make_task(queue: TaskQueue, description: str = "do thing") -> str:
    response = await queue.submit(TaskCreate(description=description))
    return response.task_id


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_sets_running_and_creates_worker_task(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)
        await runner.start()
        assert runner._running is True
        assert runner._worker_task is not None
        await runner.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_worker_task_and_closes_webhook(self) -> None:
        queue = TaskQueue()
        webhook = FakeWebhook()
        runner = TaskRunner(queue, success_executor, progress_webhook=webhook)
        await runner.start()
        await runner.stop()
        assert runner._running is False
        assert webhook.closed is True

    @pytest.mark.asyncio
    async def test_stop_drains_active_tasks_within_timeout(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)
        task_id = await make_task(queue)

        async def slow() -> None:
            await asyncio.sleep(0.05)

        t = asyncio.create_task(slow())
        runner._active_tasks.add(t)
        await runner.start()
        await runner.stop(drain_timeout=1.0)
        assert t not in runner._active_tasks or t.done()
        del task_id

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks_exceeding_drain_timeout(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)

        async def hangs() -> None:
            await asyncio.sleep(10)

        t = asyncio.create_task(hangs())
        runner._active_tasks.add(t)
        await runner.start()
        await runner.stop(drain_timeout=0.01)
        assert t.cancelled() or t.done()


class TestDrain:
    @pytest.mark.asyncio
    async def test_drain_waits_for_active_tasks_then_stops_worker(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)

        async def quick() -> None:
            await asyncio.sleep(0.01)

        t = asyncio.create_task(quick())
        runner._active_tasks.add(t)
        await runner.start()
        await runner.drain(timeout=1)
        assert runner._draining is False
        assert runner._running is False

    @pytest.mark.asyncio
    async def test_drain_cancels_tasks_exceeding_timeout(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)

        async def hangs() -> None:
            await asyncio.sleep(10)

        t = asyncio.create_task(hangs())
        runner._active_tasks.add(t)
        await runner.start()
        await runner.drain(timeout=0)
        assert t.cancelled() or t.done()

    @pytest.mark.asyncio
    async def test_drain_with_webhook_closes_it(self) -> None:
        queue = TaskQueue()
        webhook = FakeWebhook()
        runner = TaskRunner(queue, success_executor, progress_webhook=webhook)
        await runner.start()
        await runner.drain(timeout=1)
        assert webhook.closed is True


class TestDispatcherLoop:
    @pytest.mark.asyncio
    async def test_timeout_with_no_tasks_keeps_looping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("maistro.tasks.runner.WORKER_POLL_TIMEOUT", 0.01)
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)
        await runner.start()
        await asyncio.sleep(0.05)
        assert runner._worker_task is not None
        assert not runner._worker_task.done()
        await runner.stop()

    @pytest.mark.asyncio
    async def test_dispatches_submitted_task_to_executor(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)
        await runner.start()
        task_id = await make_task(queue)
        for _ in range(50):
            task = queue.get(task_id)
            assert task is not None
            if task.status == TaskStatus.COMPLETED:
                break
            await asyncio.sleep(0.02)
        await runner.stop()
        task = queue.get(task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED


class TestRunWithSemaphore:
    @pytest.mark.asyncio
    async def test_success_releases_semaphore(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)
        runner._semaphore = asyncio.Semaphore(1)
        await runner._semaphore.acquire()
        task_id = await make_task(queue)
        await runner._run_with_semaphore(task_id)
        assert runner._semaphore._value == 1
        task = queue.get(task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_exception_marks_task_failed_and_releases_semaphore(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, raising_executor)
        runner._semaphore = asyncio.Semaphore(1)
        await runner._semaphore.acquire()
        task_id = await make_task(queue)
        await runner._run_with_semaphore(task_id)
        task = queue.get(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.result is not None
        assert task.result.error == "executor blew up"
        assert runner._semaphore._value == 1

    @pytest.mark.asyncio
    async def test_cancelled_error_marks_task_failed_and_releases_semaphore(self) -> None:
        async def cancels(_request: TaskCreate) -> ConductorOutput:
            raise asyncio.CancelledError

        queue = TaskQueue()
        runner = TaskRunner(queue, cancels)
        runner._semaphore = asyncio.Semaphore(1)
        await runner._semaphore.acquire()
        task_id = await make_task(queue)
        await runner._run_with_semaphore(task_id)
        task = queue.get(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.result is not None
        assert task.result.error == "Task cancelled during shutdown"
        assert runner._semaphore._value == 1


class TestEmitProgressWebhook:
    @pytest.mark.asyncio
    async def test_no_webhook_returns_immediately(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)
        await runner._emit_progress_webhook("nonexistent")

    @pytest.mark.asyncio
    async def test_missing_task_returns_without_notifying(self) -> None:
        queue = TaskQueue()
        webhook = FakeWebhook()
        runner = TaskRunner(queue, success_executor, progress_webhook=webhook)
        await runner._emit_progress_webhook("nonexistent")
        assert webhook.notified == []

    @pytest.mark.asyncio
    async def test_notifies_webhook_with_existing_task(self) -> None:
        queue = TaskQueue()
        webhook = FakeWebhook()
        runner = TaskRunner(queue, success_executor, progress_webhook=webhook)
        task_id = await make_task(queue)
        await runner._emit_progress_webhook(task_id)
        assert len(webhook.notified) == 1

    @pytest.mark.asyncio
    async def test_webhook_failure_is_swallowed(self) -> None:
        queue = TaskQueue()
        webhook = FakeWebhook(fail=True)
        runner = TaskRunner(queue, success_executor, progress_webhook=webhook)
        task_id = await make_task(queue)
        await runner._emit_progress_webhook(task_id)  # must not raise


class TestExecuteTask:
    @pytest.mark.asyncio
    async def test_missing_task_returns_early(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)
        await runner._execute_task("nonexistent")  # must not raise

    @pytest.mark.asyncio
    async def test_success_path_sets_completed_with_files_changed(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, success_executor)
        task_id = await make_task(queue)
        await runner._execute_task(task_id)
        task = queue.get(task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.result == TaskResult(files_changed=["a.py"])

    @pytest.mark.asyncio
    async def test_success_with_no_code_defaults_files_changed_empty(self) -> None:
        async def success_no_code(_request: TaskCreate) -> ConductorOutput:
            return ConductorOutput(success=True, code=None, final_answer="done")

        queue = TaskQueue()
        runner = TaskRunner(queue, success_no_code)
        task_id = await make_task(queue)
        await runner._execute_task(task_id)
        task = queue.get(task_id)
        assert task is not None
        assert task.result is not None
        assert task.result.files_changed == []

    @pytest.mark.asyncio
    async def test_failure_path_sets_failed_with_final_answer_as_error(self) -> None:
        queue = TaskQueue()
        runner = TaskRunner(queue, failure_executor)
        task_id = await make_task(queue)
        await runner._execute_task(task_id)
        task = queue.get(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.result is not None
        assert task.result.error == "boom"
