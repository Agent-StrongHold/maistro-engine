"""DurableRunStore implementations.

`InMemoryDurableRunStore` for tests + dev; `SqliteDurableRunStore` for the
real lifecycle (survives container restart). Both implement the same
:class:`.protocol.DurableRunStore` Protocol.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .types import DurableRunRecord, RunStatus

# --- In-memory implementation ---------------------------------------------


class InMemoryDurableRunStore:
    """Thread-safe in-process store. Resets on process restart — use for
    tests + ephemeral dev runs."""

    def __init__(self) -> None:
        self._rows: dict[str, DurableRunRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: DurableRunRecord) -> DurableRunRecord:
        async with self._lock:
            if record.run_id in self._rows:
                raise ValueError(f"run_id collision: {record.run_id!r}")
            self._rows[record.run_id] = record.model_copy(deep=True)
            return self._rows[record.run_id]

    async def get(self, run_id: str) -> DurableRunRecord | None:
        return self._rows[run_id].model_copy(deep=True) if run_id in self._rows else None

    async def update(self, record: DurableRunRecord) -> DurableRunRecord:
        async with self._lock:
            existing = self._rows.get(record.run_id)
            if existing is None:
                raise KeyError(f"no such run: {record.run_id!r}")
            if record.version <= existing.version:
                raise ValueError(
                    f"version regression: stored={existing.version} incoming={record.version}"
                )
            self._rows[record.run_id] = record.model_copy(deep=True)
            return self._rows[record.run_id]

    async def list_by_status(
        self,
        status: RunStatus,
        *,
        limit: int = 100,
        project_id: str | None = None,
    ) -> list[DurableRunRecord]:
        out: list[DurableRunRecord] = []
        for r in self._rows.values():
            if r.status != status:
                continue
            if project_id and r.project_id != project_id:
                continue
            out.append(r.model_copy(deep=True))
            if len(out) >= limit:
                break
        return out

    async def list_for_project(self, project_id: str, *, limit: int = 25) -> list[DurableRunRecord]:
        runs = [r for r in self._rows.values() if r.project_id == project_id]
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return [r.model_copy(deep=True) for r in runs[:limit]]

    async def submit_hitl_answer(
        self,
        run_id: str,
        node_id: str,
        answer: dict[str, Any],
    ) -> DurableRunRecord:
        async with self._lock:
            r = self._rows.get(run_id)
            if r is None:
                raise KeyError(f"no such run: {run_id!r}")
            if r.status != RunStatus.PAUSED_HITL:
                raise ValueError(f"run {run_id!r} not paused on HITL (status={r.status})")
            if r.current_node_id != node_id:
                raise ValueError(
                    f"run {run_id!r} waiting on node {r.current_node_id!r}, not {node_id!r}"
                )
            answered = {**answer, "answered_at": datetime.now(UTC).isoformat()}
            hitl = dict(r.hitl_answers)
            hitl[node_id] = answered
            updated = r.model_copy(
                update={
                    "status": RunStatus.RUNNING,
                    "hitl_answers": hitl,
                    "version": r.version + 1,
                    "last_step_at": datetime.now(UTC),
                }
            )
            self._rows[run_id] = updated
            return updated.model_copy(deep=True)


# --- SQLite implementation ------------------------------------------------


_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS durable_runs (
    run_id          TEXT PRIMARY KEY,
    dag_id          TEXT NOT NULL,
    status          TEXT NOT NULL,
    current_node_id TEXT,
    project_id      TEXT,
    user_id         TEXT,
    started_at      TEXT NOT NULL,
    last_step_at    TEXT NOT NULL,
    finished_at     TEXT,
    resume_at       TEXT,
    version         INTEGER NOT NULL DEFAULT 0,
    record_json     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_durable_runs_status      ON durable_runs(status);
CREATE INDEX IF NOT EXISTS idx_durable_runs_project    ON durable_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_durable_runs_resume_at  ON durable_runs(resume_at);
"""


