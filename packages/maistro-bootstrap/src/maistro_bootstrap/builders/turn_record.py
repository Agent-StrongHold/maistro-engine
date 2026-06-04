"""Structured turn records for builder session fitness signals.

Each TurnRecord captures the full signal chain: prompt → tool call → output → outcome → quality delta.
These records are persisted alongside the session and consumable by maistro-evolve for prompt,
tool, and topology optimization.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TurnRecord(BaseModel):
    """One agent turn's full signal chain for evolve fitness evaluation."""

    turn_id: str
    session_id: str
    timestamp: datetime = Field(default_factory=_utc_now)
    role: Literal["architect", "editor", "tester", "fallback"]
    model: str
    stage: str

    input_prompt: str = ""
    action_name: str = ""
    action_args: dict[str, Any] = Field(default_factory=dict)

    status: Literal["ok", "error", "needs_approval"] = "ok"
    output: str = ""
    output_metadata: dict[str, Any] = Field(default_factory=dict)

    quality_before: dict[str, Any] = Field(default_factory=dict)
    quality_after: dict[str, Any] = Field(default_factory=dict)

    elapsed_seconds: float = 0.0
    tokens_used: int = 0
    retry_count: int = 0

    @property
    def quality_delta(self) -> dict[str, float]:
        deltas: dict[str, float] = {}
        for key in self.quality_after:
            before = self.quality_before.get(key)
            after = self.quality_after.get(key)
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                deltas[key] = after - before
        return deltas

    @property
    def succeeded(self) -> bool:
        return self.status == "ok"

    @property
    def needs_human(self) -> bool:
        return self.status == "needs_approval"


class TurnOutcomeSummary(BaseModel):
    """Aggregate summary of turn records for a session, consumable by evolve."""

    session_id: str
    total_turns: int = 0
    successful_turns: int = 0
    error_turns: int = 0
    approval_turns: int = 0
    avg_elapsed_seconds: float = 0.0
    total_tokens: int = 0
    action_distribution: dict[str, int] = Field(default_factory=dict)
    role_distribution: dict[str, int] = Field(default_factory=dict)
    quality_deltas: dict[str, float] = Field(default_factory=dict)
    stages_visited: list[str] = Field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_turns == 0:
            return 0.0
        return self.successful_turns / self.total_turns

    @classmethod
    def from_records(cls, session_id: str, records: list[TurnRecord]) -> TurnOutcomeSummary:
        if not records:
            return cls(session_id=session_id)

        actions: dict[str, int] = {}
        roles: dict[str, int] = {}
        total_quality: dict[str, float] = {}
        stages: set[str] = set()

        for record in records:
            actions[record.action_name] = actions.get(record.action_name, 0) + 1
            roles[record.role] = roles.get(record.role, 0) + 1
            stages.add(record.stage)
            for key, delta in record.quality_delta.items():
                total_quality[key] = total_quality.get(key, 0.0) + delta

        avg_elapsed = sum(r.elapsed_seconds for r in records) / len(records)

        return cls(
            session_id=session_id,
            total_turns=len(records),
            successful_turns=sum(1 for r in records if r.succeeded),
            error_turns=sum(1 for r in records if r.status == "error"),
            approval_turns=sum(1 for r in records if r.needs_human),
            avg_elapsed_seconds=avg_elapsed,
            total_tokens=sum(r.tokens_used for r in records),
            action_distribution=actions,
            role_distribution=roles,
            quality_deltas=total_quality,
            stages_visited=sorted(stages),
        )
