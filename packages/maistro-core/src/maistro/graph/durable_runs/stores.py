"""Stores for canonical durable graph checkpoints."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from maistro.graph.execution_state import GraphExecutionState, thaw_json_value
from maistro.runs.lifecycle import transition_node_run, transition_run
from maistro.runs.model import RunStatus

from .types import DurableRunRecord


def _clone(record: DurableRunRecord) -> DurableRunRecord:
    return DurableRunRecord.model_validate_json(record.model_dump_json())


def _replace_state(
    state: GraphExecutionState,
    **updates: object,
) -> GraphExecutionState:
    values = state.model_dump(mode="json")
    values.update({key: thaw_json_value(value) for key, value in updates.items()})
    return GraphExecutionState.model_validate(values)


def _replace_record(record: DurableRunRecord, **updates: object) -> DurableRunRecord:
    values = record.model_dump(mode="json")
    values.update({key: thaw_json_value(value) for key, value in updates.items()})
    return DurableRunRecord.model_validate(values)


def _answer_record(
    record: DurableRunRecord,
    node_id: str,
    answer: dict[str, Any],
) -> DurableRunRecord:
    if record.run.status is not RunStatus.PAUSED:
        raise ValueError(f"run {record.run_id!r} not paused on HITL (status={record.run.status})")
    if record.active_node_id != node_id:
        raise ValueError(
            f"run {record.run_id!r} waiting on node {record.active_node_id!r}, not {node_id!r}"
        )

    answered = {**answer, "answered_at": datetime.now(UTC).isoformat()}
    metadata = dict(record.graph_state.metadata)
    answers = dict(record.hitl_answers)
    answers[node_id] = answered
    metadata["hitl_answers"] = answers
    metadata.pop("pause", None)
    graph_state = _replace_state(record.graph_state, metadata=metadata)

    node_runs = list(record.node_runs)
    for index in range(len(node_runs) - 1, -1, -1):
        node_run = node_runs[index]
        if node_run.node_id == node_id and node_run.status is RunStatus.PAUSED:
            node_runs[index] = transition_node_run(node_run, RunStatus.QUEUED)
            break

    run = transition_run(record.run, RunStatus.QUEUED)
    return _replace_record(
        record,
        run=run,
        graph_state=graph_state,
        node_runs=tuple(node_runs),
        resume_at=None,
        version=record.version + 1,
    )


class InMemoryDurableRunStore:
    """In-process optimistic-concurrency checkpoint store."""

    def __init__(self) -> None:
        self._rows: dict[str, DurableRunRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: DurableRunRecord) -> DurableRunRecord:
        async with self._lock:
            if record.run_id in self._rows:
                raise ValueError(f"run_id collision: {record.run_id!r}")
            self._rows[record.run_id] = _clone(record)
            return _clone(self._rows[record.run_id])

    async def get(self, run_id: str) -> DurableRunRecord | None:
        record = self._rows.get(run_id)
        return _clone(record) if record is not None else None

    async def update(self, record: DurableRunRecord) -> DurableRunRecord:
        async with self._lock:
            existing = self._rows.get(record.run_id)
            if existing is None:
                raise KeyError(f"no such run: {record.run_id!r}")
            if record.version <= existing.version:
                raise ValueError(
                    f"version regression: stored={existing.version} incoming={record.version}"
                )
            self._rows[record.run_id] = _clone(record)
            return _clone(self._rows[record.run_id])

    async def list_by_status(
        self,
        status: RunStatus,
        *,
        limit: int = 100,
        project_id: str | None = None,
    ) -> list[DurableRunRecord]:
        out: list[DurableRunRecord] = []
        for record in self._rows.values():
            if record.run.status is not status:
                continue
            if project_id is not None and record.run.project_id != project_id:
                continue
            out.append(_clone(record))
            if len(out) >= limit:
                break
        return out

    async def list_for_project(self, project_id: str, *, limit: int = 25) -> list[DurableRunRecord]:
        runs = [record for record in self._rows.values() if record.run.project_id == project_id]
        runs.sort(key=lambda record: record.run.created_at, reverse=True)
        return [_clone(record) for record in runs[:limit]]

    async def submit_hitl_answer(
        self,
        run_id: str,
        node_id: str,
        answer: dict[str, Any],
    ) -> DurableRunRecord:
        async with self._lock:
            record = self._rows.get(run_id)
            if record is None:
                raise KeyError(f"no such run: {run_id!r}")
            updated = _answer_record(record, node_id, answer)
            self._rows[run_id] = updated
            return _clone(updated)


_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS durable_graph_runs (
    run_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    active_node_id  TEXT,
    project_id      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    resume_at       TEXT,
    version         INTEGER NOT NULL DEFAULT 0,
    record_json     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_durable_graph_runs_status
    ON durable_graph_runs(status);
CREATE INDEX IF NOT EXISTS idx_durable_graph_runs_project
    ON durable_graph_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_durable_graph_runs_resume_at
    ON durable_graph_runs(resume_at);
"""


