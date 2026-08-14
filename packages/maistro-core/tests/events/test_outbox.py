"""Transactional outbox tests for canonical event publication."""

from __future__ import annotations

import aiosqlite
import pytest

from maistro.events.envelope import EventEnvelope, SqliteEventStore
from maistro.events.outbox import SqliteEventOutbox


@pytest.fixture
async def connection() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(":memory:")
    await conn.execute("CREATE TABLE domain_state (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
    await conn.commit()
    yield conn
    await conn.close()


async def _stores(
    connection: aiosqlite.Connection,
) -> tuple[SqliteEventOutbox, SqliteEventStore]:
    outbox = SqliteEventOutbox(connection)
    event_store = SqliteEventStore(connection)
    await outbox.ensure_schema()
    await event_store.ensure_schema()
    return outbox, event_store


async def test_domain_state_and_event_stage_commit_together(
    connection: aiosqlite.Connection,
) -> None:
    outbox, event_store = await _stores(connection)
    event = EventEnvelope(type="run.updated", run_id="run-1", event_id="evt-commit")

    await connection.execute("BEGIN")
    await connection.execute(
        "INSERT INTO domain_state (id, value) VALUES (?, ?)",
        ("run-1", "running"),
    )
    await outbox.stage(event)
    await connection.commit()

    state = await (await connection.execute("SELECT value FROM domain_state WHERE id = 'run-1'" )).fetchone()
    assert state == ("running",)
    assert await outbox.pending_count() == 1

    assert await outbox.publish_pending(event_store) == 1
    persisted = await event_store.get("evt-commit")
    assert persisted is not None
    assert persisted.sequence == 1
    assert await outbox.pending_count() == 0


async def test_domain_state_and_event_stage_roll_back_together(
    connection: aiosqlite.Connection,
) -> None:
    outbox, event_store = await _stores(connection)
    event = EventEnvelope(type="run.updated", run_id="run-1", event_id="evt-rollback")

    await connection.execute("BEGIN")
    await connection.execute(
        "INSERT INTO domain_state (id, value) VALUES (?, ?)",
        ("run-1", "running"),
    )
    await outbox.stage(event)
    await connection.rollback()

    state = await (await connection.execute("SELECT value FROM domain_state WHERE id = 'run-1'" )).fetchone()
    assert state is None
    assert await outbox.pending_count() == 0
    assert await outbox.publish_pending(event_store) == 0
    assert await event_store.get("evt-rollback") is None


async def test_stage_is_idempotent_by_event_id(connection: aiosqlite.Connection) -> None:
    outbox, _ = await _stores(connection)
    event = EventEnvelope(type="run.updated", run_id="run-1", event_id="stable")

    first = await outbox.stage(event)
    second = await outbox.stage(event)
    await connection.commit()

    assert first == second
    assert await outbox.pending_count() == 1


async def test_publish_recovers_after_event_append_before_outbox_mark(
    connection: aiosqlite.Connection,
) -> None:
    outbox, event_store = await _stores(connection)
    event = EventEnvelope(type="attempt.completed", run_id="run-1", event_id="evt-crash")
    await outbox.stage(event)
    await connection.commit()

    first = await event_store.append(event)
    assert first.sequence == 1
    assert await outbox.pending_count() == 1

    assert await outbox.publish_pending(event_store) == 1
    history = await event_store.list_stream("run:run-1")
    assert [item.event_id for item in history] == ["evt-crash"]
    assert await outbox.pending_count() == 0


async def test_publish_stops_on_store_failure_and_leaves_row_pending(
    connection: aiosqlite.Connection,
) -> None:
    outbox, _ = await _stores(connection)
    event = EventEnvelope(type="attempt.failed", run_id="run-1", event_id="evt-fail")
    await outbox.stage(event)
    await connection.commit()

    class FailingStore:
        async def append(self, event: EventEnvelope) -> EventEnvelope:
            raise RuntimeError("store unavailable")

        async def get(self, event_id: str) -> EventEnvelope | None:
            return None

        async def list_stream(
            self,
            stream_id: str,
            *,
            after_sequence: int = 0,
            limit: int = 100,
        ) -> list[EventEnvelope]:
            return []

    with pytest.raises(RuntimeError, match="store unavailable"):
        await outbox.publish_pending(FailingStore())
    assert await outbox.pending_count() == 1


async def test_stage_rejects_presequenced_event(connection: aiosqlite.Connection) -> None:
    outbox, _ = await _stores(connection)
    with pytest.raises(ValueError, match="store-assigned sequence"):
        await outbox.stage(EventEnvelope(type="x", run_id="r1", sequence=9))
