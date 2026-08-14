from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from maistro.graph.definitions import Graph
from maistro.runs.lifecycle import (
    transition_attempt,
    transition_node_run,
    transition_run,
)
from maistro.runs.model import (
    TERMINAL_RUN_STATUSES,
    Attempt,
    AttemptStatus,
    GraphSnapshot,
    NodeRun,
    Run,
    RunStatus,
)


class RunNotFound(KeyError):
    pass


class NodeRunNotFound(KeyError):
    pass


class AttemptNotFound(KeyError):
    pass


class RunIntegrityError(ValueError):
    pass


class ActiveAttemptExists(RunIntegrityError):
    pass


@runtime_checkable
class RunStore(Protocol):
    async def create_run(
        self,
        graph: Graph,
        *,
        parent_run_id: str | None = None,
        parent_node_run_id: str | None = None,
        allow_cross_project: bool = False,
        persona_id: str | None = None,
        actor_principal_id: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> Run: ...

    async def get_run(self, run_id: str) -> Run | None: ...

    async def transition_run(
        self,
        run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> Run: ...

    async def create_node_run(self, run_id: str, *, node_id: str) -> NodeRun: ...

    async def list_node_runs(self, run_id: str) -> list[NodeRun]: ...

    async def transition_node_run(
        self,
        node_run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> NodeRun: ...

    async def create_attempt(
        self,
        node_run_id: str,
        *,
        runtime_id: str = "python",
        executor_id: str = "",
        deadline_at: datetime | None = None,
        resume_checkpoint_id: str | None = None,
    ) -> Attempt: ...

    async def list_attempts(self, node_run_id: str) -> list[Attempt]: ...

    async def transition_attempt(
        self,
        attempt_id: str,
        target: AttemptStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
        metrics: dict[str, object] | None = None,
    ) -> Attempt: ...


class InMemoryRunStore:
    """Reference lifecycle store for canonical Run -> NodeRun -> Attempt state."""

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._node_runs: dict[str, NodeRun] = {}
        self._attempts: dict[str, Attempt] = {}

    async def create_run(
        self,
        graph: Graph,
        *,
        parent_run_id: str | None = None,
        parent_node_run_id: str | None = None,
        allow_cross_project: bool = False,
        persona_id: str | None = None,
        actor_principal_id: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> Run:
        if parent_node_run_id is not None and parent_run_id is None:
            raise RunIntegrityError("parent_node_run_id requires parent_run_id")

        if parent_run_id is not None:
            parent = self._require_run(parent_run_id)
            if parent.workspace_id != graph.workspace_id:
                raise RunIntegrityError("child Run cannot cross Workspace boundaries")
            if parent.project_id != graph.project_id and not allow_cross_project:
                raise RunIntegrityError(
                    "child Run cannot implicitly cross Project boundaries; "
                    "caller must authorize and request the destination Project"
                )
            if parent_node_run_id is not None:
                parent_node_run = self._require_node_run(parent_node_run_id)
                if parent_node_run.run_id != parent_run_id:
                    raise RunIntegrityError(
                        "parent_node_run_id does not belong to parent_run_id"
                    )

        run = Run(
            workspace_id=graph.workspace_id,
            project_id=graph.project_id,
            graph=GraphSnapshot.from_graph(graph.model_copy(deep=True)),
            parent_run_id=parent_run_id,
            parent_node_run_id=parent_node_run_id,
            persona_id=persona_id,
            actor_principal_id=actor_principal_id,
            provenance=dict(provenance or {}),
        )
        self._runs[run.run_id] = run
        return run.model_copy(deep=True)

    async def get_run(self, run_id: str) -> Run | None:
        run = self._runs.get(run_id)
        return run.model_copy(deep=True) if run is not None else None

    async def transition_run(
        self,
        run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> Run:
        run = self._require_run(run_id)
        updated = transition_run(run, target, at=at, result=result, error=error)
        self._runs[run_id] = updated
        return updated.model_copy(deep=True)

    async def create_node_run(self, run_id: str, *, node_id: str) -> NodeRun:
        run = self._require_run(run_id)
        if run.status in TERMINAL_RUN_STATUSES:
            raise RunIntegrityError("cannot create NodeRun under a terminal Run")

        graph = run.graph.materialize()
        if not any(node.node_id == node_id for node in graph.nodes):
            raise RunIntegrityError(
                f"node_id {node_id!r} is not present in the Run Graph snapshot"
            )

        ordinal = 1 + sum(
            node_run.run_id == run_id for node_run in self._node_runs.values()
        )
        node_run = NodeRun(run_id=run_id, node_id=node_id, ordinal=ordinal)
        self._node_runs[node_run.node_run_id] = node_run
        return node_run.model_copy(deep=True)

    async def list_node_runs(self, run_id: str) -> list[NodeRun]:
        self._require_run(run_id)
        node_runs = [
            node_run.model_copy(deep=True)
            for node_run in self._node_runs.values()
            if node_run.run_id == run_id
        ]
        node_runs.sort(key=lambda item: item.ordinal)
        return node_runs

    async def transition_node_run(
        self,
        node_run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> NodeRun:
        node_run = self._require_node_run(node_run_id)
        updated = transition_node_run(
            node_run,
            target,
            at=at,
            result=result,
            error=error,
        )
        self._node_runs[node_run_id] = updated
        return updated.model_copy(deep=True)

    async def create_attempt(
        self,
        node_run_id: str,
        *,
        runtime_id: str = "python",
        executor_id: str = "",
        deadline_at: datetime | None = None,
        resume_checkpoint_id: str | None = None,
    ) -> Attempt:
        node_run = self._require_node_run(node_run_id)
        if node_run.status in TERMINAL_RUN_STATUSES:
            raise RunIntegrityError("cannot create Attempt under a terminal NodeRun")

        existing = [
            attempt
            for attempt in self._attempts.values()
            if attempt.node_run_id == node_run_id
        ]
        if any(
            attempt.status in {AttemptStatus.CREATED, AttemptStatus.RUNNING}
            for attempt in existing
        ):
            raise ActiveAttemptExists(
                f"NodeRun {node_run_id!r} already has an active Attempt"
            )

        ordinal = max((attempt.ordinal for attempt in existing), default=0) + 1
        attempt = Attempt(
            node_run_id=node_run_id,
            ordinal=ordinal,
            runtime_id=runtime_id,
            executor_id=executor_id,
            deadline_at=deadline_at,
            resume_checkpoint_id=resume_checkpoint_id,
        )
        self._attempts[attempt.attempt_id] = attempt
        return attempt.model_copy(deep=True)

    async def list_attempts(self, node_run_id: str) -> list[Attempt]:
        self._require_node_run(node_run_id)
        attempts = [
            attempt.model_copy(deep=True)
            for attempt in self._attempts.values()
            if attempt.node_run_id == node_run_id
        ]
        attempts.sort(key=lambda item: item.ordinal)
        return attempts

    async def transition_attempt(
        self,
        attempt_id: str,
        target: AttemptStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
        metrics: dict[str, object] | None = None,
    ) -> Attempt:
        attempt = self._require_attempt(attempt_id)
        updated = transition_attempt(
            attempt,
            target,
            at=at,
            result=result,
            error=error,
            metrics=metrics,
        )
        self._attempts[attempt_id] = updated
        return updated.model_copy(deep=True)

    def _require_run(self, run_id: str) -> Run:
        run = self._runs.get(run_id)
        if run is None:
            raise RunNotFound(run_id)
        return run

    def _require_node_run(self, node_run_id: str) -> NodeRun:
        node_run = self._node_runs.get(node_run_id)
        if node_run is None:
            raise NodeRunNotFound(node_run_id)
        return node_run

    def _require_attempt(self, attempt_id: str) -> Attempt:
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            raise AttemptNotFound(attempt_id)
        return attempt


__all__ = [
    "ActiveAttemptExists",
    "AttemptNotFound",
    "InMemoryRunStore",
    "NodeRunNotFound",
    "RunIntegrityError",
    "RunNotFound",
    "RunStore",
]
