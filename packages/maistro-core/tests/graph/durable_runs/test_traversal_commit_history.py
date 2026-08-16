from __future__ import annotations

from datetime import UTC, datetime

import pytest

from maistro.graph import (
    Edge,
    Graph,
    GraphEdgeDecision,
    GraphExecutionState,
    Node,
    TraversalCommit,
)
from maistro.graph.durable_runs import DurableRunRecord
from maistro.runs import (
    AcceptedNodeOutcome,
    AttemptResult,
    AttemptStatus,
    GraphSnapshot,
    NodeRun,
    Run,
    RunStatus,
)


def _fixture() -> tuple[Run, NodeRun, GraphExecutionState, TraversalCommit]:
    graph = Graph(
        workspace_id="ws-1",
        project_id="project-1",
        name="Traversal commits",
        nodes=[
            Node(node_id="a", node_type="agent"),
            Node(node_id="b", node_type="agent"),
        ],
        edges=[Edge(from_node="a", to_node="b")],
    )
    run = Run(
        run_id="run-1",
        workspace_id=graph.workspace_id,
        project_id=graph.project_id,
        graph=GraphSnapshot.from_graph(graph),
        status=RunStatus.RUNNING,
    )
    physical = AttemptResult(
        attempt_id="attempt-a",
        node_run_id="node-run-a",
        ordinal=1,
        status=AttemptStatus.COMPLETED,
        result={"physical": "envelope"},
        finished_at=datetime(2026, 8, 16, 10, 0, tzinfo=UTC),
    )
    outcome = AcceptedNodeOutcome(
        node_run_id="node-run-a",
        attempt_result=physical,
        logical_status=RunStatus.COMPLETED,
        result={"value": 7},
    )
    node_run = NodeRun(
        node_run_id="node-run-a",
        run_id=run.run_id,
        node_id="a",
        ordinal=1,
        status=RunStatus.COMPLETED,
        finished_at=datetime(2026, 8, 16, 10, 1, tzinfo=UTC),
        accepted_outcome=outcome,
        result={"value": 7},
    )
    prior = GraphExecutionState(run_id=run.run_id, active_node_ids=("a",))
    decision = GraphEdgeDecision(
        edge_id="edge-a-b",
        source_node_id="a",
        source_node_run_id=node_run.node_run_id,
        target_node_id="b",
        selected=True,
        cycle=0,
    )
    resulting = GraphExecutionState(
        run_id=run.run_id,
        active_node_ids=("b",),
        cycle=1,
        visit_counts={"a": 1},
        edge_decisions=(decision,),
    )
    commit = TraversalCommit.from_transition(
        graph_snapshot_hash=run.graph.content_hash,
        prior_state=prior,
        resulting_state=resulting,
        ordered_source_node_run_ids=(node_run.node_run_id,),
        accepted_outcomes=(outcome,),
        edge_decisions=(decision,),
        commit_sequence=1,
    )
    return run, node_run, resulting, commit


def test_durable_record_accepts_verified_commit_chain_and_exposes_latest() -> None:
    run, node_run, state, commit = _fixture()

    record = DurableRunRecord(
        run=run,
        graph_state=state,
        node_runs=(node_run,),
        traversal_commits=(commit,),
        version=4,
    )

    assert record.latest_traversal_commit == commit


def test_latest_commit_must_project_current_graph_state() -> None:
    run, node_run, state, commit = _fixture()
    drifted = state.model_copy(update={"active_node_ids": ()})

    with pytest.raises(ValueError, match="latest TraversalCommit"):
        DurableRunRecord(
            run=run,
            graph_state=drifted,
            node_runs=(node_run,),
            traversal_commits=(commit,),
        )


def test_commit_outcome_identity_must_match_persisted_accepted_node_outcome() -> None:
    run, node_run, state, commit = _fixture()
    altered_outcome = node_run.accepted_outcome.model_copy(update={"result": {"value": 8}})
    altered_node_run = node_run.model_copy(
        update={"result": {"value": 8}, "accepted_outcome": altered_outcome}
    )

    with pytest.raises(ValueError, match="outcome identities"):
        DurableRunRecord(
            run=run,
            graph_state=state,
            node_runs=(altered_node_run,),
            traversal_commits=(commit,),
        )


def test_commit_graph_snapshot_must_match_run_snapshot() -> None:
    run, node_run, state, commit = _fixture()
    payload = commit.model_dump(mode="python")
    payload["graph_snapshot_hash"] = "different"
    payload["traversal_commit_id"] = commit.traversal_commit_id

    with pytest.raises(ValueError):
        TraversalCommit.model_validate(payload)
