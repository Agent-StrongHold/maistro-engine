"""Characterization and migration-target tests for Stream 5 graph convergence.

These tests deliberately separate behavior that is already authoritative in
``GraphRun`` from known durable-executor gaps. The xfailed cases describe the
canonical behavior Stream 5 must make real once the Run/NodeRun/Attempt spine
from Stream 1 lands.

They must not be "fixed" by weakening the assertions or by teaching the tests
about another temporary lifecycle model.
"""

from __future__ import annotations

import pytest

from maistro.graph.durable_runs.executor import _next_node
from maistro.graph.nodes.base import NodeResult
from maistro.graph.run import _next_nodes
from maistro.graph.types import AgentRole, GraphConfig, GraphEdge, ReviewOutput


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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Stream 5 gap: durable _next_node chooses the first conditional edge "
        "instead of evaluating predicates"
    ),
)
def test_durable_routing_must_reject_false_condition() -> None:
    """Migration target: durable routing must agree with canonical predicates."""
    dag = {
        "nodes": [{"id": "start"}, {"id": "wrong"}, {"id": "right"}],
        "edges": [
            {
                "from_node": "start",
                "to_node": "wrong",
                "condition": "approved == false",
            },
            {
                "from_node": "start",
                "to_node": "right",
                "condition": "approved == true",
            },
        ],
    }
    result = NodeResult(
        success=True,
        status="completed",
        output={"approved": True},
    )

    assert _next_node(dag, "start", result) == "right"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Stream 5 gap: durable traversal stores one current_node_id and cannot "
        "represent the multi-node frontier required for fan-out"
    ),
)
def test_durable_routing_must_preserve_parallel_frontier() -> None:
    """Migration target: durable graph state represents all selected targets."""
    dag = {
        "nodes": [{"id": "start"}, {"id": "left"}, {"id": "right"}],
        "edges": [
            {"from_node": "start", "to_node": "left", "parallel": True},
            {"from_node": "start", "to_node": "right", "parallel": True},
        ],
    }
    result = NodeResult(success=True, status="completed", output=None)

    # The canonical GraphExecutionState frontier is intentionally expressed as
    # a collection here. Today's durable helper returns a single string.
    assert _next_node(dag, "start", result) == ["left", "right"]
