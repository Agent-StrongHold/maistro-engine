"""Edge-case coverage for graph.durable_runs.stores — error paths, HITL guards,
project-scoped filtering, and SQLite collision/optimistic-concurrency paths
not exercised by the executor-level tests in test_durable_runs.py."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from maistro.graph.durable_runs.stores import (
    InMemoryDurableRunStore,
    SqliteDurableRunStore,
)
from maistro.graph.durable_runs.types import DurableRunRecord, RunStatus


def _record_for(run_id: str, **overrides: object) -> DurableRunRecord:
    now = datetime.now(UTC)
    base = {
        "run_id": run_id,
        "dag_id": "d1",
        "dag_snapshot": {"nodes": [], "edges": []},
        "started_at": now,
        "last_step_at": now,
        "version": 1,
    }
    base.update(overrides)
    return DurableRunRecord(**base)


# --- InMemoryDurableRunStore -------------------------------------------------


async def test_update_missing_run_raises_keyerror() -> None:
    store = InMemoryDurableRunStore()
    with pytest.raises(KeyError, match="no such run"):
        await store.update(_record_for("missing"))


async def test_list_by_status_respects_limit() -> None:
    store = InMemoryDurableRunStore()
    for i in range(5):
        await store.create(_record_for(f"r{i}"))
    out = await store.list_by_status(RunStatus.PENDING, limit=2)
    assert len(out) == 2


async def test_list_by_status_filters_by_project_id() -> None:
    store = InMemoryDurableRunStore()
    await store.create(_record_for("a", project_id="p1"))
    await store.create(_record_for("b", project_id="p2"))
    out = await store.list_by_status(RunStatus.PENDING, project_id="p1")
    assert [r.run_id for r in out] == ["a"]


async def test_list_for_project_respects_limit_and_ordering() -> None:
    store = InMemoryDurableRunStore()
    rec1 = await store.create(_record_for("a", project_id="p1"))
    rec2 = await store.create(_record_for("b", project_id="p1"))
    bumped = rec2.model_copy(update={"version": 2, "started_at": rec1.started_at})
    await store.update(bumped)
    out = await store.list_for_project("p1", limit=1)
    assert len(out) == 1


async def test_submit_hitl_answer_missing_run_raises_keyerror() -> None:
    store = InMemoryDurableRunStore()
    with pytest.raises(KeyError, match="no such run"):
        await store.submit_hitl_answer("missing", "n1", {"answer": "x"})


async def test_submit_hitl_answer_wrong_status_raises_valueerror() -> None:
    store = InMemoryDurableRunStore()
    await store.create(_record_for("r1", status=RunStatus.RUNNING))
    with pytest.raises(ValueError, match="not paused on HITL"):
        await store.submit_hitl_answer("r1", "n1", {"answer": "x"})


async def test_submit_hitl_answer_wrong_node_raises_valueerror() -> None:
    store = InMemoryDurableRunStore()
    await store.create(_record_for("r1", status=RunStatus.PAUSED_HITL, current_node_id="ask"))
    with pytest.raises(ValueError, match="waiting on node"):
        await store.submit_hitl_answer("r1", "wrong-node", {"answer": "x"})


# --- SqliteDurableRunStore ----------------------------------------------------


async def test_sqlite_create_collision_raises_valueerror(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    await store.create(_record_for("r1"))
    with pytest.raises(ValueError, match="collision"):
        await store.create(_record_for("r1"))


async def test_sqlite_update_missing_run_raises_keyerror(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    with pytest.raises(KeyError, match="no such run"):
        await store.update(_record_for("missing"))


async def test_sqlite_get_missing_returns_none(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    assert await store.get("missing") is None


async def test_sqlite_list_by_status_filters_by_project_id(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    await store.create(_record_for("a", project_id="p1"))
    await store.create(_record_for("b", project_id="p2"))
    out = await store.list_by_status(RunStatus.PENDING, project_id="p1")
    assert [r.run_id for r in out] == ["a"]


async def test_sqlite_list_by_status_respects_limit(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    for i in range(5):
        await store.create(_record_for(f"r{i}"))
    out = await store.list_by_status(RunStatus.PENDING, limit=2)
    assert len(out) == 2


async def test_sqlite_list_for_project_filters_and_limits(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    await store.create(_record_for("a", project_id="p1"))
    await store.create(_record_for("b", project_id="p1"))
    await store.create(_record_for("c", project_id="p2"))
    out = await store.list_for_project("p1", limit=1)
    assert len(out) == 1
    assert out[0].project_id == "p1"


async def test_sqlite_submit_hitl_answer_missing_run_raises_keyerror(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    with pytest.raises(KeyError, match="no such run"):
        await store.submit_hitl_answer("missing", "n1", {"answer": "x"})


async def test_sqlite_submit_hitl_answer_wrong_status_raises_valueerror(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    await store.create(_record_for("r1", status=RunStatus.RUNNING))
    with pytest.raises(ValueError, match="not paused on HITL"):
        await store.submit_hitl_answer("r1", "n1", {"answer": "x"})


async def test_sqlite_submit_hitl_answer_wrong_node_raises_valueerror(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    await store.create(_record_for("r1", status=RunStatus.PAUSED_HITL, current_node_id="ask"))
    with pytest.raises(ValueError, match="waiting on node"):
        await store.submit_hitl_answer("r1", "wrong-node", {"answer": "x"})


async def test_sqlite_submit_hitl_answer_success_updates_record(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    await store.create(_record_for("r1", status=RunStatus.PAUSED_HITL, current_node_id="ask"))
    updated = await store.submit_hitl_answer("r1", "ask", {"answer": "yes"})
    assert updated.status == RunStatus.RUNNING
    assert updated.hitl_answers["ask"]["answer"] == "yes"
    assert updated.version == 2
