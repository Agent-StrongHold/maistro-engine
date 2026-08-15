"""Focused parity coverage for durable graph edge routing."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from maistro.graph.durable_runs import DurableNodeRecord, DurableRunRecord, NodePhase
from maistro.graph.durable_runs.executor import _next_node
from maistro.graph.nodes.base import NodeResult


class _Review(BaseModel):
    approved: bool
    score: float


class _Envelope(BaseModel):
    review: _Review


def _result(output: object) -> NodeResult:
    return NodeResult(success=True, status="completed", output=output)


def test_node_result_preserves_mapping_output() -> None:
    payload = {"review": {"approved": True, "score": 9.0}}

    assert _result(payload).output == payload


def test_false_condition_falls_through_to_matching_condition() -> None:
    dag = {
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
        ]
    }

    assert _next_node(dag, "start", _result({"review": {"approved": True}})) == "right"


def test_false_condition_falls_through_to_unconditional_edge() -> None:
    dag = {
        "edges": [
            {
                "from_node": "start",
                "to_node": "conditional",
                "condition": "review.approved == True",
            },
            {"from_node": "start", "to_node": "fallback"},
        ]
    }

    assert _next_node(dag, "start", _result({"review": {"approved": False}})) == "fallback"


def test_numeric_comparison_uses_canonical_predicate_dialect() -> None:
    dag = {
        "edges": [
            {
                "from_node": "start",
                "to_node": "high",
                "condition": "review.score >= 8",
            },
            {"from_node": "start", "to_node": "low"},
        ]
    }

    assert _next_node(dag, "start", _result({"review": {"score": 8.5}})) == "high"


def test_pydantic_output_supports_dotted_condition_paths() -> None:
    dag = {
        "edges": [
            {
                "from_node": "start",
                "to_node": "approved",
                "condition": "review.approved is True",
            }
        ]
    }
    output = _Envelope(review=_Review(approved=True, score=9.0))

    assert _next_node(dag, "start", _result(output)) == "approved"


def test_typed_reviewer_output_uses_canonical_review_namespace() -> None:
    dag = {
        "nodes": [{"id": "reviewer", "kind": "llm.review"}],
        "edges": [
            {
                "from_node": "reviewer",
                "to_node": "approved",
                "condition": "review.approved == True",
            }
        ],
    }

    assert _next_node(dag, "reviewer", _result(_Review(approved=True, score=9.0))) == "approved"


def test_condition_can_read_prior_canonical_node_output() -> None:
    dag = {
        "id": "routing-state",
        "nodes": [
            {"id": "planner", "kind": "llm.plan"},
            {"id": "coder", "kind": "llm.code"},
        ],
        "edges": [
            {
                "from_node": "coder",
                "to_node": "ready",
                "condition": "plan.summary == 'ready'",
            }
        ],
    }
    now = datetime.now(UTC)
    record = DurableRunRecord(
        run_id="r-routing",
        dag_id="routing-state",
        dag_snapshot=dag,
        node_records=[
            DurableNodeRecord(
                node_id="planner",
                kind="llm.plan",
                phase=NodePhase.COMPLETED,
                output={"summary": "ready"},
            )
        ],
        started_at=now,
        last_step_at=now,
    )

    assert _next_node(dag, "coder", _result({"artifact": "code"}), record) == "ready"


def test_missing_condition_path_does_not_match() -> None:
    dag = {
        "edges": [
            {
                "from_node": "start",
                "to_node": "missing",
                "condition": "review.score >= 8",
            }
        ]
    }

    assert _next_node(dag, "start", _result({"other": {"score": 10}})) is None


def test_first_matching_edge_keeps_document_order_precedence() -> None:
    dag = {
        "edges": [
            {
                "from_node": "start",
                "to_node": "first",
                "condition": "review.approved == True",
            },
            {"from_node": "start", "to_node": "second"},
        ]
    }

    assert _next_node(dag, "start", _result({"review": {"approved": True}})) == "first"


def test_targetless_matching_edge_does_not_hide_later_route() -> None:
    dag = {
        "edges": [
            {"from_node": "start", "condition": "review.approved == True"},
            {"from_node": "start", "to_node": "next"},
        ]
    }

    assert _next_node(dag, "start", _result({"review": {"approved": True}})) == "next"
