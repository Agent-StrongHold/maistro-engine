"""Memory types: Learning, EpisodicMemory, Outcome, tiers, scopes (ADR-013)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class MemoryTier(StrEnum):
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    OPINION = "opinion"
    LESSON = "lesson"
    REGRET = "regret"
    AFFIRMATION = "affirmation"
    WISDOM = "wisdom"


WEIGHT_BOUNDS: dict[MemoryTier, tuple[float, float]] = {
    MemoryTier.OBSERVATION: (0.1, 0.5),
    MemoryTier.HYPOTHESIS: (0.2, 0.6),
    MemoryTier.OPINION: (0.3, 0.8),
    MemoryTier.LESSON: (0.5, 0.9),
    MemoryTier.REGRET: (0.6, 1.0),
    MemoryTier.AFFIRMATION: (0.6, 1.0),
    MemoryTier.WISDOM: (0.9, 1.0),
}

REINFORCE_DELTA: float = 0.05
CONTRADICT_DELTA: float = 0.05


class MemoryScope(StrEnum):
    GLOBAL = "global"
    ORGANIZATION = "organization"
    TEAM = "team"
    USER = "user"
    AGENT = "agent"
    SESSION = "session"


@dataclass
class Learning:
    category: str = "general"
    trigger_keys: list[str] = field(default_factory=list)
    learning: str = ""
    tool_name: str = ""
    source_query: str = ""
    org_id: str = ""
    team_id: str = ""
    agent_id: str | None = None
    user_id: str | None = None
    scope: MemoryScope = MemoryScope.AGENT
    hit_count: int = 0
    status: str = "active"
    id: int | None = None


@dataclass
class EpisodicMemory:
    memory_id: str = ""
    tier: MemoryTier = MemoryTier.OBSERVATION
    content: str = ""
    weight: float = 0.3
    org_id: str = ""
    team_id: str = ""
    agent_id: str | None = None
    user_id: str | None = None
    scope: MemoryScope = MemoryScope.AGENT
    source: str = ""
    context: dict[str, str] = field(default_factory=dict)
    reinforcement_count: int = 0
    contradiction_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted: bool = False


@dataclass
class Outcome:
    request_id: str = ""
    task_type: str = ""
    model_used: str = ""
    provider: str = ""
    tool_calls: list[dict[str, object]] = field(default_factory=list)
    success: bool = True
    error_type: str = ""
    response_time_ms: int = 0
    org_id: str = ""
    team_id: str = ""
    user_id: str = ""
    agent_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: int | None = None
