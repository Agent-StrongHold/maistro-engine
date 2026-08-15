"""Characterization and migration-target tests for Stream 5 graph convergence.

These tests deliberately separate behavior that is already authoritative in
``GraphRun`` from known durable-executor gaps. Strict xfails describe canonical
behavior Stream 5 has not made real yet; passing cases are parity already won.

They must not be "fixed" by weakening the assertions or by teaching the tests
about another temporary lifecycle model.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel

from maistro.graph.durable_runs import InMemoryDurableRunStore, run_durable_dag
from maistro.graph.durable_runs.executor import _next_node
from maistro.graph.nodes.base import BaseNode, NodeContext, NodeResult
from maistro.graph.run import _next_nodes
from maistro.graph.types import AgentRole, GraphConfig, GraphEdge, ReviewOutput


class _PassInput(BaseModel):
    text: str = "x"


class _PassOutput(BaseModel):
    text: str


class _PassNode(BaseNode[_PassInput, _PassOutput]):
    """Minimal deterministic node for exercising durable traversal state."""

    kind: ClassVar[str] = "test.stream5.pass"
    input_schema: ClassVar[type[BaseModel]] = _PassInput
    output_schema: ClassVar[type[BaseModel]] = _PassOutput

    async def _execute(self, inputs: _PassInput, ctx: NodeContext) -> _PassOutput:
        return _PassOutput(text=inputs.text)


def _pass_resolver(node_id: str, dag: dict[str, object]) -> _PassNode:
    return _PassNode()


def test_graphrun_conditional_routing_follows_matching_edge() -> None:
    """GraphRun already provides the conditional semantics convergence keeps."""
    config = GraphConfig(
        nodes=[AgentRole.PLANNER, AgentRole.CODER, AgentRole.REVIEWER],
        edges=[
            GraphEdge(
                from_role=AgentRole.PLANNER,
                to_role=AgentRole.CODER,
                condition="review.approved == False",
            ),
            GraphEdge(
                from_role=AgentRole.PLANNER,
                to_role=AgentRole.REVIEWER,
                condition="review.approved == True",
            ),
        ],
    )

    next_nodes = _next_nodes(
        config,
        AgentRole.PLANNER,
        plan=None,
        code=None,
        review=ReviewOutput(approved=True),
    )

    assert next_nodes == [AgentRole.REVIEWER]


def test_graphrun_frontier_contains_sequential_and_parallel_targets() -> None:
    """A canonical persisted frontier must be able to represent this shape."""
    config = GraphConfig(
        nodes=[AgentRole.PLANNER, AgentRole.CODER, AgentRole.REVIEWER],
        edges=[
            GraphEdge(
                from_role=AgentRole.PLANNER,
                to_role=AgentRole.CODER,
            ),
            GraphEdge(
                from_role=AgentRole.PLANNER,
                to_role=AgentRole.REVIEWER,
                parallel=True,
            ),
        ],
    )

    next_nodes = _next_nodes(
        config,
        AgentRole.PLANNER,
        plan=None,
        code=None,
        review=None,
    )

    assert next_nodes == [AgentRole.CODER, AgentRole.REVIEWER]


def test_durable_routing_rejects_false_condition() -> None:
    """Durable routing uses the same predicate dialect as GraphRun."""
    dag = {
        "nodes": [{"id": "start"}, {"id": "wrong"}, {"id": "right"}],
        "edges": [
            {
                "from_node": "start",
                "to_node": "wrong",
                "condition": "review.approved == False",
            },
            {
                "from_node": "start",
                "to_node": "right",
                "condition": "review.approved == True",
            },
        ],
    }
    result = NodeResult(
        success=True,
        status="completed",
        output={"review": {"approved": True}},
    )

    assert _next_node(dag, "start", result) == "right"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Stream 5 gap: durable traversal stores one current_node_id and cannot "
        "execute and persist the multi-node frontier required for fan-out"
    ),
)
async def test_durable_run_must_execute_and_persist_parallel_frontier() -> None:
    """Migration target: the durable entrypoint executes and persists both branches."""
    dag = {
        "id": "stream5-fanout",
        "entry_node": "start",
        "nodes": [
            {"id": "start", "kind": _PassNode.kind, "inputs": {"text": "start"}},
            {"id": "left", "kind": _PassNode.kind, "inputs": {"text": "left"}},
            {"id": "right", "kind": _PassNode.kind, "inputs": {"text": "right"}},
        ],
        "edges": [
            {"from_node": "start", "to_node": "left", "parallel": True},
            {"from_node": "start", "to_node": "right", "parallel": True},
        ],
    }
    store = InMemoryDurableRunStore()

    record = await run_durable_dag(dag, store=store, node_resolver=_pass_resolver)
    persisted = await store.get(record.run_id)

    assert persisted is not None
    assert {node.node_id for node in persisted.node_records} == {"start", "left", "right"}
    assert all(node.phase.value == "completed" for node in persisted.node_records)
