"""Memory types: learnings, episodic memory, tiers, scopes.

The 7-tier episodic memory system with bounded weights.
Key insight: REGRET weight cannot drop below 0.6 — structurally unforgettable.

Merged from maistro.memory.types + upstream types.memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class MemoryTier(StrEnum):
    """Episodic memory confidence tiers with increasing weight bounds."""

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

INHERITANCE_PRIORITY: dict[MemoryTier, int] = {
    MemoryTier.OBSERVATION: 1,
    MemoryTier.HYPOTHESIS: 2,
    MemoryTier.OPINION: 3,
    MemoryTier.LESSON: 4,
    MemoryTier.REGRET: 5,
    MemoryTier.AFFIRMATION: 5,
    MemoryTier.WISDOM: 6,
}

REINFORCE_DELTA: float = 0.05
CONTRADICT_DELTA: float = 0.05

# Decay + reinforcement dynamics (ADR-080 part A / SPEC-240).
DEFAULT_DECAY_RATE: float = 0.01  # weight lost per hour at decay_rate=1.0
BOOST_RATE: float = 1.5  # weight multiplier on thumbs-up
DROP_RATE: float = 0.5  # weight multiplier on thumbs-down
SLOW_DECAY: float = 0.5  # decay_rate multiplier on thumbs-up
FAST_DECAY: float = 2.0  # decay_rate multiplier on thumbs-down
WISDOM_PROMOTE_THRESHOLD: int = 5  # reinforcement_count to promote -> WISDOM
REGRET_DEMOTE_THRESHOLD: int = 5  # contradiction_count to demote -> REGRET


class MemoryScope(StrEnum):
    """Memory visibility scopes — hierarchical from broadest to narrowest."""

    GLOBAL = "global"
    ORGANIZATION = "organization"
    TEAM = "team"
    USER = "user"
    AGENT = "agent"
    SESSION = "session"


@dataclass
class Learning:
    """A self-improving correction learned from tool call patterns."""

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
    rca_category: str | None = None
    rca_prevention: str = ""
    success_after_use: int = 0
    failure_after_use: int = 0


@dataclass
class Outcome:
    """The outcome of a completed request — tracks task completion rate."""

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
    charged_microchips: int = 0
    pricing_version: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: int | None = None
    # Phase 2 additions — per-project memory + per-DAG telemetry. Defaults
    # keep existing callers byte-identical; new code passes these so
    # get_experience_context can return a project-scoped failure narrative
    # without polluting another project's learning loop.
    project_id: str = ""
    dag_id: str = ""
    dag_run_id: str = ""
    node_id: str = ""
    # For Phase 5/6 optimizer signals — extended outcomes the user-thumbs
    # widget + eval-judge can land on this same record without needing a
    # parallel store.
    thumb: str = ""  # "" | "up" | "down"
    thumb_comment: str = ""
    eval_judge_score: float | None = None  # 0..100 if eval-judge ran


@dataclass
class SkillMutation:
    """Record of a skill being rewritten from a promoted learning."""

    skill_name: str = ""
    learning_id: int = 0
    old_prompt_hash: str = ""
    new_prompt_hash: str = ""
    mutation_type: str = "system_prompt_update"
    org_id: str = ""
    team_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: int | None = None


@dataclass
class EpisodicMemory:
    """A single episodic memory in the 7-tier weighted system."""

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
    decay_rate: float = DEFAULT_DECAY_RATE
