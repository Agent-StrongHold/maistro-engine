"""Minimal persistence contract required by physical Attempt execution.

Canonical Run repositories may implement much more than this seam. Durable
Graph execution needs only the already-created Run/NodeRun plus physical
Attempt lifecycle, so it can adapt its canonical checkpoint envelope without
pretending to be a second full Run repository.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from maistro.runs.model import (
    AcceptedNodeOutcome,
    Attempt,
    AttemptStatus,
    NodeRun,
    Run,
    RunStatus,
)


@runtime_checkable
class AttemptExecutionStore(Protocol):
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

    async def get_node_run(self, node_run_id: str) -> NodeRun | None: ...

    async def list_node_runs(self, run_id: str) -> list[NodeRun]: ...

    async def transition_node_run(
        self,
        node_run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        result: object | None = None,
        error: str | None = None,
        accepted_outcome: AcceptedNodeOutcome | None = None,
    ) -> NodeRun: ...

    async def create_attempt(
        self,
        node_run_id: str,
        *,
        runtime_id: str = "python",
        executor_id: str = "",
        deadline_at: datetime | None = None,
        resume_checkpoint_id: str | None = None,
        lease_holder: str | None = None,
    ) -> Attempt: ...

    async def get_attempt(self, attempt_id: str) -> Attempt | None: ...

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
        fencing_token: str | None = None,
    ) -> Attempt: ...


__all__ = ["AttemptExecutionStore"]
