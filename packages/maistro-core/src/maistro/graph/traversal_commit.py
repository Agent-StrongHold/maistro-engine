"""Authoritative durable commits for logical Graph traversal advancement.

Physical node execution and routing facts may exist before traversal advances.
A :class:`TraversalCommit` binds those accepted facts to one deterministic
transition from a prior GraphExecutionState to its resulting state. Recovery
can therefore distinguish completed physical work from authoritative logical
advancement.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from maistro.graph.execution_state import GraphEdgeDecision, GraphExecutionState
from maistro.runs.model import AcceptedNodeOutcome


def _digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def graph_state_hash(state: GraphExecutionState) -> str:
    return _digest(state.model_dump(mode="json"))


def edge_decision_id(decision: GraphEdgeDecision) -> str:
    return _digest(decision.model_dump(mode="json"))


def accepted_outcome_id(outcome: AcceptedNodeOutcome) -> str:
    """Hash physical evidence plus its accepted logical projection, excluding wall-clock acceptance."""
    return _digest(
        {
            "node_run_id": outcome.node_run_id,
            "attempt_id": outcome.attempt_result.attempt_id,
            "attempt_ordinal": outcome.attempt_result.ordinal,
            "attempt_status": outcome.attempt_result.status.value,
            "attempt_result": outcome.attempt_result.result,
            "attempt_error": outcome.attempt_result.error,
            "attempt_finished_at": outcome.attempt_result.finished_at.isoformat(),
            "logical_status": outcome.logical_status.value,
            "logical_result": outcome.result,
            "logical_error": outcome.error,
        }
    )


def _commit_identity(
    *,
    run_id: str,
    prior_commit_id: str | None,
    graph_snapshot_hash: str,
    prior_state_hash: str,
    ordered_source_node_run_ids: tuple[str, ...],
    accepted_outcome_ids: tuple[str, ...],
    edge_decision_ids: tuple[str, ...],
    resulting_frontier: tuple[str, ...],
    resulting_state_hash: str,
    checkpoint_id: str | None,
    commit_sequence: int,
) -> str:
    return _digest(
        {
            "run_id": run_id,
            "prior_commit_id": prior_commit_id,
            "graph_snapshot_hash": graph_snapshot_hash,
            "prior_state_hash": prior_state_hash,
            "ordered_source_node_run_ids": ordered_source_node_run_ids,
            "accepted_outcome_ids": accepted_outcome_ids,
            "edge_decision_ids": edge_decision_ids,
            "resulting_frontier": resulting_frontier,
            "resulting_state_hash": resulting_state_hash,
            "checkpoint_id": checkpoint_id,
            "commit_sequence": commit_sequence,
        }
    )


class TraversalCommit(BaseModel):
    """One accepted logical transition between durable Graph traversal states."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    traversal_commit_id: str
    run_id: str
    prior_commit_id: str | None = None
    graph_snapshot_hash: str
    prior_state_hash: str
    ordered_source_node_run_ids: tuple[str, ...]
    accepted_outcome_ids: tuple[str, ...]
    edge_decision_ids: tuple[str, ...]
    resulting_frontier: tuple[str, ...]
    resulting_state_hash: str
    checkpoint_id: str | None = None
    commit_sequence: int = Field(ge=1)
    committed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator(
        "traversal_commit_id",
        "run_id",
        "graph_snapshot_hash",
        "prior_state_hash",
        "resulting_state_hash",
    )
    @classmethod
    def _non_empty_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("TraversalCommit identities and hashes must be non-empty")
        return value

    @field_validator(
        "ordered_source_node_run_ids",
        "accepted_outcome_ids",
        "edge_decision_ids",
        "resulting_frontier",
    )
    @classmethod
    def _non_empty_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("TraversalCommit identity collections cannot contain empty values")
        return value

    @model_validator(mode="after")
    def _validate_cardinality_and_identity(self) -> TraversalCommit:
        if len(self.ordered_source_node_run_ids) != len(set(self.ordered_source_node_run_ids)):
            raise ValueError("source NodeRuns must appear once per TraversalCommit")
        if len(self.accepted_outcome_ids) != len(self.ordered_source_node_run_ids):
            raise ValueError("every source NodeRun must contribute one accepted outcome")
        if len(self.accepted_outcome_ids) != len(set(self.accepted_outcome_ids)):
            raise ValueError("accepted outcomes must be unique per TraversalCommit")
        if len(self.edge_decision_ids) != len(set(self.edge_decision_ids)):
            raise ValueError("edge decisions must be unique per TraversalCommit")
        if len(self.resulting_frontier) != len(set(self.resulting_frontier)):
            raise ValueError("resulting frontier must not contain duplicate nodes")
        expected = _commit_identity(
            run_id=self.run_id,
            prior_commit_id=self.prior_commit_id,
            graph_snapshot_hash=self.graph_snapshot_hash,
            prior_state_hash=self.prior_state_hash,
            ordered_source_node_run_ids=self.ordered_source_node_run_ids,
            accepted_outcome_ids=self.accepted_outcome_ids,
            edge_decision_ids=self.edge_decision_ids,
            resulting_frontier=self.resulting_frontier,
            resulting_state_hash=self.resulting_state_hash,
            checkpoint_id=self.checkpoint_id,
            commit_sequence=self.commit_sequence,
        )
        if self.traversal_commit_id != expected:
            raise ValueError("TraversalCommit identity does not match its authoritative content")
        return self

    @classmethod
    def from_transition(
        cls,
        *,
        graph_snapshot_hash: str,
        prior_state: GraphExecutionState,
        resulting_state: GraphExecutionState,
        ordered_source_node_run_ids: tuple[str, ...],
        accepted_outcomes: tuple[AcceptedNodeOutcome, ...],
        edge_decisions: tuple[GraphEdgeDecision, ...],
        commit_sequence: int,
        prior_commit_id: str | None = None,
        checkpoint_id: str | None = None,
    ) -> TraversalCommit:
        if prior_state.run_id != resulting_state.run_id:
            raise ValueError("TraversalCommit cannot cross Run identity")
        outcome_node_runs = tuple(outcome.node_run_id for outcome in accepted_outcomes)
        if outcome_node_runs != ordered_source_node_run_ids:
            raise ValueError("accepted outcomes must match source NodeRuns in deterministic order")
        source_set = set(ordered_source_node_run_ids)
        if any(decision.source_node_run_id not in source_set for decision in edge_decisions):
            raise ValueError("routing decisions must come from this commit's source NodeRuns")

        prior_hash = graph_state_hash(prior_state)
        outcome_ids = tuple(accepted_outcome_id(item) for item in accepted_outcomes)
        decision_ids = tuple(edge_decision_id(item) for item in edge_decisions)
        frontier = resulting_state.active_node_ids
        resulting_hash = graph_state_hash(resulting_state)
        commit_id = _commit_identity(
            run_id=prior_state.run_id,
            prior_commit_id=prior_commit_id,
            graph_snapshot_hash=graph_snapshot_hash,
            prior_state_hash=prior_hash,
            ordered_source_node_run_ids=ordered_source_node_run_ids,
            accepted_outcome_ids=outcome_ids,
            edge_decision_ids=decision_ids,
            resulting_frontier=frontier,
            resulting_state_hash=resulting_hash,
            checkpoint_id=checkpoint_id,
            commit_sequence=commit_sequence,
        )
        return cls(
            traversal_commit_id=commit_id,
            run_id=prior_state.run_id,
            prior_commit_id=prior_commit_id,
            graph_snapshot_hash=graph_snapshot_hash,
            prior_state_hash=prior_hash,
            ordered_source_node_run_ids=ordered_source_node_run_ids,
            accepted_outcome_ids=outcome_ids,
            edge_decision_ids=decision_ids,
            resulting_frontier=frontier,
            resulting_state_hash=resulting_hash,
            checkpoint_id=checkpoint_id,
            commit_sequence=commit_sequence,
        )


__all__ = ["TraversalCommit", "accepted_outcome_id", "edge_decision_id", "graph_state_hash"]
