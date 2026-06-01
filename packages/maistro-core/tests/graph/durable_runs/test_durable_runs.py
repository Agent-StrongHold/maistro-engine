"""Durable run state + executor tests.

Covers:
- InMemoryDurableRunStore: CRUD, optimistic concurrency, HITL answer flow.
- SqliteDurableRunStore: same surface via a tmp_path-backed file (proves
  the persistence layer round-trips records identically).
- Executor (run_durable_dag / resume_durable_dag):
  - sync DAG (all transforms) walks to completion in one call
  - HITL DAG pauses on first call; resumes after submit_hitl_answer
  - wait DAG pauses, resumes after a re-invoke (via the same resume path)
  - failed node halts the run
  - negative_signal compliance.block with halt_run=true halts the run
  - simulated container restart: drop the executor + store reference,
    rebuild from disk, resume; the run completes correctly.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel

from maistro.graph.durable_runs import (
    DurableRunRecord,
    DurableRunStore,
    InMemoryDurableRunStore,
    RunStatus,
    SqliteDurableRunStore,
    resume_durable_dag,
    run_durable_dag,
)
from maistro.graph.nodes import (
    BaseNode,
    NodeContext,
    get_node,
    pause_until,
    register_node,
)

# --- Test fixtures: tiny nodes registered just for these tests -------------


class _UpperIn(BaseModel):
    text: str


class _UpperOut(BaseModel):
    text: str


class _UppercaseNode(BaseNode):
    kind: ClassVar[str] = "test.uppercase"
    kind_category: ClassVar = "sync.transform"
    input_schema: ClassVar[type[BaseModel]] = _UpperIn
    output_schema: ClassVar[type[BaseModel]] = _UpperOut

    async def _execute(self, inputs: _UpperIn, ctx: NodeContext) -> _UpperOut:
        return _UpperOut(text=inputs.text.upper())


class _AppendIn(BaseModel):
    text: str
    suffix: str = "!"


class _AppendOut(BaseModel):
    text: str


class _AppendNode(BaseNode):
    kind: ClassVar[str] = "test.append"
    kind_category: ClassVar = "sync.transform"
    input_schema: ClassVar[type[BaseModel]] = _AppendIn
    output_schema: ClassVar[type[BaseModel]] = _AppendOut

    async def _execute(self, inputs: _AppendIn, ctx: NodeContext) -> _AppendOut:
        return _AppendOut(text=inputs.text + inputs.suffix)


class _AskIn(BaseModel):
    question: str


class _AskOut(BaseModel):
    # Emit `text` so a downstream _AppendNode (which expects {text, suffix})
    # picks the answer up by name. This matches the executor's default
    # "upstream output wins" flow without needing an explicit input-map.
    text: str


class _MiniAskNode(BaseNode):
    """A HITL node small enough to drive without the full human.ask_question
    metadata machinery — pauses with `awaiting_human_answer`, resumes when
    the answer arrives in ctx.metadata['hitl_answers'][node_id]."""

    kind: ClassVar[str] = "test.mini_ask"
    kind_category: ClassVar = "hitl"
    input_schema: ClassVar[type[BaseModel]] = _AskIn
    output_schema: ClassVar[type[BaseModel]] = _AskOut

    async def _execute(self, inputs: _AskIn, ctx: NodeContext) -> _AskOut:
        answers = (ctx.metadata or {}).get("hitl_answers") or {}
        existing = answers.get(ctx.node_id)
        if existing is not None:
            return _AskOut(text=str(existing.get("answer") or ""))
        pause_until(
            "awaiting_human_answer",
            resume_at=datetime.now(UTC) + timedelta(seconds=300),
            metadata={"question": inputs.question},
        )
        return _AskOut(text="UNREACHABLE")


class _BoomIn(BaseModel):
    pass


class _BoomOut(BaseModel):
    pass


class _DurableBoomNode(BaseNode):
    # Distinct kind from the contract-test fixture so cross-file pytest
    # collection doesn't trip the registry's collision guard.
    kind: ClassVar[str] = "test.durable_boom"
    kind_category: ClassVar = "sync.transform"
    input_schema: ClassVar[type[BaseModel]] = _BoomIn
    output_schema: ClassVar[type[BaseModel]] = _BoomOut

    async def _execute(self, inputs: _BoomIn, ctx: NodeContext) -> _BoomOut:
        raise ValueError("intentional test failure")


for _cls in (_UppercaseNode, _AppendNode, _MiniAskNode, _DurableBoomNode):
    # Tests rerun in the same process; collision is fine.
    with contextlib.suppress(ValueError):
        register_node(_cls)


def _resolver(node_id: str, dag: dict[str, Any]) -> BaseNode:
    """Phase-1 resolver: find the kind in dag.nodes[*].kind, look it up."""
    for n in dag.get("nodes", []):
        if str(n.get("id")) == node_id:
            return get_node(n["kind"])()
    raise KeyError(node_id)


# --- InMemoryDurableRunStore CRUD + concurrency ----------------------------


@pytest.fixture
def mem_store() -> DurableRunStore:
    return InMemoryDurableRunStore()


def _record_for(run_id: str) -> DurableRunRecord:
    now = datetime.now(UTC)
    return DurableRunRecord(
        run_id=run_id,
        dag_id="d1",
        dag_snapshot={"nodes": [], "edges": []},
        started_at=now,
        last_step_at=now,
        version=1,
    )


async def test_create_get_roundtrip(mem_store: DurableRunStore) -> None:
    await mem_store.create(_record_for("r-1"))
    got = await mem_store.get("r-1")
    assert got is not None
    assert got.run_id == "r-1"
    assert got.version == 1


async def test_create_collision_raises(mem_store: DurableRunStore) -> None:
    await mem_store.create(_record_for("r-1"))
    with pytest.raises(ValueError, match="collision"):
        await mem_store.create(_record_for("r-1"))


async def test_update_requires_higher_version(mem_store: DurableRunStore) -> None:
    rec = await mem_store.create(_record_for("r-1"))
    bumped = rec.model_copy(update={"version": 2})
    await mem_store.update(bumped)
    with pytest.raises(ValueError, match="version regression"):
        await mem_store.update(bumped)  # version still 2 — rejected


async def test_list_by_status_filters_correctly(mem_store: DurableRunStore) -> None:
    a = _record_for("a")
    b = _record_for("b").model_copy(update={"status": RunStatus.COMPLETED})
    await mem_store.create(a)
    await mem_store.create(b)
    running = await mem_store.list_by_status(RunStatus.RUNNING)
    completed = await mem_store.list_by_status(RunStatus.COMPLETED)
    assert {r.run_id for r in running} == set()  # both start "pending" not running
    assert {r.run_id for r in completed} == {"b"}


# --- SqliteDurableRunStore: same surface, persistence verified ------------


async def test_sqlite_store_roundtrips_across_reopen(tmp_path) -> None:
    db = tmp_path / "durable.db"
    store1 = SqliteDurableRunStore(db)
    rec = _record_for("r-sqlite-1").model_copy(
        update={"status": RunStatus.PAUSED_HITL, "current_node_id": "ask-1"}
    )
    await store1.create(rec)

    # New store instance, same file — simulates process restart.
    store2 = SqliteDurableRunStore(db)
    got = await store2.get("r-sqlite-1")
    assert got is not None
    assert got.status == RunStatus.PAUSED_HITL
    assert got.current_node_id == "ask-1"


async def test_sqlite_store_optimistic_concurrency(tmp_path) -> None:
    store = SqliteDurableRunStore(tmp_path / "durable.db")
    rec = await store.create(_record_for("r-1"))
    bumped = rec.model_copy(update={"version": 2})
    await store.update(bumped)
    with pytest.raises(ValueError, match="version regression"):
        await store.update(bumped)


# --- Executor: sync DAG runs to completion in one call --------------------


def _sync_dag() -> dict[str, Any]:
    return {
        "id": "sync-dag",
        "name": "uppercase-then-append",
        "nodes": [
            {"id": "n1", "kind": "test.uppercase", "inputs": {"text": "hello"}},
            {"id": "n2", "kind": "test.append", "config": {"suffix": "!!"}},
        ],
        "edges": [{"from_node": "n1", "to_node": "n2"}],
        "entry_node": "n1",
    }


async def test_run_sync_dag_completes_in_one_walk(mem_store: DurableRunStore) -> None:
    result = await run_durable_dag(
        _sync_dag(),
        store=mem_store,
        node_resolver=_resolver,
        inputs={"text": "hello"},
        user_id="alice",
        project_id="proj-a",
    )
    assert result.status == RunStatus.COMPLETED
    assert result.finished_at is not None
    assert len(result.node_records) == 2
    assert result.node_records[0].node_id == "n1"
    assert result.node_records[0].output == {"text": "HELLO"}
    assert result.node_records[1].node_id == "n2"
    assert result.node_records[1].output == {"text": "HELLO!!"}


async def test_run_sync_dag_persists_each_node_to_store(mem_store: DurableRunStore) -> None:
    result = await run_durable_dag(
        _sync_dag(),
        store=mem_store,
        node_resolver=_resolver,
        inputs={"text": "x"},
    )
    on_disk = await mem_store.get(result.run_id)
    assert on_disk is not None
    assert on_disk.status == RunStatus.COMPLETED
    assert len(on_disk.node_records) == 2


# --- Executor: HITL DAG pauses then resumes -------------------------------


def _hitl_dag() -> dict[str, Any]:
    return {
        "id": "hitl-dag",
        "name": "uppercase → ask → append",
        "nodes": [
            {"id": "u1", "kind": "test.uppercase", "inputs": {"text": "hi"}},
            {"id": "ask", "kind": "test.mini_ask", "inputs": {"question": "Continue?"}},
            {"id": "a1", "kind": "test.append", "config": {"suffix": " <done>"}},
        ],
        "edges": [
            {"from_node": "u1", "to_node": "ask"},
            {"from_node": "ask", "to_node": "a1"},
        ],
        "entry_node": "u1",
    }


async def test_hitl_dag_pauses_at_ask_node(mem_store: DurableRunStore) -> None:
    result = await run_durable_dag(
        _hitl_dag(),
        store=mem_store,
        node_resolver=_resolver,
        inputs={"text": "hi"},
        user_id="alice",
    )
    assert result.status == RunStatus.PAUSED_HITL
    assert result.current_node_id == "ask"
    # First node should have completed successfully.
    by_id = {nr.node_id: nr for nr in result.node_records}
    assert by_id["u1"].phase == "completed"
    assert by_id["u1"].output == {"text": "HI"}
    # Ask node recorded with phase=paused and the question metadata.
    assert by_id["ask"].phase == "paused"
    assert by_id["ask"].pause_metadata.get("question") == "Continue?"


async def test_hitl_dag_resumes_after_submit_answer(mem_store: DurableRunStore) -> None:
    started = await run_durable_dag(
        _hitl_dag(),
        store=mem_store,
        node_resolver=_resolver,
        inputs={"text": "hi"},
    )
    assert started.status == RunStatus.PAUSED_HITL

    await mem_store.submit_hitl_answer(started.run_id, "ask", {"answer": "yes"})
    resumed = await resume_durable_dag(
        started.run_id,
        store=mem_store,
        node_resolver=_resolver,
    )
    assert resumed.status == RunStatus.COMPLETED
    by_id = {nr.node_id: nr for nr in resumed.node_records}
    assert by_id["ask"].phase == "completed"
    # _MiniAskNode emits its `text` field so downstream nodes that expect
    # {text, suffix} (like _AppendNode) pick it up by name.
    assert by_id["ask"].output == {"text": "yes"}
    assert by_id["a1"].phase == "completed"
    # Append got "yes" from upstream + suffix " <done>".
    assert by_id["a1"].output == {"text": "yes <done>"}


# --- Executor: failure halts the run --------------------------------------


def _boom_dag() -> dict[str, Any]:
    return {
        "id": "boom-dag",
        "name": "uppercase → boom",
        "nodes": [
            {"id": "u1", "kind": "test.uppercase", "inputs": {"text": "hi"}},
            {"id": "boom", "kind": "test.durable_boom"},
        ],
        "edges": [{"from_node": "u1", "to_node": "boom"}],
        "entry_node": "u1",
    }


async def test_failed_node_marks_run_failed(mem_store: DurableRunStore) -> None:
    result = await run_durable_dag(
        _boom_dag(),
        store=mem_store,
        node_resolver=_resolver,
    )
    assert result.status == RunStatus.FAILED
    assert result.error_code == "ValueError"
    assert "intentional test failure" in (result.error_message or "")
    by_id = {nr.node_id: nr for nr in result.node_records}
    assert by_id["u1"].phase == "completed"
    assert by_id["boom"].phase == "failed"
    assert by_id["boom"].error_code == "ValueError"


# --- Executor: simulated container restart --------------------------------


async def test_sqlite_paused_run_resumes_after_simulated_restart(tmp_path) -> None:
    db = tmp_path / "durable.db"

    # Boot 1: start run, pause at HITL, drop the store reference.
    store1 = SqliteDurableRunStore(db)
    started = await run_durable_dag(
        _hitl_dag(),
        store=store1,
        node_resolver=_resolver,
        inputs={"text": "hi"},
        user_id="alice",
    )
    assert started.status == RunStatus.PAUSED_HITL
    run_id = started.run_id
    del store1

    # Boot 2: fresh store instance on the same file.
    store2 = SqliteDurableRunStore(db)
    persisted = await store2.get(run_id)
    assert persisted is not None
    assert persisted.status == RunStatus.PAUSED_HITL
    # Submit the answer.
    await store2.submit_hitl_answer(run_id, "ask", {"answer": "shipped"})
    final = await resume_durable_dag(run_id, store=store2, node_resolver=_resolver)
    assert final.status == RunStatus.COMPLETED
    # And the answer survived the restart through to the downstream node.
    by_id = {nr.node_id: nr for nr in final.node_records}
    assert by_id["a1"].output == {"text": "shipped <done>"}


# --- Executor: compliance.block halt_run=True halts the run ---------------


async def test_compliance_block_with_halt_run_marks_run_failed(
    mem_store: DurableRunStore,
) -> None:
    dag = {
        "id": "halt-dag",
        "name": "uppercase → compliance.block(halt) → append",
        "nodes": [
            {"id": "u1", "kind": "test.uppercase", "inputs": {"text": "x"}},
            {
                "id": "block",
                "kind": "compliance.block",
                "inputs": {
                    "rule_id": "policy.test",
                    "severity": 5.0,
                    "halt_run": True,
                    "reason": "test halt",
                },
            },
            {"id": "a1", "kind": "test.append", "config": {"suffix": "!"}},
        ],
        "edges": [
            {"from_node": "u1", "to_node": "block"},
            {"from_node": "block", "to_node": "a1"},
        ],
        "entry_node": "u1",
    }
    result = await run_durable_dag(
        dag, store=mem_store, node_resolver=_resolver, inputs={"text": "x"}
    )
    # compliance.block emits halt_requested into the blackboard; the
    # executor lifts the blackboard mutation back into the durable snapshot
    # AFTER each node completes, then checks halt_requested before
    # advancing. So u1 ran, block ran (success), then halt fired before a1.
    assert result.status == RunStatus.FAILED
    assert result.error_code == "HaltRequested"
    assert (result.error_message or "").startswith("test halt") or "test halt" in (
        result.error_message or ""
    )
    by_id = {nr.node_id: nr for nr in result.node_records}
    assert by_id["u1"].phase == "completed"
    assert by_id["block"].phase == "completed"
    assert by_id["block"].output is not None
    assert by_id["block"].output["halt_run"] is True
    # a1 must NOT have run — the halt fired before advancing to it.
    assert "a1" not in by_id
