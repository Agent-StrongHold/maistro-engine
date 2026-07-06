"""`HarnessAdapter` (maistro.graph.harness) wrapping an RSI cycle.

`RsiCycle.run(baseline, candidate, available_models)` is a single long-running
coroutine — clone, branch, patch, test, evaluate, battle — rather than its own
dispatch/poll primitive. This adapter is the seam: `dispatch` starts it as a
background asyncio task and returns immediately (the calling DAG node then
pauses, same as every other harness); `poll` checks whether it has finished
and translates an `RsiCycleResult` into a `HarnessResult`; `cancel` tears down
an in-flight attempt.

A dispatched RSI cycle is exactly the kind of self-modifying work
`maistro_rsi.quarantine` exists to gate — this adapter dispatches the cycle,
it does not itself decide whether the cycle's diff is safe to promote; that's
`RsiCycle.run`'s own `quarantine_check` plumbing (see `runner.py`/`SPEC.md`).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import structlog

from maistro.graph.harness import HarnessHandle, HarnessRequest, HarnessResult
from maistro_evolve.types import PipelineGenome

if TYPE_CHECKING:
    from maistro_rsi.runner import RsiCycleResult

logger = structlog.get_logger()


@runtime_checkable
class RsiCycleRunner(Protocol):
    """What the adapter needs from an RSI cycle — `RsiCycle.run` satisfies this
    structurally, but depending on the protocol (not the concrete class) keeps
    this module free of the sandbox/git/tournament import chain and makes the
    adapter trivially testable with a fake."""

    async def run(
        self,
        baseline: PipelineGenome,
        candidate: PipelineGenome,
        available_models: list[str],
    ) -> RsiCycleResult: ...


@dataclass
class _InFlight:
    task: asyncio.Task[RsiCycleResult]
    deadline: float


def _cancel(task: asyncio.Task[RsiCycleResult]) -> None:
    """Cancel a task whose result nobody will ever await directly, and make
    sure asyncio doesn't log an "exception was never retrieved" warning for
    whatever the cancelled coroutine unwinds into."""
    if task.done():
        return
    task.cancel()
    task.add_done_callback(_drain)


def _drain(task: asyncio.Task[RsiCycleResult]) -> None:
    if not task.cancelled():
        task.exception()  # retrieve + discard


def _result_to_harness_result(handle_id: str, result: RsiCycleResult) -> HarnessResult:
    return HarnessResult(
        handle_id=handle_id,
        success=result.improved,
        output=(
            f"run_id={result.run_id} tests_passed={result.branch_result.tests_passed} "
            f"benchmarks_won={result.benchmarks_won}/{len(result.battles)}"
        ),
        metadata={
            "run_id": result.run_id,
            "model_used": result.model_used,
            "tests_passed": result.branch_result.tests_passed,
            "benchmarks_won": result.benchmarks_won,
            "battles_total": len(result.battles),
            "pr_url": result.branch_result.pr_url,
            "improved": result.improved,
        },
    )


class RsiCycleHarnessAdapter:
    """Dispatches an RSI cycle as a background task.

    `cycle` is a single, reusable `RsiCycleRunner` (`RsiCycle` in production)
    "recipe" object — `run()` mints its own `run_id`/workspace per call, so
    nothing about it is per-dispatch state and one instance safely serves
    many concurrent dispatches.

    Each `HarnessRequest.context` must carry `baseline_genome` and
    `candidate_genome` (`PipelineGenome` instances) and `available_models`
    (`list[str]`) — the actual arguments `RsiCycle.run` needs. Missing any of
    these is a caller error, not a runtime failure to gate silently, so
    `dispatch` raises rather than swallowing it.
    """

    def __init__(self, cycle: RsiCycleRunner) -> None:
        self._cycle = cycle
        self._in_flight: dict[str, _InFlight] = {}

    async def dispatch(self, request: HarnessRequest) -> HarnessHandle:
        baseline = request.context.get("baseline_genome")
        candidate = request.context.get("candidate_genome")
        available_models = request.context.get("available_models")
        if not isinstance(baseline, PipelineGenome) or not isinstance(candidate, PipelineGenome):
            raise ValueError(
                "RsiCycleHarnessAdapter requires context['baseline_genome'] and "
                "context['candidate_genome'] to be PipelineGenome instances"
            )
        if not isinstance(available_models, list):
            raise ValueError(
                "RsiCycleHarnessAdapter requires context['available_models']: list[str]"
            )

        handle_id = uuid.uuid4().hex[:12]
        task = asyncio.create_task(self._cycle.run(baseline, candidate, available_models))
        self._in_flight[handle_id] = _InFlight(
            task=task, deadline=time.monotonic() + request.timeout_seconds
        )
        await logger.ainfo("rsi_harness_dispatched", handle_id=handle_id)
        return HarnessHandle(handle_id=handle_id, harness_type="rsi_cycle")

    async def poll(self, handle: HarnessHandle) -> HarnessResult | None:
        in_flight = self._in_flight.get(handle.handle_id)
        if in_flight is None:
            return HarnessResult(
                handle_id=handle.handle_id, success=False, output="", error="unknown handle"
            )

        if not in_flight.task.done():
            if time.monotonic() < in_flight.deadline:
                return None
            _cancel(in_flight.task)
            del self._in_flight[handle.handle_id]
            return HarnessResult(
                handle_id=handle.handle_id, success=False, output="", error="timed out"
            )

        del self._in_flight[handle.handle_id]

        if in_flight.task.cancelled():
            return HarnessResult(
                handle_id=handle.handle_id, success=False, output="", error="cancelled"
            )

        exc = in_flight.task.exception()
        if exc is not None:
            await logger.awarning("rsi_harness_failed", handle_id=handle.handle_id, error=str(exc))
            return HarnessResult(
                handle_id=handle.handle_id, success=False, output="", error=str(exc)
            )

        return _result_to_harness_result(handle.handle_id, in_flight.task.result())

    async def cancel(self, handle: HarnessHandle) -> None:
        in_flight = self._in_flight.pop(handle.handle_id, None)
        if in_flight is not None:
            _cancel(in_flight.task)
