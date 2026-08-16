"""Canonical durable graph persistence envelope."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maistro.graph.execution_state import GraphExecutionState
from maistro.runs.model import Attempt, NodeRun, Run, RunStatus


class DurableRunRecord(BaseModel):
    """Persisted canonical Run plus graph-specific continuation state."""

    model_config = ConfigDict(extra="forbid")

    run: Run
    graph_state: GraphExecutionState
    node_runs: tuple[NodeRun, ...] = Field(default_factory=tuple)
    attempts: tuple[Attempt, ...] = Field(default_factory=tuple)
    resume_at: datetime | None = None
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_links(self) -> DurableRunRecord:
        if self.graph_state.run_id != self.run.run_id:
            raise ValueError("graph_state.run_id must match run.run_id")
        if any(node_run.run_id != self.run.run_id for node_run in self.node_runs):
            raise ValueError("every NodeRun must belong to the persisted Run")
        ordinals = [node_run.ordinal for node_run in self.node_runs]
        if ordinals != list(range(1, len(ordinals) + 1)):
            raise ValueError("NodeRun ordinals must be consecutive in persistence order")

        node_run_ids = {node_run.node_run_id for node_run in self.node_runs}
        if any(attempt.node_run_id not in node_run_ids for attempt in self.attempts):
            raise ValueError("every Attempt must belong to a persisted NodeRun")
        attempts_by_node_run: dict[str, list[int]] = {}
        for attempt in self.attempts:
            attempts_by_node_run.setdefault(attempt.node_run_id, []).append(attempt.ordinal)
        if any(
            ordinals != list(range(1, len(ordinals) + 1))
            for ordinals in attempts_by_node_run.values()
        ):
            raise ValueError("Attempt ordinals must be consecutive per NodeRun")

        node_ids = {node.node_id for node in self.run.graph.materialize().nodes}
        if any(node_id not in node_ids for node_id in self.graph_state.active_node_ids):
            raise ValueError("active graph frontier must reference nodes in the Run Graph snapshot")
        return self

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

    _ = _vulture_pydantic_contract_usage


__all__ = ["DurableRunRecord", "RunStatus"]
