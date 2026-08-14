"""Canonical event envelope and append-only persistence contract.

The envelope carries stable execution correlation IDs while leaving domain payloads
opaque. Sequence numbers are allocated by the store within a logical stream:
Run when ``run_id`` is present, otherwise Workspace, otherwise the system stream.
This gives execution consumers deterministic per-Run ordering without claiming a
meaningful global event order.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import uuid4

if TYPE_CHECKING:
    import aiosqlite


@dataclass(frozen=True)
class EventEnvelope:
    """Immutable canonical event envelope.

    ``sequence`` is ``None`` until the event is durably appended. Stores assign a
    monotonically increasing sequence within :attr:`stream_id`. Domain-specific
    event data belongs in ``payload`` rather than additional envelope fields.
    """

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    sequence: int | None = None
    timestamp: float = field(default_factory=time.time)
    workspace_id: str = ""
    project_id: str = ""
    run_id: str = ""
    node_run_id: str = ""
    attempt_id: str = ""
    invocation_id: str = ""
    session_id: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    source: str = ""
    actor_id: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def stream_id(self) -> str:
        """Return the ordering scope for this event."""
        if self.run_id:
            return f"run:{self.run_id}"
        if self.workspace_id:
            return f"workspace:{self.workspace_id}"
        return "system"

    def to_dict(self) -> dict[str, Any]:
        """Return a serialization-ready copy of the envelope."""
        return asdict(self)


@runtime_checkable
class EventStore(Protocol):
    """Append-only persistence for canonical :class:`EventEnvelope` objects."""

    async def append(self, event: EventEnvelope) -> EventEnvelope:
        """Persist ``event`` idempotently and assign its stream sequence."""
        ...

    async def get(self, event_id: str) -> EventEnvelope | None:
        """Return one event by its stable event ID."""
        ...

    async def list_stream(
        self,
        stream_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[EventEnvelope]:
        """Return one stream in ascending sequence order."""
        ...


class InMemoryEventStore:
    """Concurrency-safe in-memory EventStore for tests and local execution."""

    def __init__(self) -> None:
        self._events_by_id: dict[str, EventEnvelope] = {}
        self._streams: dict[str, list[EventEnvelope]] = {}
        self._lock = asyncio.Lock()

    async def append(self, event: EventEnvelope) -> EventEnvelope:
        async with self._lock:
            existing = self._events_by_id.get(event.event_id)
            if existing is not None:
                return existing
            if event.sequence is not None:
                raise ValueError("sequence is store-assigned and must be None on append")

            stream = self._streams.setdefault(event.stream_id, [])
            persisted = replace(event, sequence=len(stream) + 1)
            stream.append(persisted)
            self._events_by_id[persisted.event_id] = persisted
            return persisted

    async def get(self, event_id: str) -> EventEnvelope | None:
        return self._events_by_id.get(event_id)

    async def list_stream(
        self,
        stream_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[EventEnvelope]:
        if limit < 1:
            return []
        return [
            event
            for event in self._streams.get(stream_id, [])
            if event.sequence is not None and event.sequence > after_sequence
        ][:limit]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS canonical_event_log (
    event_id TEXT PRIMARY KEY,
    stream_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    node_run_id TEXT NOT NULL DEFAULT '',
    attempt_id TEXT NOT NULL DEFAULT '',
    invocation_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    causation_id TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{}',
    provenance TEXT NOT NULL DEFAULT '{}',
    UNIQUE(stream_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_canonical_event_stream
    ON canonical_event_log (stream_id, sequence);
CREATE INDEX IF NOT EXISTS idx_canonical_event_run
    ON canonical_event_log (run_id, sequence);
"""


class SqliteEventStore:
    """SQLite implementation of the canonical EventStore contract.

    Sequence allocation and insertion are serialized by an in-process lock. The
    table-level ``UNIQUE(stream_id, sequence)`` constraint also protects the
    ordering invariant if another writer violates that assumption.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        self._lock = asyncio.Lock()

    async def ensure_schema(self) -> None:
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def append(self, event: EventEnvelope) -> EventEnvelope:
        async with self._lock:
            existing = await self.get(event.event_id)
            if existing is not None:
                return existing
            if event.sequence is not None:
                raise ValueError("sequence is store-assigned and must be None on append")

            cursor = await self._conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM canonical_event_log WHERE stream_id = ?",
                (event.stream_id,),
            )
            row = await cursor.fetchone()
            sequence = int(row[0]) if row is not None else 1
            persisted = replace(event, sequence=sequence)
            await self._conn.execute(
                """INSERT INTO canonical_event_log (
                    event_id, stream_id, sequence, type, timestamp,
                    workspace_id, project_id, run_id, node_run_id, attempt_id,
                    invocation_id, session_id, correlation_id, causation_id,
                    source, actor_id, payload, provenance
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    persisted.event_id,
                    persisted.stream_id,
                    persisted.sequence,
                    persisted.type,
                    persisted.timestamp,
                    persisted.workspace_id,
                    persisted.project_id,
                    persisted.run_id,
                    persisted.node_run_id,
                    persisted.attempt_id,
                    persisted.invocation_id,
                    persisted.session_id,
                    persisted.correlation_id,
                    persisted.causation_id,
                    persisted.source,
                    persisted.actor_id,
                    json.dumps(persisted.payload),
                    json.dumps(persisted.provenance),
                ),
            )
            await self._conn.commit()
            return persisted

    async def get(self, event_id: str) -> EventEnvelope | None:
        cursor = await self._conn.execute(
            "SELECT * FROM canonical_event_log WHERE event_id = ?",
            (event_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_event(tuple(row)) if row is not None else None

    async def list_stream(
        self,
        stream_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[EventEnvelope]:
        if limit < 1:
            return []
        cursor = await self._conn.execute(
            """SELECT * FROM canonical_event_log
               WHERE stream_id = ? AND sequence > ?
               ORDER BY sequence ASC LIMIT ?""",
            (stream_id, after_sequence, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_event(tuple(row)) for row in rows]

    @staticmethod
    def _row_to_event(row: tuple[Any, ...]) -> EventEnvelope:
        return EventEnvelope(
            event_id=row[0],
            sequence=row[2],
            type=row[3],
            timestamp=row[4],
            workspace_id=row[5],
            project_id=row[6],
            run_id=row[7],
            node_run_id=row[8],
            attempt_id=row[9],
            invocation_id=row[10],
            session_id=row[11],
            correlation_id=row[12],
            causation_id=row[13],
            source=row[14],
            actor_id=row[15],
            payload=json.loads(row[16]),
            provenance=json.loads(row[17]),
        )
