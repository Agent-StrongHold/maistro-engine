"""Gap-filling coverage for graph/durable_runs/executor.py not exercised
by test_durable_runs.py: resume_durable_dag's missing-run/bad-status
branches, _walk's unknown-node branch, _entry_node's nodes-fallback and
no-nodes-raise branches, _node_spec's no-match branch, _next_node's
all-conditions-fallback branch, _lift_blackboard's no-blackboard early
return, and _build_ctx's blackboard-construction exception fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel

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
    _walk,
)
from maistro.graph.nodes import BaseNode, NodeContext, get_node, register_node
from maistro.graph.nodes.base import NodeResult


class _EchoIn(BaseModel):
    text: str = "x"


class _EchoOut(BaseModel):
    text: str


class _EchoNode(BaseNode):
    """Registered here rather than reused from test_durable_runs.py.

    The node registry is process-global, so borrowing "test.uppercase" would
    work only when that module happens to be imported first — a test that
    passes or fails depending on collection order.
    """

    kind: ClassVar[str] = "test.executor_gaps.echo"
    kind_category: ClassVar = "sync.transform"
    input_schema: ClassVar[type[BaseModel]] = _EchoIn
    output_schema: ClassVar[type[BaseModel]] = _EchoOut

    async def _execute(self, inputs: _EchoIn, ctx: NodeContext) -> _EchoOut:
        return _EchoOut(text=inputs.text)


register_node(_EchoNode)


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


class TestStepBudgetExhaustion:
    """M5b: a run that exhausts max_steps must not be recorded as COMPLETED.

    `_walk` leaves its loop two ways — `current_node_id` went empty (the graph
    finished) or `steps` hit `max_steps` (it did not). Both fell through to
    `_mark_completed`, so a cycling or over-long DAG was persisted as a success
    with a partial blackboard. That is worse than a failure record: downstream
    consumers trust COMPLETED.

    The review downgraded this to latent because the one shipped caller obtains
    its snapshot from `DagRegistry.register()`, which rejects cycles via
    `_validate_no_cycles`. It becomes reachable the moment a second caller
    skips the registry — and `run_durable_dag` takes a raw dict, so nothing
    structural prevents that.
    """

    @staticmethod
    def _cycle_dag() -> dict[str, Any]:
        # n1 -> n2 -> n1. Never reaches an end node, so the walk can only stop
        # by running out of steps.
        return {
            "id": "cycle-dag",
            "nodes": [
                {"id": "n1", "kind": "test.executor_gaps.echo", "inputs": {"text": "hello"}},
                {"id": "n2", "kind": "test.executor_gaps.echo", "inputs": {"text": "b"}},
            ],
            "edges": [
                {"from_node": "n1", "to_node": "n2"},
                {"from_node": "n2", "to_node": "n1"},
            ],
            "entry_node": "n1",
        }

    @staticmethod
    def _resolver(node_id: str, dag: dict[str, Any]) -> Any:
        for n in dag.get("nodes", []):
            if str(n.get("id")) == node_id:
                return get_node(n["kind"])()
        raise KeyError(node_id)

    async def test_cycling_dag_is_marked_failed_not_completed(self) -> None:
        """Fails without the fix: status was COMPLETED."""
        store = InMemoryDurableRunStore()
        record = _record_for("r-cycle", dag_snapshot=self._cycle_dag(), current_node_id="n1")
        await store.create(record)

        # `run_durable_dag` exposes no max_steps, so drive `_walk` directly
        # with a small budget rather than executing 256 real steps.
        result = await _walk(record, store=store, node_resolver=self._resolver, max_steps=8)

        assert result.status == RunStatus.FAILED, (
            f"a cycling DAG was recorded as {result.status}; a partial run must "
            "not be indistinguishable from a finished one"
        )
        assert result.error_code == "StepBudgetExhausted"
        assert "max_steps=8" in (result.error_message or "")

    async def test_a_run_that_really_finishes_is_still_completed(self) -> None:
        """Control: the fix must not fail every run that used its budget.

        Distinguishes "stopped because it ended" from "stopped because it ran
        out" — without this, marking everything FAILED would satisfy the test
        above.
        """
        store = InMemoryDurableRunStore()
        dag: dict[str, Any] = {
            "id": "linear-dag",
            "nodes": [{"id": "n1", "kind": "test.executor_gaps.echo", "inputs": {"text": "hi"}}],
            "edges": [],
            "entry_node": "n1",
        }
        record = _record_for("r-done", dag_snapshot=dag, current_node_id="n1")
        await store.create(record)

        result = await _walk(record, store=store, node_resolver=self._resolver, max_steps=8)

        assert result.status == RunStatus.COMPLETED
