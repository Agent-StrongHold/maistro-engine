"""Agent type definitions — roles, task specs, and structured outputs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

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


# ---------------------------------------------------------------------------
# Blackboard — shared situational awareness across all nodes
# ---------------------------------------------------------------------------


class ScoutContext(BaseModel):
    """What the SCOUT node found in the workspace.

    Populated before (or concurrently with) PLANNER so all nodes start with
    shared situational awareness of the codebase rather than working blind.
    """

    relevant_files: list[str] = Field(default_factory=list)
    patterns: str = ""  # free-form findings: conventions, idioms, anti-patterns
    dependency_map: dict[str, list[str]] = Field(default_factory=dict)  # file → imports
    similar_implementations: list[str] = Field(default_factory=list)  # existing examples
    raw_findings: str = ""  # full scout output for nodes that need more detail


class ToolEvaluation(BaseModel):
    """Objective evaluation produced by running the code in the sandbox.

    Replaces (or supplements) model self-review with hard pass/fail signal.
    The optimizer uses evaluation_score as its primary gradient when available.
    """

    tests_passed: int = 0
    tests_failed: int = 0
    test_output: str = ""
    lint_errors: list[str] = Field(default_factory=list)
    type_errors: list[str] = Field(default_factory=list)
    evaluation_score: float = Field(default=0.0, ge=0, le=10)  # derived from results

    @property
    def total_tests(self) -> int:
        return self.tests_passed + self.tests_failed

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.total_tests if self.total_tests else 0.0


class GraphBlackboard(BaseModel):
    """Shared context flowing through the entire graph execution.

    Every node reads from the blackboard when building its prompt.
    SCOUT writes scout_context; the sandbox runner writes tool_evaluation.
    The hyperagent writes node_annotations to give specific nodes focused context
    before they run (e.g. "match the auth pattern in src/security/middleware.py").

    The blackboard is the mechanism that turns isolated agents into a coordinated
    team: all members share the same view of the objective, the workspace, and
    what has been learned in prior iterations.
    """

    task_objective: str
    workspace: str
    iteration: int = 0  # which optimization iteration (0 = first run)
    scout_context: ScoutContext | None = None
    tool_evaluation: ToolEvaluation | None = None
    node_annotations: dict[str, str] = Field(default_factory=dict)  # AgentRole.value → note
    optimization_history: list[Any] = Field(default_factory=list)  # list[OptimizationSignal]
    metadata: dict[str, Any] = Field(default_factory=dict)  # extensible catch-all


class ScoutOutput(BaseModel):
    """Structured output from the SCOUT node."""

    relevant_files: list[str]
    patterns: str
    dependency_map: dict[str, list[str]] = Field(default_factory=dict)
    similar_implementations: list[str] = Field(default_factory=list)
    summary: str  # one-paragraph briefing for other nodes


class ConductorRoutingOutput(BaseModel):
    """Output from an LLM-based CONDUCTOR routing call.

    When use_llm_routing=True on GraphConfig, the CONDUCTOR makes a real LLM
    call instead of evaluating condition strings.  It receives the full
    blackboard and all current node outputs and returns a routing decision
    with explicit reasoning.
    """

    next_node: AgentRole | None
    reasoning: str
    blackboard_update: dict[str, str] = Field(default_factory=dict)  # node_annotations to set


class NodeConfig(BaseModel):
    """Per-node tunable configuration — prompts become parameters the optimizer can update.

    `system_prompt=None` means use the role's default from agents/prompts.py.
    The optimizer writes improved prompts here after analysing execution traces.
    """

    role: AgentRole
    system_prompt: str | None = None  # None = use role default
    temperature: float | None = None  # None = use tier default


class GraphConfig(BaseModel):
    """Topology of a hyperagent graph execution.

    Defines which sub-agent nodes participate, how they are connected, where
    execution starts, which node acts as the hyperagent orchestrator, and a
    cycle cap to prevent runaway loops.

    `node_configs` holds per-node tunable parameters (primarily system_prompt).
    The GraphOptimizer writes improved prompts here after analysing traces.
    """

    nodes: list[AgentRole]
    edges: list[GraphEdge] = Field(default_factory=list)
    entry: AgentRole = AgentRole.PLANNER
    hyperagent: AgentRole = AgentRole.CONDUCTOR
    max_cycles: int = Field(default=5, ge=1, le=20)
    node_configs: dict[AgentRole, NodeConfig] = Field(default_factory=dict)
    use_llm_routing: bool = False  # True = CONDUCTOR makes LLM routing calls
    run_scout: bool = False  # True = SCOUT runs before entry node to populate blackboard


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
    blackboard: GraphBlackboard | None = None  # final state of the shared context


# ---------------------------------------------------------------------------
# Optimizer signal models
# ---------------------------------------------------------------------------


class NodePerformanceMetrics(BaseModel):
    """Per-node performance summary extracted from a set of execution traces.

    `bottleneck_score` is a composite signal (0-1) indicating how much this
    node limits overall pipeline quality.  Higher = higher optimization priority.
    """

    role: AgentRole
    run_count: int
    success_rate: float = Field(ge=0, le=1)
    avg_tokens: float
    avg_review_score: float | None = None  # only set when the role is REVIEWER
    bottleneck_score: float = Field(ge=0, le=1)


class OptimizationSignal(BaseModel):
    """Gradient signal derived from a batch of HyperagentOutput traces.

    `weakest_node` is the role with the highest bottleneck_score — the one the
    optimizer should target first.  `avg_review_score` is the pipeline-wide
    quality baseline the optimization is trying to improve.
    """

    node_metrics: list[NodePerformanceMetrics]
    weakest_node: AgentRole
    total_runs: int
    avg_review_score: float | None = None
