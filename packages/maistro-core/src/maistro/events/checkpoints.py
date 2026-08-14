"""Canonical checkpoint contract and durable persistence.

Checkpoints are immutable execution snapshots scoped to one canonical Run. They
carry opaque state plus the canonical execution identifiers needed to resume an
Attempt without coupling persistence to the Run model implementation.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import uuid4

if TYPE_CHECKING:
    import aiosqlite

CHECKPOINT_SCHEMA_VERSION = 1
SUPPORTED_CHECKPOINT_SCHEMA_VERSIONS = frozenset({CHECKPOINT_SCHEMA_VERSION})


class CheckpointError(RuntimeError):
    """Base error for canonical checkpoint persistence and resume."""


class CheckpointNotFoundError(CheckpointError):
    """A resume reference points to a checkpoint that does not exist."""


class CheckpointVersionError(CheckpointError):
    """A checkpoint cannot be resumed by the requested schema version set."""


@dataclass(frozen=True)
class CheckpointRef:
    """Stable resume reference persisted on an Attempt or recovery record."""

    checkpoint_id: str
    schema_version: int = CHECKPOINT_SCHEMA_VERSION


@dataclass(frozen=True)
class Checkpoint:
    """Immutable checkpoint snapshot for one canonical Run.

    ``sequence`` is assigned by the store and orders checkpoints within a Run.
    ``event_sequence`` is optional and records the last canonical event known to
    be reflected in ``state`` so recovery can replay later events deterministically.
    """

    workspace_id: str
    project_id: str
    run_id: str
    state: dict[str, Any]
    checkpoint_id: str = field(default_factory=lambda: uuid4().hex)
    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    sequence: int | None = None
    event_sequence: int | None = None
    node_run_id: str = ""
    attempt_id: str = ""
    previous_checkpoint_id: str = ""
    reason: str = ""
    created_at: float = field(default_factory=time.time)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workspace_id.strip():
            raise ValueError("workspace_id must be a non-empty string")
        if not self.project_id.strip():
            raise ValueError("project_id must be a non-empty string")
        if not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if self.schema_version < 1:
            raise ValueError("schema_version must be positive")
        if self.event_sequence is not None and self.event_sequence < 1:
            raise ValueError("event_sequence must be positive when present")

    @property
    def ref(self) -> CheckpointRef:
        """Return the stable resume reference for this checkpoint."""
        return CheckpointRef(
            checkpoint_id=self.checkpoint_id,
            schema_version=self.schema_version,
        )


@runtime_checkable
class CheckpointStore(Protocol):
    """Append-only persistence for canonical Checkpoint snapshots."""

    async def append(self, checkpoint: Checkpoint) -> Checkpoint:
        """Persist a checkpoint idempotently and assign its Run sequence."""
        ...

    async def get(self, checkpoint_id: str) -> Checkpoint | None:
        """Return one checkpoint by stable ID."""
        ...

    async def latest(self, run_id: str) -> Checkpoint | None:
        """Return the most recent checkpoint for a Run."""
        ...

    async def list_run(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[Checkpoint]:
        """Return Run checkpoints in ascending sequence order."""
        ...


async def resolve_checkpoint(
    store: CheckpointStore,
    ref: CheckpointRef,
    *,
    supported_schema_versions: frozenset[int] = SUPPORTED_CHECKPOINT_SCHEMA_VERSIONS,
) -> Checkpoint:
    """Resolve and validate a resume reference.

    The reference schema version must be supported and must match the durable
    checkpoint. This prevents a caller from silently interpreting state with the
    wrong schema after deployment or migration.
    """
    if ref.schema_version not in supported_schema_versions:
        raise CheckpointVersionError(
            f"checkpoint schema version {ref.schema_version} is not supported"
        )
    checkpoint = await store.get(ref.checkpoint_id)
    if checkpoint is None:
        raise CheckpointNotFoundError(ref.checkpoint_id)
    if checkpoint.schema_version != ref.schema_version:
        raise CheckpointVersionError(
            "resume reference schema version does not match persisted checkpoint"
        )
    return checkpoint


class InMemoryCheckpointStore:
    """Concurrency-safe in-memory CheckpointStore."""

    def __init__(self) -> None:
        self._checkpoints_by_id: dict[str, Checkpoint] = {}
        self._runs: dict[str, list[Checkpoint]] = {}
        self._lock = asyncio.Lock()

    async def append(self, checkpoint: Checkpoint) -> Checkpoint:
        async with self._lock:
            existing = self._checkpoints_by_id.get(checkpoint.checkpoint_id)
            if existing is not None:
                return existing
            if checkpoint.sequence is not None:
                raise ValueError("sequence is store-assigned and must be None on append")

            run = self._runs.setdefault(checkpoint.run_id, [])
            persisted = replace(checkpoint, sequence=len(run) + 1)
            run.append(persisted)
            self._checkpoints_by_id[persisted.checkpoint_id] = persisted
            return persisted

    async def get(self, checkpoint_id: str) -> Checkpoint | None:
        return self._checkpoints_by_id.get(checkpoint_id)

    async def latest(self, run_id: str) -> Checkpoint | None:
        run = self._runs.get(run_id, [])
        return run[-1] if run else None

    async def list_run(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[Checkpoint]:
        if limit < 1:
            return []
        return [
            checkpoint
            for checkpoint in self._runs.get(run_id, [])
            if checkpoint.sequence is not None and checkpoint.sequence > after_sequence
        ][:limit]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS canonical_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at REAL NOT NULL,
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    node_run_id TEXT NOT NULL DEFAULT '',
    attempt_id TEXT NOT NULL DEFAULT '',
    event_sequence INTEGER,
    previous_checkpoint_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT '{}',
    UNIQUE(run_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_canonical_checkpoint_run
    ON canonical_checkpoints (run_id, sequence);
"""


