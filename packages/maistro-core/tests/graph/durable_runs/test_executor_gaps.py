"""Gap-filling coverage for graph/durable_runs/executor.py not exercised
by test_durable_runs.py: resume_durable_dag's missing-run/bad-status
branches, _walk's unknown-node branch, _entry_node's nodes-fallback and
no-nodes-raise branches, _node_spec's no-match branch, _next_node's
all-conditions-fallback branch, _lift_blackboard's no-blackboard early
return, and _build_ctx's blackboard-construction exception fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from maistro.graph.durable_runs import (
    DurableRunRecord,
    InMemoryDurableRunStore,
    RunStatus,
    resume_durable_dag,
    run_durable_dag,
)
from maistro.graph.durable_runs.executor import (
    _build_ctx,
    _entry_node,
    _lift_blackboard,
    _next_node,
    _node_spec,
)
from maistro.graph.nodes.base import NodeContext, NodeResult


def _record_for(run_id: str, **overrides: Any) -> DurableRunRecord:
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "run_id": run_id,
        "dag_id": "d1",
        "dag_snapshot": {"nodes": [], "edges": []},
        "started_at": now,
        "last_step_at": now,
        "version": 1,
    }
    base.update(overrides)
    return DurableRunRecord(**base)


def _no_op_resolver(node_id: str, dag: dict[str, Any]) -> Any:
    raise AssertionError("resolver should not be called in this test")


class TestResumeDurableDagGuards:
    async def test_missing_run_raises_key_error(self) -> None:
        store = InMemoryDurableRunStore()
        with pytest.raises(KeyError, match="no such run"):
            await resume_durable_dag("nope", store=store, node_resolver=_no_op_resolver)

    async def test_completed_run_raises_value_error(self) -> None:
        store = InMemoryDurableRunStore()
        record = _record_for("r-completed", status=RunStatus.COMPLETED)
        await store.create(record)
        with pytest.raises(ValueError, match="cannot resume run"):
            await resume_durable_dag("r-completed", store=store, node_resolver=_no_op_resolver)

    async def test_paused_wait_run_is_flipped_to_running_before_walk(self) -> None:
        store = InMemoryDurableRunStore()
        record = _record_for(
            "r-paused",
            status=RunStatus.PAUSED_WAIT,
            current_node_id=None,  # no current node -> walk completes immediately
        )
        await store.create(record)
        result = await resume_durable_dag("r-paused", store=store, node_resolver=_no_op_resolver)
        assert result.status == RunStatus.COMPLETED


class TestWalkUnknownNode:
    async def test_unknown_node_id_marks_run_failed(self) -> None:
        store = InMemoryDurableRunStore()
        dag = {"nodes": [], "edges": [], "entry_node": "missing-node"}
        result = await run_durable_dag(dag, store=store, node_resolver=_no_op_resolver)
        assert result.status == RunStatus.FAILED
        assert result.error_code == "UnknownNode"
        assert "missing-node" in (result.error_message or "")


class TestEntryNode:
    def test_explicit_entry_node_wins(self) -> None:
        dag = {"entry_node": "start", "nodes": [{"id": "other"}]}
        assert _entry_node(dag) == "start"

    def test_falls_back_to_first_node_by_document_order(self) -> None:
        dag = {"nodes": [{"id": "first"}, {"id": "second"}]}
        assert _entry_node(dag) == "first"

    def test_no_nodes_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="no nodes"):
            _entry_node({"nodes": []})


class TestNodeSpec:
    def test_no_matching_node_returns_none(self) -> None:
        dag = {"nodes": [{"id": "a"}]}
        assert _node_spec(dag, "b") is None


class TestNextNode:
    def test_all_outgoing_edges_have_conditions_takes_first(self) -> None:
        dag = {
            "edges": [
                {"from_node": "a", "to_node": "b", "condition": "x == 1"},
                {"from_node": "a", "to_node": "c", "condition": "x == 2"},
            ]
        }
        result = NodeResult(success=True, status="completed", output=None)
        assert _next_node(dag, "a", result) == "b"


class TestLiftBlackboard:
    def test_none_blackboard_returns_record_unchanged(self) -> None:
        record = _record_for("r-lift")
        ctx = NodeContext(run_id="r-lift", dag_id="d1", node_id="n1", blackboard=None)
        assert _lift_blackboard(record, ctx) is record


class TestBuildCtxBlackboardFallback:
    def test_malformed_blackboard_snapshot_falls_back_to_none(self) -> None:
        record = _record_for(
            "r-ctx",
            blackboard_snapshot={"metadata": "not-a-dict-and-not-iterable-pairs"},
        )
        ctx = _build_ctx(record, "n1")
        assert ctx.blackboard is None
