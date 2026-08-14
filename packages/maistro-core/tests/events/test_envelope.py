"""Contract tests for the canonical event envelope and persistence stores."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import aiosqlite
import pytest

from maistro.events.envelope import (
    EventEnvelope,
    EventStore,
    InMemoryEventStore,
    SqliteEventStore,
)


@pytest.fixture(params=["memory", "sqlite"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[EventStore]:
    if request.param == "memory":
        yield InMemoryEventStore()
        return

    conn = await aiosqlite.connect(":memory:")
    sqlite_store = SqliteEventStore(conn)
    await sqlite_store.ensure_schema()
    yield sqlite_store
    await conn.close()


def test_envelope_preserves_canonical_correlation_fields() -> None:
    event = EventEnvelope(
        type="attempt.completed",
        payload={"result": {"ok": True}},
        workspace_id="ws-1",
        project_id="project-1",
        run_id="run-1",
        node_run_id="node-run-1",
        attempt_id="attempt-2",
        invocation_id="inv-3",
        session_id="session-1",
        correlation_id="corr-1",
        causation_id="event-parent",
        source="execution-runtime",
        actor_id="agent-1",
        provenance={"provider": "local"},
    )

    serialized = event.to_dict()
    assert serialized["type"] == "attempt.completed"
    assert serialized["payload"] == {"result": {"ok": True}}
    assert serialized["workspace_id"] == "ws-1"
    assert serialized["project_id"] == "project-1"
    assert serialized["run_id"] == "run-1"
    assert serialized["node_run_id"] == "node-run-1"
    assert serialized["attempt_id"] == "attempt-2"
    assert serialized["invocation_id"] == "inv-3"
    assert serialized["session_id"] == "session-1"
    assert serialized["correlation_id"] == "corr-1"
    assert serialized["causation_id"] == "event-parent"
    assert serialized["source"] == "execution-runtime"
    assert serialized["actor_id"] == "agent-1"
    assert serialized["provenance"] == {"provider": "local"}
    assert event.sequence is None


def test_stream_scope_precedence() -> None:
    run_event = EventEnvelope(type="x", run_id="r1", workspace_id="w1")
    workspace_event = EventEnvelope(type="x", workspace_id="w1")
    system_event = EventEnvelope(type="x")

    assert run_event.stream_id == "run:r1"
    assert workspace_event.stream_id == "workspace:w1"
    assert system_event.stream_id == "system"


class TestEventStoreContract:
    async def test_assigns_sequence_per_run(self, store: EventStore) -> None:
        first = await store.append(EventEnvelope(type="run.started", run_id="run-1"))
        second = await store.append(EventEnvelope(type="node.started", run_id="run-1"))

        assert first.sequence == 1
        assert second.sequence == 2

    async def test_run_sequences_are_independent(self, store: EventStore) -> None:
        run_a = await store.append(EventEnvelope(type="run.started", run_id="a"))
        run_b = await store.append(EventEnvelope(type="run.started", run_id="b"))
        run_a_2 = await store.append(EventEnvelope(type="run.completed", run_id="a"))

        assert run_a.sequence == 1
        assert run_b.sequence == 1
        assert run_a_2.sequence == 2

    async def test_append_is_idempotent(self, store: EventStore) -> None:
        event = EventEnvelope(type="node.completed", run_id="r1", event_id="stable")
        first = await store.append(event)
        duplicate = await store.append(event)
        history = await store.list_stream("run:r1")

        assert duplicate == first
        assert [item.event_id for item in history] == ["stable"]

    async def test_rejects_caller_sequence(self, store: EventStore) -> None:
        event = EventEnvelope(type="x", run_id="r1", sequence=99)
        with pytest.raises(ValueError, match="store-assigned"):
            await store.append(event)

    async def test_round_trips_payload(self, store: EventStore) -> None:
        event = EventEnvelope(
            type="invocation.completed",
            run_id="r1",
            attempt_id="a1",
            payload={"nested": [1, {"ok": True}]},
            provenance={"model": "example"},
        )
        persisted = await store.append(event)
        loaded = await store.get(persisted.event_id)

        assert loaded == persisted

    async def test_stream_cursor(self, store: EventStore) -> None:
        for index in range(5):
            event = EventEnvelope(type=f"event.{index}", run_id="r1")
            await store.append(event)

        page = await store.list_stream("run:r1", after_sequence=2, limit=2)
        assert [event.sequence for event in page] == [3, 4]
        assert [event.type for event in page] == ["event.2", "event.3"]
        assert await store.list_stream("run:r1", limit=0) == []

    async def test_concurrent_sequences(self, store: EventStore) -> None:
        events = [EventEnvelope(type="node.progress", run_id="r1") for _ in range(25)]
        persisted = await asyncio.gather(*(store.append(event) for event in events))
        sequences = [event.sequence for event in persisted]

        assert all(sequence is not None for sequence in sequences)
        assert sorted(sequence for sequence in sequences if sequence is not None) == list(
            range(1, 26)
        )

    async def test_retries_share_run_history(self, store: EventStore) -> None:
        first_attempt = EventEnvelope(
            type="attempt.failed",
            run_id="r1",
            attempt_id="attempt-1",
        )
        second_attempt = EventEnvelope(
            type="attempt.started",
            run_id="r1",
            attempt_id="attempt-2",
        )
        failed = await store.append(first_attempt)
        retried = await store.append(second_attempt)
        history = await store.list_stream("run:r1")

        assert failed.sequence == 1
        assert retried.sequence == 2
        assert [event.attempt_id for event in history] == ["attempt-1", "attempt-2"]
