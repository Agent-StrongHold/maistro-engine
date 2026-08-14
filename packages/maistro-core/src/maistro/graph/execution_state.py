"""Graph-specific execution state kept separate from canonical Run lifecycle.

``Run`` owns universal execution identity, scope, parentage and status.
``GraphExecutionState`` owns only traversal facts needed to resume a Graph:
the active frontier, cycle/visit information, blackboard state, and recorded
edge decisions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GraphEdgeDecision(BaseModel):
    """Immutable routing fact produced by one completed source NodeRun."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str
    source_node_id: str
    source_node_run_id: str
    target_node_id: str
    selected: bool
    cycle: int = Field(ge=0)
    condition: str | None = None

    @model_validator(mode="after")
    def _validate_identity(self) -> GraphEdgeDecision:
        for value, name in (
            (self.edge_id, "edge_id"),
            (self.source_node_id, "source_node_id"),
            (self.source_node_run_id, "source_node_run_id"),
            (self.target_node_id, "target_node_id"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        return self


class GraphExecutionState(BaseModel):
    """Persistable traversal state associated with one canonical Run.

    This deliberately has no lifecycle status, retry/attempt counters, scope,
    deadlines, or terminal result. Those belong to Run/NodeRun/Attempt. Visit
    counts are traversal facts only: they let a cyclic graph distinguish the
    first visit to a node from later visits without pretending that a node has
    only one logical execution.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    active_node_ids: list[str] = Field(default_factory=list)
    cycle: int = Field(default=0, ge=0)
    visit_counts: dict[str, int] = Field(default_factory=dict)
    blackboard_snapshot: dict[str, Any] = Field(default_factory=dict)
    edge_decisions: list[GraphEdgeDecision] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_state(self) -> GraphExecutionState:
        if not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if len(self.active_node_ids) != len(set(self.active_node_ids)):
            raise ValueError("active_node_ids must not contain duplicates")
        if any(not node_id.strip() for node_id in self.active_node_ids):
            raise ValueError("active_node_ids must contain non-empty strings")
        if any(not node_id.strip() for node_id in self.visit_counts):
            raise ValueError("visit_counts keys must be non-empty strings")
        if any(count < 0 for count in self.visit_counts.values()):
            raise ValueError("visit_counts values must be non-negative")
        return self


__all__ = ["GraphEdgeDecision", "GraphExecutionState"]
