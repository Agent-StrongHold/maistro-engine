"""EngineService — singleton that wires maistro-core into hive-conductor.

Exposes two surfaces:
  chat   — route_request() delegates to MaistroCoreBridge
  tasks  — submit_task() / get_task() / list_tasks() / iter_task_events() via TaskQueue
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Any

logger = logging.getLogger("hive.engine")

if TYPE_CHECKING:
    from config import Settings

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

    @property
    def error(self) -> str | None:
        result = self._task.result
        return result.error if result is not None else None


class EngineService:
    def __init__(self) -> None:
        self._agent_port: Any = None
        self._queue: Any = None
        self._runner: Any = None
        self._configured = False
        self._capabilities: Any = None

    @property
    def is_configured(self) -> bool:
        return self._configured

    @property
    def capabilities(self) -> Any:
        """The CapabilityRegistry backing the API. Sourced from the core Container
        when configured, else a standalone canonical registry (stub/dev mode)."""
        if self._capabilities is None:
            from maistro.capabilities.bootstrap import default_capability_registry

            self._capabilities = default_capability_registry()
        return self._capabilities

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
                    "maistro-core bridge failed (%s) — falling back to stub", exc
                )
                self._agent_port = StubAgentPort()
        else:
            self._agent_port = StubAgentPort()

        self._wire_capabilities(settings)

        try:
            import os

            from maistro.tasks.queue import TaskQueue
            from maistro.tasks.runner import TaskRunner

            pm_mode = (
                os.getenv("MAISTRO_POC_MODE", os.getenv("HIVE_POC_MODE", "")).strip().lower()
                == "pm"
            )
            if pm_mode:
                from maistro.agents.pm_runner import run_pm_task

                executor = run_pm_task
                # pm_runner makes real Claude calls through the JedAI gateway
                # for LLM-reasoning capabilities and short-circuits to
                # source='no_data' for data tools that need PATs (jira) or
                # Chromium (browser-use) when those aren't wired yet.
                logger.info(
                    "TaskRunner using PM runner — real LLM via JedAI gateway "
                    "(source='no_data' for Jira/Airtable/web until PATs set)"
                )
            else:
                from maistro.agents.conductor import run_task

                executor = run_task
                logger.info("TaskRunner using engineering conductor executor")

            self._queue = TaskQueue()
            self._runner = TaskRunner(self._queue, executor=executor)
            await self._runner.start()
            if pm_mode:
                from maistro.agents.catalog import AgentCatalog
                from maistro.agents.pm_fleet import register_pm_fleet

                catalog = AgentCatalog()
                register_pm_fleet(catalog)
                self._pm_catalog = catalog
        except Exception as exc:
            import logging

            logging.getLogger("hive.engine").warning(
                "TaskRunner failed (%s) — mission dispatch disabled", exc
            )

    def _wire_capabilities(self, settings: Settings) -> None:
        """Source the registry (Container when configured, else canonical) and
        register host-health providers + apply activation. Never crashes startup."""
        container = getattr(self._agent_port, "container", None)
        if container is not None and getattr(container, "capabilities", None) is not None:
            self._capabilities = container.capabilities
        else:
            from maistro.capabilities.bootstrap import default_capability_registry

            self._capabilities = default_capability_registry()

        try:
            import stores

            from services.capabilities_wiring import wire_capabilities
            from services.foundation import get_foundation

            try:
                vault = get_foundation().vault
            except Exception:
                vault = None

            wire_capabilities(
                self._capabilities,
                settings_model=stores.settings,
                config=settings,
                vault=vault,
            )
        except Exception as exc:
            logger.warning("capability wiring failed (%s) — slots use baselines/SAFE_NOOP", exc)

    async def stop(self) -> None:
        if self._runner is not None:
            with contextlib.suppress(Exception):
                await self._runner.stop()

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

    async def submit_task(
        self,
        name: str,
        description: str,
        *,
        user_id: str = "",
        task_type: str | None = None,
        agent_id: str | None = None,
        capability: str | None = None,
        program_context: dict | None = None,
    ) -> TaskRecord:
        if self._queue is None:
            raise RuntimeError("TaskQueue not available")
        from maistro.agents.pm_capabilities import is_gated, normalize_capability
        from maistro.tasks.models import TaskCreate

        cap = normalize_capability(capability or "")
        pctx_probe = program_context if isinstance(program_context, dict) else {}
        if is_gated(cap) and not pctx_probe.get("confirmed"):
            raise ValueError(
                f"Capability {cap!r} must use the work-item draft flow (POST /v1/work-items/suggest → confirm)"
            )

        pctx = program_context
        if pctx is None and user_id:
            try:
                from maistro.agents.program_context import context_for_task
                from services import program_store as prog

                pctx = context_for_task(prog.get_context(user_id))
            except Exception:
                pctx = None

        task = await self._queue.submit(
            TaskCreate(
                description=description or name,
                task_type=task_type,
                agent_id=agent_id,
                capability=capability,
                program_context=pctx,
            ),
            user_id=user_id,
        )
        logger.info(
            "task_submitted id=%s user=%s agent=%s capability=%s type=%s",
            task.task_id,
            user_id or "-",
            agent_id or "-",
            capability or "-",
            task_type or "-",
        )
        return TaskRecord(task)

    def get_task(self, task_id: str, *, user_id: str | None = None) -> TaskRecord | None:
        if self._queue is None:
            return None
        task = self._queue.get(task_id, user_id=user_id)
        return TaskRecord(task) if task is not None else None

    def list_tasks(self, *, user_id: str | None = None) -> list[TaskRecord]:
        if self._queue is None:
            return []
        items, _ = self._queue.list_tasks(limit=200, user_id=user_id)
        return [TaskRecord(t) for t in reversed(items)]

    def delete_task(self, task_id: str) -> bool:
        if self._queue is None:
            return False
        return self._queue.remove(task_id)

    def clear_tasks(self, *, status: str | None = None) -> int:
        if self._queue is None:
            return 0
        from maistro.tasks.models import TaskStatus

        filter_status: TaskStatus | None = None
        if status == "failed":
            filter_status = TaskStatus.FAILED
        elif status == "completed":
            filter_status = TaskStatus.COMPLETED
        return self._queue.remove_where(status=filter_status)

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
