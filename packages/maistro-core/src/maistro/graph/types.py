from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class LLMProviderError(Exception):
    pass


class AgentRole(StrEnum):
    CONDUCTOR = "conductor"
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    SCOUT = "scout"


class ExecutionMode(StrEnum):
    TASK = "task"
    WORKFLOW = "workflow"
    AGENT = "agent"
    GRAPH = "graph"


class GraphEdge(BaseModel):
    from_role: AgentRole
    to_role: AgentRole | None
    condition: str | None = None
    parallel: bool = False


class ScoutContext(BaseModel):
    relevant_files: list[str] = Field(default_factory=list)
    patterns: str = ""
    dependency_map: dict[str, list[str]] = Field(default_factory=dict)
    similar_implementations: list[str] = Field(default_factory=list)
    raw_findings: str = ""


class ToolEvaluation(BaseModel):
    tests_passed: int = 0
    tests_failed: int = 0
    test_output: str = ""
    lint_errors: list[str] = Field(default_factory=list)
    type_errors: list[str] = Field(default_factory=list)
    evaluation_score: float = Field(default=0.0, ge=0, le=10)

    @property
    def total_tests(self) -> int:
        return self.tests_passed + self.tests_failed

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.total_tests if self.total_tests else 0.0


class GraphBlackboard(BaseModel):
    task_objective: str
    workspace: str
    iteration: int = 0
    scout_context: ScoutContext | None = None
    tool_evaluation: ToolEvaluation | None = None
    node_annotations: dict[str, str] = Field(default_factory=dict)
    optimization_history: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoutOutput(BaseModel):
    relevant_files: list[str]
    patterns: str
    dependency_map: dict[str, list[str]] = Field(default_factory=dict)
    similar_implementations: list[str] = Field(default_factory=list)
    summary: str


class ConductorRoutingOutput(BaseModel):
    next_node: AgentRole | None
    reasoning: str
    blackboard_update: dict[str, str] = Field(default_factory=dict)


class NodeConfig(BaseModel):
    role: AgentRole
    system_prompt: str | None = None
    temperature: float | None = None
    beam_width: int = 1


class GraphConfig(BaseModel):
    nodes: list[AgentRole]
    edges: list[GraphEdge] = Field(default_factory=list)
    entry: AgentRole = AgentRole.PLANNER
    hyperagent: AgentRole = AgentRole.CONDUCTOR
    max_cycles: int = Field(default=5, ge=1, le=20)
    node_configs: dict[AgentRole, NodeConfig] = Field(default_factory=dict)
    use_llm_routing: bool = False
    run_scout: bool = False


class GraphNodeResult(BaseModel):
    role: AgentRole
    success: bool
    output: str
    tokens_used: int = 0
    next_nodes: list[AgentRole] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)
    selected_candidate: int = 0
    parallel_group: int | None = None


class SubTask(BaseModel):
    title: str
    description: str
    file_paths: list[str] = Field(default_factory=list)


class PlanOutput(BaseModel):
    summary: str
    subtasks: list[SubTask] = Field(default_factory=list)
    estimated_files: list[str] = Field(default_factory=list)


class CodeOutput(BaseModel):
    files_changed: list[str] = Field(default_factory=list)
    description: str = ""
    tests_added: bool = False


class ReviewOutput(BaseModel):
    approved: bool
    score: float = Field(default=0.0, ge=0, le=10)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ConductorOutput(BaseModel):
    plan: PlanOutput | None = None
    code: CodeOutput | None = None
    review: ReviewOutput | None = None
    final_answer: str = ""
    success: bool = True


class HyperagentOutput(ConductorOutput):
    graph_config: GraphConfig | None = None
    node_results: list[GraphNodeResult] = Field(default_factory=list)
    total_cycles: int = 0
    blackboard: GraphBlackboard | None = None


class NodePerformanceMetrics(BaseModel):
    role: AgentRole
    run_count: int
    success_rate: float = Field(ge=0, le=1)
    avg_tokens: float
    avg_review_score: float | None = None
    bottleneck_score: float = Field(ge=0, le=1)


class OptimizationSignal(BaseModel):
    node_metrics: list[NodePerformanceMetrics]
    weakest_node: AgentRole
    total_runs: int
    avg_review_score: float | None = None


class GraphTask(BaseModel):
    description: str
    workspace: str = ""
    constraints: list[str] = Field(default_factory=list)
    graph_config: GraphConfig | None = None


DEFAULT_SYSTEM_PROMPTS: dict[AgentRole, str] = {
    AgentRole.PLANNER: (
        "You are an expert software planner. Analyze the task and workspace, "
        "then produce a clear, actionable plan with specific subtasks and file paths."
    ),
    AgentRole.CODER: (
        "You are an expert software developer. Implement the plan by writing "
        "correct, well-structured code. Follow existing patterns in the workspace."
    ),
    AgentRole.REVIEWER: (
        "You are a senior code reviewer. Evaluate the implementation for "
        "correctness, quality, security, and completeness. Be thorough but fair."
    ),
    AgentRole.SCOUT: (
        "You are a workspace analyst. Survey the codebase to identify relevant "
        "files, patterns, conventions, and similar implementations."
    ),
    AgentRole.CONDUCTOR: (
        "You are the pipeline conductor. Route tasks to the appropriate next "
        "node based on the current state of the pipeline."
    ),
}

JSON_OUTPUT_SCHEMAS: dict[AgentRole, str] = {
    AgentRole.PLANNER: (
        '\nYou MUST respond with valid JSON matching this schema (no markdown, no extra text):\n'
        '{"summary": "string", "subtasks": [{"title": "string", "description": "string", '
        '"file_paths": []}], "estimated_files": []}'
    ),
    AgentRole.CODER: (
        '\nYou MUST respond with valid JSON matching this schema (no markdown, no extra text):\n'
        '{"files_changed": ["string"], "description": "string", "tests_added": false}'
    ),
    AgentRole.REVIEWER: (
        '\nYou MUST respond with valid JSON matching this schema (no markdown, no extra text):\n'
        '{"approved": true, "score": 8.0, "issues": [], "suggestions": []}'
    ),
    AgentRole.SCOUT: (
        '\nYou MUST respond with valid JSON matching this schema (no markdown, no extra text):\n'
        '{"relevant_files": ["string"], "patterns": "string", '
        '"dependency_map": {"file": ["import"]}, "similar_implementations": ["string"], '
        '"summary": "string"}'
    ),
}

OUTPUT_TYPES: dict[AgentRole, type[BaseModel]] = {
    AgentRole.PLANNER: PlanOutput,
    AgentRole.CODER: CodeOutput,
    AgentRole.REVIEWER: ReviewOutput,
    AgentRole.SCOUT: ScoutOutput,
}