class SqliteCheckpointStore:
    """SQLite implementation of the canonical CheckpointStore contract."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        self._lock = asyncio.Lock()

    async def ensure_schema(self) -> None:
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def append(self, checkpoint: Checkpoint) -> Checkpoint:
        async with self._lock:
            existing = await self.get(checkpoint.checkpoint_id)
            if existing is not None:
                return existing
            if checkpoint.sequence is not None:
                raise ValueError("sequence is store-assigned and must be None on append")

            cursor = await self._conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM canonical_checkpoints WHERE run_id = ?",
                (checkpoint.run_id,),
            )
            row = await cursor.fetchone()
            sequence = int(row[0]) if row is not None else 1
            persisted = replace(checkpoint, sequence=sequence)
            await self._conn.execute(
                """INSERT INTO canonical_checkpoints (
                    checkpoint_id, run_id, sequence, schema_version, created_at,
                    workspace_id, project_id, node_run_id, attempt_id, event_sequence,
                    previous_checkpoint_id, reason, state, provenance
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    persisted.checkpoint_id,
                    persisted.run_id,
                    persisted.sequence,
                    persisted.schema_version,
                    persisted.created_at,
                    persisted.workspace_id,
                    persisted.project_id,
                    persisted.node_run_id,
                    persisted.attempt_id,
                    persisted.event_sequence,
                    persisted.previous_checkpoint_id,
                    persisted.reason,
                    json.dumps(persisted.state),
                    json.dumps(persisted.provenance),
                ),
            )
            await self._conn.commit()
            return persisted

    async def get(self, checkpoint_id: str) -> Checkpoint | None:
        cursor = await self._conn.execute(
            "SELECT * FROM canonical_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_checkpoint(tuple(row)) if row is not None else None

    async def latest(self, run_id: str) -> Checkpoint | None:
        cursor = await self._conn.execute(
            """SELECT * FROM canonical_checkpoints
               WHERE run_id = ? ORDER BY sequence DESC LIMIT 1""",
            (run_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_checkpoint(tuple(row)) if row is not None else None

    async def list_run(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[Checkpoint]:
        if limit < 1:
            return []
        cursor = await self._conn.execute(
            """SELECT * FROM canonical_checkpoints
               WHERE run_id = ? AND sequence > ?
               ORDER BY sequence ASC LIMIT ?""",
            (run_id, after_sequence, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_checkpoint(tuple(row)) for row in rows]

    @staticmethod
    def _row_to_checkpoint(row: tuple[Any, ...]) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=row[0],
            run_id=row[1],
            sequence=row[2],
            schema_version=row[3],
            created_at=row[4],
            workspace_id=row[5],
            project_id=row[6],
            node_run_id=row[7],
            attempt_id=row[8],
            event_sequence=row[9],
            previous_checkpoint_id=row[10],
            reason=row[11],
            state=json.loads(row[12]),
            provenance=json.loads(row[13]),
        )
