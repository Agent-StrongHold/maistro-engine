"""Agent type definitions — roles, task specs, and structured outputs."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class LLMProviderError(Exception):
    """Raised when the LLM provider fails after exhausting retries."""


class ExecutionMode(StrEnum):
    """Control-flow tier for a task.

    TASK      — single model call; predictable cost, bounded failure modes.
    WORKFLOW  — fixed sequence of model calls; developer controls flow.
    AGENT     — autonomous loop; model decides its own trajectory at runtime.
    GRAPH     — hyperagent orchestrates a directed graph of sub-agents; topology
                is set by the developer, routing decisions are made dynamically
                by the hyperagent node based on intermediate outputs. This is the
                primary pattern for complex multi-role tasks (plan → code →
                review → retry cycles).

    Prefer TASK or WORKFLOW when steps are fully known in advance. Use AGENT
    for ambiguous single-actor problems with verifiable outputs (coding). Use
    GRAPH when multiple specialized roles collaborate and routing between them
    depends on runtime results.
    """

    TASK = "task"
    WORKFLOW = "workflow"
    AGENT = "agent"
    GRAPH = "graph"


class AgentRole(StrEnum):
    CONDUCTOR = "conductor"
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    SCOUT = "scout"


# ---------------------------------------------------------------------------
# Graph / hyperagent models
# ---------------------------------------------------------------------------


class GraphEdge(BaseModel):
    """Directed edge between two sub-agent nodes in a graph execution.

    `condition` is an optional free-text predicate evaluated against accumulated
    node outputs (e.g. "review.approved is False").  None means always traverse.

    `parallel=True` marks the edge as a fan-out edge: all matching parallel edges
    from the same node fire concurrently via asyncio.gather.  Sequential edges
    (parallel=False, the default) use first-match routing — at most one fires.
    Both types can co-exist on the same source node.

    `to_role=None` is a terminal edge: reaching it stops the graph from this node.
    """

    from_role: AgentRole
    to_role: AgentRole | None
    condition: str | None = None
    parallel: bool = False


class GraphConfig(BaseModel):
    """Topology of a hyperagent graph execution.

    Defines which sub-agent nodes participate, how they are connected, where
    execution starts, which node acts as the hyperagent orchestrator, and a
    cycle cap to prevent runaway loops.
    """

    nodes: list[AgentRole]
    edges: list[GraphEdge] = Field(default_factory=list)
    entry: AgentRole = AgentRole.PLANNER
    hyperagent: AgentRole = AgentRole.CONDUCTOR
    max_cycles: int = Field(default=5, ge=1, le=20)


class GraphNodeResult(BaseModel):
    """Output produced by a single sub-agent node during graph execution.

    For beam-search runs (parallel_generations > 1), `candidates` holds every
    generation's output string and `selected_candidate` is the index of the one
    chosen by the scoring heuristic.  `output` is always the selected candidate.

    `parallel_group` is set to the cycle index when multiple nodes ran in the
    same asyncio.gather batch (fan-out), so callers can group concurrent steps.
    """

    role: AgentRole
    success: bool
    output: str  # selected candidate (truncated to 500 chars)
    tokens_used: int = 0
    next_nodes: list[AgentRole] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)  # all beam outputs
    selected_candidate: int = 0  # index into candidates of the winning output
    parallel_group: int | None = None  # cycle index if part of a fan-out batch


class SubTask(BaseModel):
    """A single subtask produced by the planner."""

    title: str
    description: str
    file_paths: list[str] = Field(default_factory=list)


class PlanOutput(BaseModel):
    """Structured output from the planning phase."""

    summary: str
    subtasks: list[SubTask]
    estimated_files: list[str] = Field(default_factory=list)


class CodeOutput(BaseModel):
    """Structured output from the coding phase."""

    files_changed: list[str]
    description: str
    tests_added: bool = False


class ReviewOutput(BaseModel):
    """Structured output from the review phase."""

    approved: bool
    score: float = Field(ge=0, le=10)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ConductorOutput(BaseModel):
    """Top-level output from the conductor — wraps the full pipeline result."""

    plan: PlanOutput | None = None
    code: CodeOutput | None = None
    review: ReviewOutput | None = None
    final_answer: str = ""
    success: bool = True


class HyperagentOutput(ConductorOutput):
    """Output from a GRAPH-mode execution.

    Extends ConductorOutput with the per-node trace produced by each sub-agent
    and the graph config that was used so callers can correlate routing decisions
    with results.
    """

    graph_config: GraphConfig | None = None
    node_results: list[GraphNodeResult] = Field(default_factory=list)
    total_cycles: int = 0
