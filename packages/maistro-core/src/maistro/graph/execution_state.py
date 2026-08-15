"""Graph-specific execution state kept separate from canonical Run lifecycle.

``Run`` owns universal execution identity, scope, parentage and status.
``GraphExecutionState`` owns only traversal facts needed to resume a Graph:
the active frontier, cycle/visit information, blackboard state, and recorded
edge decisions.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


def _freeze_json(value: object, *, path: str) -> object:
    """Validate and recursively freeze a lossless JSON value."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite JSON numbers")
        return value
    if isinstance(value, list):
        return tuple(_freeze_json(item, path=f"{path}[]") for item in value)
    if isinstance(value, dict):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings")
            frozen[key] = _freeze_json(item, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    raise ValueError(f"{path} must contain only JSON values")


def _thaw_json(value: object) -> object:
    """Return ordinary JSON containers for persistence serialization."""
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


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
    """Persistable immutable traversal state associated with one canonical Run.

    This deliberately has no lifecycle status, retry/attempt counters, scope,
    deadlines, or terminal result. Those belong to Run/NodeRun/Attempt. Visit
    counts are traversal facts only: they let a cyclic graph distinguish the
    first visit to a node from later visits without pretending that a node has
    only one logical execution.

    State transitions create a newly validated instance. Tuple frontiers and
    decisions plus read-only mappings prevent a valid checkpoint from being
    mutated into an invalid one after construction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    active_node_ids: tuple[str, ...] = Field(default_factory=tuple)
    cycle: int = Field(default=0, ge=0)
    visit_counts: Mapping[str, int] = Field(default_factory=dict)
    blackboard_snapshot: Mapping[str, Any] = Field(default_factory=dict)
    edge_decisions: tuple[GraphEdgeDecision, ...] = Field(default_factory=tuple)
    metadata: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("run_id")
    @classmethod
    def _validate_run_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run_id must be a non-empty string")
        return value

    @field_validator("active_node_ids")
    @classmethod
    def _validate_active_node_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("active_node_ids must not contain duplicates")
        if any(not node_id.strip() for node_id in value):
            raise ValueError("active_node_ids must contain non-empty strings")
        return value

    @field_validator("visit_counts", mode="after")
    @classmethod
    def _freeze_visit_counts(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        snapshot = dict(value)
        if any(not node_id.strip() for node_id in snapshot):
            raise ValueError("visit_counts keys must be non-empty strings")
        if any(count < 0 for count in snapshot.values()):
            raise ValueError("visit_counts values must be non-negative")
        return MappingProxyType(snapshot)

    @field_validator("blackboard_snapshot", "metadata", mode="after")
    @classmethod
    def _freeze_json_mapping(cls, value: Mapping[str, Any], info: Any) -> Mapping[str, Any]:
        frozen = _freeze_json(dict(value), path=str(info.field_name))
        if not isinstance(frozen, Mapping):
            raise ValueError(f"{info.field_name} must be a JSON object")
        return frozen

    @field_validator("edge_decisions")
    @classmethod
    def _validate_edge_decisions(
        cls, value: tuple[GraphEdgeDecision, ...]
    ) -> tuple[GraphEdgeDecision, ...]:
        decision_keys = [
            (decision.source_node_run_id, decision.edge_id) for decision in value
        ]
        if len(decision_keys) != len(set(decision_keys)):
            raise ValueError("edge_decisions must be unique per source_node_run_id and edge_id")
        return value

    @field_serializer("visit_counts", "blackboard_snapshot", "metadata")
    def _serialize_mapping(self, value: Mapping[str, Any]) -> dict[str, Any]:
        thawed = _thaw_json(value)
        if not isinstance(thawed, dict):
            raise TypeError("graph execution mappings must serialize as JSON objects")
        return thawed


__all__ = ["GraphEdgeDecision", "GraphExecutionState"]
