"""EngineService — singleton that wires maistro-core into hive-conductor.

Exposes two surfaces:
  chat   — route_request() delegates to MaistroCoreBridge (Container.route_request())
  tasks  — submit_task() / get_task() / list_tasks() / iter_task_events() via TaskQueue
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config import Settings

# Status mapping: maistro TaskStatus → hive Mission status
_STATUS_MAP = {
    "queued": "pending",
    "planning": "running",
    "coding": "running",
    "reviewing": "running",
    "testing": "running",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "failed",
}

_TERMINAL = frozenset({"completed", "failed"})


class TaskRecord:
    """Thin view of a maistro TaskResponse as used by hive-conductor routes."""

    def __init__(self, task: Any) -> None:
        self._task = task

    @property
    def id(self) -> str:
        return self._task.task_id

    @property
    def name(self) -> str:
        return self._task.description[:60]

    @property
    def description(self) -> str:
        return self._task.description

    @property
    def mission_status(self) -> str:
        return _STATUS_MAP.get(str(self._task.status), "pending")

    @property
    def progress(self) -> float:
        p = self._task.progress
        if p.subtasks:
            return p.completed / p.subtasks
        if self.mission_status == "completed":
            return 1.0
        return 0.0

    @property
    def current_step(self) -> str:
        return self._task.progress.current or self._task.phase or ""

    @property
    def created_at(self) -> datetime:
        return self._task.created_at

    @property
    def started_at(self) -> datetime | None:
        return self._task.started_at

    @property
    def completed_at(self) -> datetime | None:
        return self._task.completed_at


class EngineService:
    """Singleton service bridging hive-conductor UI to maistro-core execution."""

    def __init__(self) -> None:
        self._agent_port: Any = None
        self._queue: Any = None
        self._runner: Any = None
        self._configured = False

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def start(self, settings: Settings) -> None:
        from adapters.maistro_core import MaistroCoreBridge, StubAgentPort

        if settings.maistro_router_api_key:
            bridge = MaistroCoreBridge()
            try:
                await bridge.start(settings)
                self._agent_port = bridge
                self._configured = True
            except Exception as exc:
                import logging
                logging.getLogger("hive.engine").warning(
                    "maistro-core bridge failed to start (%s) — falling back to stub", exc
                )
                self._agent_port = StubAgentPort()
        else:
            self._agent_port = StubAgentPort()

        try:
            from maistro.agents.conductor import run_task
            from maistro.tasks.queue import TaskQueue
            from maistro.tasks.runner import TaskRunner

            self._queue = TaskQueue()
            self._runner = TaskRunner(self._queue, executor=run_task)
            await self._runner.start()
        except Exception as exc:
            import logging
            logging.getLogger("hive.engine").warning(
                "TaskRunner failed to start (%s) — mission dispatch disabled", exc
            )

        self._wire_reactor()

    async def stop(self) -> None:
        if self._runner is not None:
            with contextlib.suppress(Exception):
                await self._runner.stop()

    def _wire_reactor(self) -> None:
        try:
            from services.foundation import get_foundation

            f = get_foundation()
            if not f.reactor_available or f.reactor is None:
                return

            async def on_task_event(event: Any) -> None:
                import logging
                logging.getLogger("hive.engine.reactor").info(
                    "Reactor event: %s", getattr(event, "type", "unknown")
                )

            f.reactor.on("task.*", on_task_event)  # type: ignore[union-attr]
        except Exception as exc:
            import logging
            logging.getLogger("hive.engine").debug(
                "Reactor wiring skipped (%s)", exc
            )

    # --- Chat surface ---

    async def route_request(
        self,
        messages: list[dict[str, Any]],
        *,
        session_id: str | None = None,
        intent_hint: str = "",
    ) -> dict[str, Any]:
        return await self._agent_port.route(
            messages,
            session_id=session_id,
            intent_hint=intent_hint,
        )

    # --- Task/Mission surface ---

    async def submit_task(self, name: str, description: str) -> TaskRecord:
        if self._queue is None:
            raise RuntimeError("TaskQueue not available")
        from maistro.tasks.models import TaskCreate

        task = await self._queue.submit(TaskCreate(description=description or name))
        return TaskRecord(task)

    def get_task(self, task_id: str) -> TaskRecord | None:
        if self._queue is None:
            return None
        task = self._queue.get(task_id)
        return TaskRecord(task) if task is not None else None

    def list_tasks(self) -> list[TaskRecord]:
        if self._queue is None:
            return []
        items, _ = self._queue.list_tasks(limit=200)
        return [TaskRecord(t) for t in items]

    async def iter_task_events(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
        if self._queue is None:
            return
        while True:
            task = self._queue.get(task_id)
            if task is None:
                return
            rec = TaskRecord(task)
            yield {
                "id": rec.id,
                "status": rec.mission_status,
                "progress": rec.progress,
                "current_step": rec.current_step,
            }
            if rec.mission_status in _TERMINAL:
                return
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._queue.wait_for_update(task_id), timeout=30.0)


# Module-level singleton
_singleton: EngineService | None = None


def get_engine() -> EngineService:
    if _singleton is None:
        raise RuntimeError("EngineService not started — call start_engine() at app lifespan")
    return _singleton


async def start_engine(settings: Settings) -> EngineService:
    global _singleton
    _singleton = EngineService()
    await _singleton.start(settings)
    return _singleton


async def stop_engine() -> None:
    global _singleton
    if _singleton is not None:
        await _singleton.stop()
        _singleton = None
