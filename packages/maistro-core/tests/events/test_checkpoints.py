"""Contract tests for canonical checkpoints and resume references."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator

import aiosqlite
import pytest

from maistro.events.checkpoints import (
    CHECKPOINT_SCHEMA_VERSION,
    Checkpoint,
    CheckpointNotFoundError,
    CheckpointRef,
    CheckpointStore,
    CheckpointVersionError,
    InMemoryCheckpointStore,
    SqliteCheckpointStore,
    checkpoint_created_event,
    resolve_checkpoint,
)


@pytest.fixture(params=["memory", "sqlite"])
async def checkpoint_store(request: pytest.FixtureRequest) -> AsyncIterator[CheckpointStore]:
    if request.param == "memory":
        yield InMemoryCheckpointStore()
        return

    conn = await aiosqlite.connect(":memory:")
    store = SqliteCheckpointStore(conn)
    await store.ensure_schema()
    yield store
    await conn.close()


def _checkpoint(**overrides: object) -> Checkpoint:
    values: dict[str, object] = {
        "workspace_id": "ws-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "executable_version": "runtime-v1",
        "state": {"cursor": "node-2", "blackboard": {"answer": 42}},
    }
    values.update(overrides)
    return Checkpoint(**values)  # type: ignore[arg-type]


def test_checkpoint_requires_canonical_scope_and_compatibility() -> None:
    with pytest.raises(ValueError, match="workspace_id"):
        _checkpoint(workspace_id="")
    with pytest.raises(ValueError, match="project_id"):
        _checkpoint(project_id="")
    with pytest.raises(ValueError, match="run_id"):
        _checkpoint(run_id="")
    with pytest.raises(ValueError, match="executable_version"):
        _checkpoint(executable_version="")


def test_checkpoint_requires_inline_or_external_state() -> None:
    with pytest.raises(ValueError, match="inline state or state_locator"):
        _checkpoint(state={})
    with pytest.raises(ValueError, match="requires state_hash"):
        _checkpoint(state={}, state_locator="artifact://checkpoint/1")


def test_inline_state_gets_stable_hash() -> None:
    state = {"b": 2, "a": {"value": 1}}
    checkpoint = _checkpoint(state=state)
    expected = hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert checkpoint.state_hash == expected


def test_external_state_retains_locator_and_hash() -> None:
    checkpoint = _checkpoint(
        state={},
        state_locator="artifact://checkpoint/1",
        state_hash="sha256:abc123",
    )
    assert checkpoint.state == {}
    assert checkpoint.state_locator == "artifact://checkpoint/1"
    assert checkpoint.state_hash == "sha256:abc123"


def test_checkpoint_ref_preserves_schema_version() -> None:
    checkpoint = _checkpoint(checkpoint_id="cp-1", schema_version=3)
    assert checkpoint.ref == CheckpointRef(checkpoint_id="cp-1", schema_version=3)


def test_checkpoint_created_event_preserves_canonical_correlation() -> None:
    checkpoint = _checkpoint(
        checkpoint_id="cp-event",
        sequence=4,
        event_sequence=17,
        node_run_id="node-run-1",
        attempt_id="attempt-2",
        graph_id="graph-1",
        graph_snapshot_hash="graph-sha",
        reason="provider-yield",
        provenance={"runtime": "python"},
    )
    event = checkpoint_created_event(checkpoint)

    assert event.type == "checkpoint.created"
    assert event.workspace_id == "ws-1"
    assert event.project_id == "project-1"
    assert event.run_id == "run-1"
    assert event.node_run_id == "node-run-1"
    assert event.attempt_id == "attempt-2"
    assert event.provenance == {"runtime": "python"}
    assert event.payload["checkpoint_id"] == "cp-event"
    assert event.payload["checkpoint_sequence"] == 4
    assert event.payload["event_sequence"] == 17
    assert event.payload["graph_snapshot_hash"] == "graph-sha"


class TestCheckpointStoreContract:
    async def test_assigns_sequence_per_run(self, checkpoint_store: CheckpointStore) -> None:
        first = await checkpoint_store.append(_checkpoint(checkpoint_id="cp-1"))
        second = await checkpoint_store.append(_checkpoint(checkpoint_id="cp-2"))
        other = await checkpoint_store.append(
            _checkpoint(checkpoint_id="cp-other", run_id="run-2")
        )

        assert first.sequence == 1
        assert second.sequence == 2
        assert other.sequence == 1

    async def test_append_is_idempotent(self, checkpoint_store: CheckpointStore) -> None:
        checkpoint = _checkpoint(checkpoint_id="stable")
        first = await checkpoint_store.append(checkpoint)
        duplicate = await checkpoint_store.append(checkpoint)
        history = await checkpoint_store.list_run("run-1")

        assert duplicate == first
        assert [item.checkpoint_id for item in history] == ["stable"]

    async def test_rejects_caller_sequence(self, checkpoint_store: CheckpointStore) -> None:
        with pytest.raises(ValueError, match="store-assigned"):
            await checkpoint_store.append(_checkpoint(sequence=7))

    async def test_round_trips_resume_metadata(self, checkpoint_store: CheckpointStore) -> None:
        checkpoint = _checkpoint(
            checkpoint_id="cp-roundtrip",
            node_run_id="node-run-1",
            attempt_id="attempt-2",
            event_sequence=17,
            previous_checkpoint_id="cp-previous",
            reason="provider-yield",
            state_locator="artifact://checkpoint/roundtrip",
            graph_id="graph-1",
            graph_snapshot_hash="graph-sha",
            provenance={"runtime": "python"},
        )
        persisted = await checkpoint_store.append(checkpoint)
        loaded = await checkpoint_store.get("cp-roundtrip")

        assert loaded == persisted
        assert loaded is not None
        assert loaded.event_sequence == 17
        assert loaded.attempt_id == "attempt-2"
        assert loaded.executable_version == "runtime-v1"
        assert loaded.graph_snapshot_hash == "graph-sha"
        assert loaded.state_hash == checkpoint.state_hash

    async def test_latest_and_cursor_reads(self, checkpoint_store: CheckpointStore) -> None:
        for index in range(5):
            await checkpoint_store.append(
                _checkpoint(checkpoint_id=f"cp-{index}", reason=f"step-{index}")
            )

        latest = await checkpoint_store.latest("run-1")
        page = await checkpoint_store.list_run("run-1", after_sequence=2, limit=2)

        assert latest is not None
        assert latest.sequence == 5
        assert [checkpoint.sequence for checkpoint in page] == [3, 4]
        assert await checkpoint_store.list_run("run-1", limit=0) == []

    async def test_concurrent_sequences(self, checkpoint_store: CheckpointStore) -> None:
        checkpoints = [_checkpoint(checkpoint_id=f"cp-{index}") for index in range(20)]
        persisted = await asyncio.gather(
            *(checkpoint_store.append(checkpoint) for checkpoint in checkpoints)
        )
        sequences = [checkpoint.sequence for checkpoint in persisted]

        assert sorted(sequence for sequence in sequences if sequence is not None) == list(
            range(1, 21)
        )

    async def test_resolve_checkpoint_validates_schema_version(
        self,
        checkpoint_store: CheckpointStore,
    ) -> None:
        persisted = await checkpoint_store.append(_checkpoint(checkpoint_id="cp-resume"))
        resolved = await resolve_checkpoint(checkpoint_store, persisted.ref)
        assert resolved == persisted

        with pytest.raises(CheckpointVersionError, match="not supported"):
            await resolve_checkpoint(
                checkpoint_store,
                CheckpointRef("cp-resume", schema_version=CHECKPOINT_SCHEMA_VERSION + 1),
            )

    async def test_resolve_checkpoint_rejects_reference_version_mismatch(
        self,
        checkpoint_store: CheckpointStore,
    ) -> None:
        await checkpoint_store.append(
            _checkpoint(checkpoint_id="cp-versioned", schema_version=2)
        )
        with pytest.raises(CheckpointVersionError, match="does not match"):
            await resolve_checkpoint(
                checkpoint_store,
                CheckpointRef("cp-versioned", schema_version=1),
                supported_schema_versions=frozenset({1, 2}),
            )

    async def test_resolve_checkpoint_rejects_executable_incompatibility(
        self,
        checkpoint_store: CheckpointStore,
    ) -> None:
        persisted = await checkpoint_store.append(
            _checkpoint(checkpoint_id="cp-runtime", executable_version="runtime-v2")
        )
        with pytest.raises(CheckpointVersionError, match="executable version"):
            await resolve_checkpoint(
                checkpoint_store,
                persisted.ref,
                supported_executable_versions=frozenset({"runtime-v1"}),
            )

    async def test_resolve_checkpoint_requires_existing_checkpoint(
        self,
        checkpoint_store: CheckpointStore,
    ) -> None:
        with pytest.raises(CheckpointNotFoundError):
            await resolve_checkpoint(checkpoint_store, CheckpointRef("missing"))