class SqliteDurableRunStore:
    """SQLite-backed canonical durable graph checkpoint store."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        self._lock = asyncio.Lock()
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
            "status": record.run.status.value,
            "active_node_id": record.active_node_id,
            "project_id": record.run.project_id,
            "created_at": record.run.created_at.isoformat(),
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
        return await asyncio.to_thread(
            _list_by_status_sync,
            self,
            status,
            limit,
            project_id,
        )

    async def list_for_project(self, project_id: str, *, limit: int = 25) -> list[DurableRunRecord]:
        return await asyncio.to_thread(
            _list_for_project_sync,
            self,
            project_id,
            limit,
        )

    async def submit_hitl_answer(
        self,
        run_id: str,
        node_id: str,
        answer: dict[str, Any],
    ) -> DurableRunRecord:
        async with self._lock:
            current = await asyncio.to_thread(_get_sync, self, run_id)
            if current is None:
                raise KeyError(f"no such run: {run_id!r}")
            return await asyncio.to_thread(
                _update_sync,
                self,
                _answer_record(current, node_id, answer),
            )


def _create_sync(
    store: SqliteDurableRunStore,
    record: DurableRunRecord,
) -> DurableRunRecord:
    row = store._to_row(record)
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO durable_graph_runs(
                run_id, status, active_node_id, project_id, created_at,
                resume_at, version, record_json
            ) VALUES (
                :run_id, :status, :active_node_id, :project_id, :created_at,
                :resume_at, :version, :record_json
            )
            """,
            row,
        )
        conn.commit()
    return _clone(record)


def _get_sync(
    store: SqliteDurableRunStore,
    run_id: str,
) -> DurableRunRecord | None:
    with store._connect() as conn:
        row = conn.execute(
            "SELECT * FROM durable_graph_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return store._from_row(row) if row else None


def _update_sync(
    store: SqliteDurableRunStore,
    record: DurableRunRecord,
) -> DurableRunRecord:
    row = store._to_row(record)
    with store._connect() as conn:
        cursor = conn.execute(
            """
            UPDATE durable_graph_runs
               SET status = :status,
                   active_node_id = :active_node_id,
                   project_id = :project_id,
                   created_at = :created_at,
                   resume_at = :resume_at,
                   version = :version,
                   record_json = :record_json
             WHERE run_id = :run_id
               AND version < :version
            """,
            row,
        )
        if cursor.rowcount == 0:
            existing = conn.execute(
                "SELECT version FROM durable_graph_runs WHERE run_id = ?",
                (record.run_id,),
            ).fetchone()
            conn.commit()
            if existing is None:
                raise KeyError(f"no such run: {record.run_id!r}")
            raise ValueError(
                f"version regression: stored={existing['version']} incoming={record.version}"
            )
        conn.commit()
    return _clone(record)


def _list_by_status_sync(
    store: SqliteDurableRunStore,
    status: RunStatus,
    limit: int,
    project_id: str | None,
) -> list[DurableRunRecord]:
    query = "SELECT * FROM durable_graph_runs WHERE status = ?"
    params: list[Any] = [status.value]
    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with store._connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [store._from_row(row) for row in rows]


def _list_for_project_sync(
    store: SqliteDurableRunStore,
    project_id: str,
    limit: int,
) -> list[DurableRunRecord]:
    with store._connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM durable_graph_runs
             WHERE project_id = ?
             ORDER BY created_at DESC
             LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return [store._from_row(row) for row in rows]


__all__ = ["InMemoryDurableRunStore", "SqliteDurableRunStore"]
