"""Canonical durable graph persistence envelope."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maistro.graph.execution_state import GraphExecutionState
from maistro.graph.traversal_commit import (
    TraversalCommit,
    accepted_outcome_id,
    edge_decision_id,
    graph_state_hash,
)
from maistro.runs.model import Attempt, NodeRun, Run, RunStatus


class DurableRunRecord(BaseModel):
    """Persisted canonical Run plus graph continuation, physical history, and commits."""

    model_config = ConfigDict(extra="forbid")

    run: Run
    graph_state: GraphExecutionState
    node_runs: tuple[NodeRun, ...] = Field(default_factory=tuple)
    attempts: tuple[Attempt, ...] = Field(default_factory=tuple)
    traversal_commits: tuple[TraversalCommit, ...] = Field(default_factory=tuple)
    resume_at: datetime | None = None
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_links(self) -> DurableRunRecord:
        if self.graph_state.run_id != self.run.run_id:
            raise ValueError("graph_state.run_id must match run.run_id")
        if any(node_run.run_id != self.run.run_id for node_run in self.node_runs):
            raise ValueError("every NodeRun must belong to the persisted Run")
        node_run_ordinals = [node_run.ordinal for node_run in self.node_runs]
        if node_run_ordinals != list(range(1, len(node_run_ordinals) + 1)):
            raise ValueError("NodeRun ordinals must be consecutive in persistence order")
        node_runs_by_id = {node_run.node_run_id: node_run for node_run in self.node_runs}
        if any(attempt.node_run_id not in node_runs_by_id for attempt in self.attempts):
            raise ValueError("every Attempt must belong to a persisted NodeRun")
        attempts_by_node_run: dict[str, list[int]] = {}
        for attempt in self.attempts:
            attempts_by_node_run.setdefault(attempt.node_run_id, []).append(attempt.ordinal)
        if any(
            ordinals != list(range(1, len(ordinals) + 1))
            for ordinals in attempts_by_node_run.values()
        ):
            raise ValueError("Attempt ordinals must be consecutive within each NodeRun")
        node_ids = {node.node_id for node in self.run.graph.materialize().nodes}
        if any(node_id not in node_ids for node_id in self.graph_state.active_node_ids):
            raise ValueError("active graph frontier must reference nodes in the Run Graph snapshot")
        self._validate_traversal_commits(node_runs_by_id)
        return self

    def _validate_traversal_commits(self, node_runs_by_id: dict[str, NodeRun]) -> None:
        commits = self.traversal_commits
        if not commits:
            return
        if [commit.commit_sequence for commit in commits] != list(range(1, len(commits) + 1)):
            raise ValueError("TraversalCommit sequences must be consecutive from one")
        all_decision_ids = {edge_decision_id(item) for item in self.graph_state.edge_decisions}
        previous_id: str | None = None
        for commit in commits:
            if commit.run_id != self.run.run_id:
                raise ValueError("every TraversalCommit must belong to the persisted Run")
            if commit.graph_snapshot_hash != self.run.graph.content_hash:
                raise ValueError("TraversalCommit graph snapshot must match the Run snapshot")
            if commit.prior_commit_id != previous_id:
                raise ValueError("TraversalCommit history must form one parent-linked chain")
            source_runs: list[NodeRun] = []
            for node_run_id in commit.ordered_source_node_run_ids:
                source = node_runs_by_id.get(node_run_id)
                if source is None:
                    raise ValueError("TraversalCommit source NodeRun must be persisted")
                if source.accepted_outcome is None:
                    raise ValueError("TraversalCommit source NodeRun requires an accepted outcome")
                source_runs.append(source)
            persisted_outcome_ids = tuple(
                accepted_outcome_id(source.accepted_outcome) for source in source_runs
            )
            if persisted_outcome_ids != commit.accepted_outcome_ids:
                raise ValueError("TraversalCommit outcome identities must match persisted NodeRuns")
            if any(decision_id not in all_decision_ids for decision_id in commit.edge_decision_ids):
                raise ValueError("TraversalCommit routing decisions must exist in GraphExecutionState")
            previous_id = commit.traversal_commit_id
        if commits[-1].resulting_state_hash != graph_state_hash(self.graph_state):
            raise ValueError("latest TraversalCommit must project the persisted GraphExecutionState")

    @property
    def run_id(self) -> str:
        return self.run.run_id

    @property
    def status(self) -> RunStatus:
        return self.run.status

    @property
    def project_id(self) -> str:
        return self.run.project_id

    @property
    def active_node_id(self) -> str | None:
        active = self.graph_state.active_node_ids
        return active[0] if active else None

    @property
    def latest_traversal_commit(self) -> TraversalCommit | None:
        return self.traversal_commits[-1] if self.traversal_commits else None

    @property
    def hitl_answers(self) -> dict[str, dict[str, object]]:
        raw = self.graph_state.metadata.get("hitl_answers", {})
        if not isinstance(raw, Mapping):
            return {}
        return {
            str(node_id): dict(answer)
            for node_id, answer in raw.items()
            if isinstance(answer, Mapping)
        }


if TYPE_CHECKING:

    def _vulture_pydantic_contract_usage(record: DurableRunRecord) -> None:
        _ = record._validate_links
        _ = record._validate_traversal_commits

    _ = _vulture_pydantic_contract_usage


__all__ = ["DurableRunRecord", "RunStatus"]