class SqliteDurableRunStore:
    """SQLite-backed durable run store.

    All `sqlite3` calls are wrapped in `asyncio.to_thread` so they don't
    block the event loop. The schema is created on construction (idempotent).
    The full :class:`DurableRunRecord` is serialized to JSON in the
    `record_json` column; the indexed columns mirror commonly-filtered fields
    so list queries don't deserialize every row.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        self._lock = asyncio.Lock()
        # Create the schema synchronously on construction — happens once at
        # service start; cheap; idempotent.
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _to_row(record: DurableRunRecord) -> dict[str, Any]:
        return {
            "run_id": record.run_id,
            "dag_id": record.dag_id,
            "status": record.status.value
            if hasattr(record.status, "value")
            else str(record.status),
            "current_node_id": record.current_node_id,
            "project_id": record.project_id,
            "user_id": record.user_id,
            "started_at": record.started_at.isoformat(),
            "last_step_at": record.last_step_at.isoformat(),
            "finished_at": record.finished_at.isoformat() if record.finished_at else None,
            "resume_at": record.resume_at.isoformat() if record.resume_at else None,
            "version": record.version,
            "record_json": record.model_dump_json(),
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DurableRunRecord:
        return DurableRunRecord.model_validate_json(row["record_json"])

    async def create(self, record: DurableRunRecord) -> DurableRunRecord:
        async with self._lock:
            try:
                return await asyncio.to_thread(_create_sync, self, record)
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"run_id collision: {record.run_id!r}") from exc

    async def get(self, run_id: str) -> DurableRunRecord | None:
        return await asyncio.to_thread(_get_sync, self, run_id)

    async def update(self, record: DurableRunRecord) -> DurableRunRecord:
        async with self._lock:
            return await asyncio.to_thread(_update_sync, self, record)

    async def list_by_status(
        self,
        status: RunStatus,
        *,
        limit: int = 100,
        project_id: str | None = None,
    ) -> list[DurableRunRecord]:
        return await asyncio.to_thread(_list_by_status_sync, self, status, limit, project_id)

    async def list_for_project(self, project_id: str, *, limit: int = 25) -> list[DurableRunRecord]:
        return await asyncio.to_thread(_list_for_project_sync, self, project_id, limit)

    async def submit_hitl_answer(
        self,
        run_id: str,
        node_id: str,
        answer: dict[str, Any],
    ) -> DurableRunRecord:
        async with self._lock:
            # Don't call self.get / self.update — those would re-acquire the
            # lock. Do the SQLite read + write directly via the sync helpers
            # (run in the thread pool to keep the loop responsive).
            def _read_and_check() -> DurableRunRecord:
                current = _get_sync(self, run_id)
                if current is None:
                    raise KeyError(f"no such run: {run_id!r}")
                if current.status != RunStatus.PAUSED_HITL:
                    raise ValueError(f"run {run_id!r} not paused on HITL (status={current.status})")
                if current.current_node_id != node_id:
                    raise ValueError(
                        f"run {run_id!r} waiting on node "
                        f"{current.current_node_id!r}, not {node_id!r}"
                    )
                return current

            current = await asyncio.to_thread(_read_and_check)
            answered = {**answer, "answered_at": datetime.now(UTC).isoformat()}
            hitl = dict(current.hitl_answers)
            hitl[node_id] = answered
            updated = current.model_copy(
                update={
                    "status": RunStatus.RUNNING,
                    "hitl_answers": hitl,
                    "version": current.version + 1,
                    "last_step_at": datetime.now(UTC),
                }
            )
            return await asyncio.to_thread(_update_sync, self, updated)


# Module-level sync helpers — these are the actual SQLite calls. Async
# wrappers hand them to `asyncio.to_thread` so the event loop stays
# responsive. They must NOT be `async def` (to_thread can't await coroutines).


def _create_sync(store: SqliteDurableRunStore, record: DurableRunRecord) -> DurableRunRecord:
    row = store._to_row(record)
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO durable_runs(
                run_id, dag_id, status, current_node_id, project_id, user_id,
                started_at, last_step_at, finished_at, resume_at, version, record_json
            ) VALUES (
                :run_id, :dag_id, :status, :current_node_id, :project_id, :user_id,
                :started_at, :last_step_at, :finished_at, :resume_at, :version, :record_json
            )
            """,
            row,
        )
        conn.commit()
    return record.model_copy(deep=True)


def _get_sync(store: SqliteDurableRunStore, run_id: str) -> DurableRunRecord | None:
    with store._connect() as conn:
        row = conn.execute("SELECT * FROM durable_runs WHERE run_id = ?", (run_id,)).fetchone()
    return store._from_row(row) if row else None


def _update_sync(store: SqliteDurableRunStore, record: DurableRunRecord) -> DurableRunRecord:
    row = store._to_row(record)
    with store._connect() as conn:
        cur = conn.execute(
            """
            UPDATE durable_runs
               SET dag_id = :dag_id,
                   status = :status,
                   current_node_id = :current_node_id,
                   project_id = :project_id,
                   user_id = :user_id,
                   started_at = :started_at,
                   last_step_at = :last_step_at,
                   finished_at = :finished_at,
                   resume_at = :resume_at,
                   version = :version,
                   record_json = :record_json
             WHERE run_id = :run_id
               AND version < :version
            """,
            row,
        )
        if cur.rowcount == 0:
            existing = conn.execute(
                "SELECT version FROM durable_runs WHERE run_id = ?",
                (record.run_id,),
            ).fetchone()
            conn.commit()
            if existing is None:
                raise KeyError(f"no such run: {record.run_id!r}")
            raise ValueError(
                f"version regression: stored={existing['version']} incoming={record.version}"
            )
        conn.commit()
    return record.model_copy(deep=True)


def _list_by_status_sync(
    store: SqliteDurableRunStore,
    status: RunStatus,
    limit: int,
    project_id: str | None,
) -> list[DurableRunRecord]:
    query = "SELECT * FROM durable_runs WHERE status = ?"
    params: list[Any] = [status.value if hasattr(status, "value") else str(status)]
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    query += " ORDER BY last_step_at DESC LIMIT ?"
    params.append(limit)
    with store._connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [store._from_row(r) for r in rows]


def _list_for_project_sync(
    store: SqliteDurableRunStore, project_id: str, limit: int
) -> list[DurableRunRecord]:
    with store._connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM durable_runs
             WHERE project_id = ?
             ORDER BY started_at DESC
             LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return [store._from_row(r) for r in rows]
