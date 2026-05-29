"""Protocol every durable-run store implements.

In-memory and SQLite implementations live in :mod:`.stores`. Postgres-backed
implementation lands in Phase 17 (Launch deploy).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import DurableRunRecord, RunStatus


@runtime_checkable
class DurableRunStore(Protocol):
    """Persist + retrieve durable run records.

    All methods are async (the SQLite impl uses `asyncio.to_thread` so the
    in-process SQLite calls don't block the event loop).
    """

    async def create(self, record: DurableRunRecord) -> DurableRunRecord:
        """Insert a new run. Raises if `run_id` already exists."""
        ...

    async def get(self, run_id: str) -> DurableRunRecord | None:
        """Look up a run by id. Returns None if missing."""
        ...

    async def update(self, record: DurableRunRecord) -> DurableRunRecord:
        """Persist a checkpoint. Caller is responsible for incrementing
        `record.version`; the store enforces optimistic-concurrency by
        rejecting a write whose version isn't strictly greater than the
        stored row's version."""
        ...

    async def list_by_status(
        self,
        status: RunStatus,
        *,
        limit: int = 100,
        project_id: str | None = None,
    ) -> list[DurableRunRecord]:
        """List runs matching a status (used by the scheduler to find
        paused_wait runs whose resume_at has passed)."""
        ...

    async def list_for_project(self, project_id: str, *, limit: int = 25) -> list[DurableRunRecord]:
        """List recent runs for a project (UI: project detail page)."""
        ...

    async def submit_hitl_answer(
        self,
        run_id: str,
        node_id: str,
        answer: dict,
    ) -> DurableRunRecord:
        """Attach a user-supplied answer to a HITL node. Flips the run from
        `paused_hitl` to `running` so the scheduler picks it up. Raises if
        the run isn't currently waiting on that node."""
        ...
