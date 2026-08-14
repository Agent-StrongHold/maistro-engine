from __future__ import annotations

import asyncio
from typing import Any

import pytest

from maistro.runtime import ExecutionRuntime, PythonExecutionRuntime


@pytest.mark.asyncio
async def test_executes_opaque_domain_work() -> None:
    runtime = PythonExecutionRuntime(max_concurrency=2)

    async def executor(work_item: Any, context: Any) -> dict[str, Any]:
        return {"work_item": work_item, "context": context}

    result = await runtime.execute(
        {"node": "opaque"},
        {"workspace_id": "ws-1"},
        execution_id="attempt-1",
        executor=executor,
    )

    assert result["context"]["workspace_id"] == "ws-1"
    assert isinstance(runtime, ExecutionRuntime)
    metrics = runtime.metrics()
    assert metrics.executions_started == 1
    assert metrics.executions_completed == 1
    assert metrics.active_executions == 0
    assert metrics.active_slots == 0
    assert metrics.max_rss_bytes is None or metrics.max_rss_bytes >= 0


@pytest.mark.asyncio
async def test_bounds_concurrency_and_records_wait() -> None:
    runtime = PythonExecutionRuntime(max_concurrency=1)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    async def executor(_work_item: Any, context: str) -> str:
        if context == "first":
            first_started.set()
            await release_first.wait()
        else:
            second_started.set()
        return context

    first = asyncio.create_task(
        runtime.execute(None, "first", execution_id="attempt-1", executor=executor)
    )
    await first_started.wait()
    second = asyncio.create_task(
        runtime.execute(None, "second", execution_id="attempt-2", executor=executor)
    )
    await asyncio.sleep(0)

    assert not second_started.is_set()
    assert runtime.metrics().peak_concurrency == 1

    release_first.set()
    assert await first == "first"
    assert await second == "second"
    assert runtime.metrics().scheduling_wait_seconds_total >= 0


@pytest.mark.asyncio
async def test_parallel_attempts_can_share_one_logical_run_context() -> None:
    runtime = PythonExecutionRuntime(max_concurrency=2)
    both_started = asyncio.Event()
    started = 0

    async def executor(_work_item: Any, context: dict[str, str]) -> str:
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await both_started.wait()
        return context["run_id"]

    first = asyncio.create_task(
        runtime.execute(
            "node-a",
            {"run_id": "run-1"},
            execution_id="attempt-a",
            executor=executor,
        )
    )
    second = asyncio.create_task(
        runtime.execute(
            "node-b",
            {"run_id": "run-1"},
            execution_id="attempt-b",
            executor=executor,
        )
    )

    assert await first == "run-1"
    assert await second == "run-1"
    assert runtime.metrics().peak_concurrency == 2


@pytest.mark.asyncio
async def test_cancel_propagates_to_active_execution() -> None:
    runtime = PythonExecutionRuntime()
    started = asyncio.Event()

    async def executor(_work_item: Any, _context: Any) -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(
        runtime.execute(None, None, execution_id="attempt-cancel", executor=executor)
    )
    await started.wait()

    assert await runtime.cancel("attempt-cancel") is True
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runtime.metrics().executions_cancelled == 1
    assert await runtime.cancel("attempt-cancel") is False


@pytest.mark.asyncio
async def test_deadline_is_enforced() -> None:
    runtime = PythonExecutionRuntime()

    async def executor(_work_item: Any, _context: Any) -> None:
        await asyncio.sleep(0.1)

    with pytest.raises(TimeoutError):
        await runtime.execute(
            None,
            None,
            execution_id="attempt-timeout",
            executor=executor,
            timeout_s=0.001,
        )

    assert runtime.metrics().executions_timed_out == 1


@pytest.mark.asyncio
async def test_events_receive_monotonic_sequence() -> None:
    seen: list[int] = []

    async def sink(envelope: Any) -> None:
        seen.append(envelope.sequence)

    runtime = PythonExecutionRuntime(event_sink=sink)
    first = await runtime.emit({"type": "run.started"})
    second = await runtime.emit({"type": "run.completed"})

    assert (first.sequence, second.sequence) == (1, 2)
    assert seen == [1, 2]
    assert runtime.metrics().event_sequence == 2
    assert runtime.metrics().events_emitted == 2


@pytest.mark.asyncio
async def test_event_loop_lag_sample_is_exposed_in_metrics() -> None:
    runtime = PythonExecutionRuntime()
    lag_ms = await runtime.sample_event_loop_lag(0)

    assert lag_ms >= 0
    assert runtime.metrics().event_loop_lag_ms_last == lag_ms
