"""Shared Builders runtime for Frank, Mason, Auditor, and all DAG agents."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from maistro.builders.contracts import (
    ExecutionContext,
    RunRequest,
    RunResult,
    RunStatus,
    WorkerName,
)
from maistro.builders.errors import ContextViolation

StageHandler = Callable[[RunRequest], Awaitable[RunResult]]


@dataclass
class BuildersRuntime:
    """Stateless stage dispatcher shared by all Builders DAG agents.

    Each stage handler declares its ExecutionContext at registration time.
    execute() enforces the context before calling the handler — a handler
    that tries to operate outside its declared context raises ContextViolation.
    """

    _handlers: dict[WorkerName, dict[str, StageHandler]] = field(default_factory=dict)
    _contexts: dict[tuple[WorkerName, str], ExecutionContext] = field(default_factory=dict)
    _prompts: dict[tuple[WorkerName, str, str], str] = field(default_factory=dict)
    _tools: dict[tuple[WorkerName, str], tuple[str, ...]] = field(default_factory=dict)

    def register(
        self,
        worker: WorkerName,
        stage: str,
        handler: StageHandler,
        *,
        context: ExecutionContext,
    ) -> None:
        """Register a stage handler with a required execution context."""
        self._handlers.setdefault(worker, {})[stage] = handler
        self._contexts[(worker, stage)] = context

    def declared_context(self, worker: WorkerName, stage: str) -> ExecutionContext | None:
        """Return the declared context for a registered handler, or None."""
        return self._contexts.get((worker, stage))

    def supports(self, worker: WorkerName, stage: str) -> bool:
        return stage in self._handlers.get(worker, {})

    def register_prompt(self, worker: WorkerName, stage: str, version: str, prompt: str) -> None:
        self._prompts[(worker, stage, version)] = prompt

    def load_prompt(self, worker: WorkerName, stage: str, version: str) -> str:
        return self._prompts[(worker, stage, version)]

    def register_tools(self, worker: WorkerName, stage: str, tools: tuple[str, ...]) -> None:
        self._tools[(worker, stage)] = tools

    def allowed_tools(self, worker: WorkerName, stage: str) -> tuple[str, ...]:
        return self._tools.get((worker, stage), ())

    async def execute(
        self,
        request: RunRequest,
        *,
        active_context: ExecutionContext | None = None,
    ) -> RunResult:
        """Dispatch request to its handler, enforcing the declared context.

        If active_context is provided and does not match the handler's declared
        context, ContextViolation is raised before the handler is called.
        """
        handler = self._handlers.get(request.worker, {}).get(request.stage)
        if handler is None:
            return RunResult(
                run_id=request.run_id,
                worker=request.worker,
                stage=request.stage,
                status=RunStatus.FAILED,
                summary=f"Unsupported role/stage: {request.worker.value}/{request.stage}",
            )

        declared = self._contexts.get((request.worker, request.stage))
        if active_context is not None and declared is not None and active_context != declared:
            raise ContextViolation(
                agent=request.worker.value,
                declared=declared.value,
                attempted=active_context.value,
            )

        return await handler(request)
