"""Graph optimizer — gradient-signal extraction and prompt optimization.

Treats node system prompts as tunable parameters.  After one or more graph
executions, the optimizer:

  1. Extracts a per-node performance signal from execution traces
     (success rate, token cost, review score contribution).
  2. Computes a bottleneck_score per node — the composite "gradient" indicating
     which node most limits overall pipeline quality.
  3. Calls an LLM with a meta-prompt to rewrite the weakest node's system prompt
     so it acts as a coordinated team member (aware of pipeline objective,
     upstream inputs, downstream expectations, and recent failure patterns)
     rather than an isolated agent.
  4. Returns an updated GraphConfig with the improved NodeConfig.

The caller is responsible for persisting traces and iterating — this module
only does one optimization step per call.

Typical usage:

    optimizer = GraphOptimizer(
        task_description="Add rate limiting to /tasks",
        model=resolved_model,
        base_url=base_url,
    )
    signal = optimizer.extract_signal(traces)
    new_config = await optimizer.optimize(config, traces)
    # use new_config for the next run
"""

from __future__ import annotations

import functools
import os
from collections import defaultdict

import structlog
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from maistro.agents.types import (
    AgentRole,
    GraphConfig,
    HyperagentOutput,
    NodeConfig,
    NodePerformanceMetrics,
    OptimizationSignal,
    ReviewOutput,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Role metadata — used by the meta-prompt to give each node pipeline context
# ---------------------------------------------------------------------------

_ROLE_UPSTREAM = {
    AgentRole.PLANNER: "A task description, workspace path, and optional constraints.",
    AgentRole.CODER: "A PlanOutput: summary string and a list of subtasks each with title, description, and file_paths.",
    AgentRole.REVIEWER: "A CodeOutput: list of files_changed, implementation description, tests_added flag.",
    AgentRole.SCOUT: "A task description and workspace path.",
    AgentRole.CONDUCTOR: "Outputs from all completed sub-agent nodes.",
}

_ROLE_OUTPUT_SPEC = {
    AgentRole.PLANNER: (
        "PlanOutput — summary: str, subtasks: list[{title, description, file_paths}], "
        "estimated_files: list[str]"
    ),
    AgentRole.CODER: "CodeOutput — files_changed: list[str], description: str, tests_added: bool",
    AgentRole.REVIEWER: (
        "ReviewOutput — approved: bool, score: float (0–10), "
        "issues: list[str], suggestions: list[str]"
    ),
    AgentRole.SCOUT: "SearchOutput — findings: str, relevant_files: list[str]",
    AgentRole.CONDUCTOR: "Routing decision: which node to activate next.",
}

_ROLE_DOWNSTREAM = {
    AgentRole.PLANNER: (
        "CODER — needs specific, actionable subtasks with file paths so it can "
        "implement without ambiguity."
    ),
    AgentRole.CODER: (
        "REVIEWER — evaluates correctness, quality, security, and completeness. "
        "It needs to know what changed and why."
    ),
    AgentRole.REVIEWER: (
        "CONDUCTOR (routing) — uses approved/score to decide whether to accept or "
        "send back to CODER for revision."
    ),
    AgentRole.SCOUT: "PLANNER or CODER — provides research context to inform planning or implementation.",
    AgentRole.CONDUCTOR: "All nodes — routing decisions determine which node runs next.",
}


# ---------------------------------------------------------------------------
# Optimizer agent builder
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=4)
def _build_optimizer_agent(model: str, base_url: str | None) -> Agent:
    """Build the LLM agent used to propose improved node prompts."""
    system = (
        "You are an expert prompt engineer specializing in multi-agent AI pipelines. "
        "You rewrite system prompts to maximize coordinated performance across a team "
        "of specialized agents, treating each agent's prompt as a learnable parameter."
    )
    litellm_key = os.environ.get("LITELLM_MASTER_KEY", "")
    api_key = litellm_key if litellm_key else "ollama"

    if base_url:
        model_name = model.removeprefix("openai:")
        provider = OpenAIProvider(base_url=base_url, api_key=api_key)
        openai_model = OpenAIChatModel(model_name, provider=provider)
        return Agent(model=openai_model, system_prompt=system, output_type=str, retries=2)

    return Agent(model=model, system_prompt=system, output_type=str, retries=2)


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------


def _compute_bottleneck_score(
    success_rate: float,
    avg_review_score: float | None,
    avg_tokens: float,
    max_avg_tokens: float,
) -> float:
    """Composite bottleneck score in [0, 1].

    Weights:
      50%  failure contribution  (1 - success_rate)
      40%  quality gap           (lower review score = worse)
      10%  token waste           (expensive failures amplify the signal)
    """
    failure = 1.0 - success_rate
    quality_gap = (10.0 - avg_review_score) / 10.0 if avg_review_score is not None else 0.5
    token_waste = (avg_tokens / max(max_avg_tokens, 1.0)) * failure
    return min(1.0, 0.5 * failure + 0.4 * quality_gap + 0.1 * token_waste)


def _describe_pipeline(config: GraphConfig) -> str:
    """Human-readable pipeline description derived from graph edges."""
    if not config.edges:
        return " → ".join(config.nodes)
    parts = []
    for edge in config.edges:
        arrow = "⇉" if edge.parallel else "→"
        cond = f" [{edge.condition}]" if edge.condition else ""
        to = edge.to_role or "END"
        parts.append(f"{edge.from_role} {arrow} {to}{cond}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# GraphOptimizer
# ---------------------------------------------------------------------------


class GraphOptimizer:
    """Extracts gradient signal from execution traces and proposes prompt improvements.

    Instantiate once per optimization session (task + model config).  Call
    extract_signal() to inspect the current performance, then optimize() to get
    an improved GraphConfig.
    """

    def __init__(self, task_description: str, model: str, base_url: str | None = None) -> None:
        self.task_description = task_description
        self.model = model
        self.base_url = base_url

    # --- Public API ----------------------------------------------------------

    def extract_signal(self, traces: list[HyperagentOutput]) -> OptimizationSignal:
        """Aggregate per-node performance metrics from execution traces.

        Returns an OptimizationSignal identifying the weakest node (highest
        bottleneck_score) and the pipeline-wide quality baseline.
        """
        if not traces:
            raise ValueError("At least one trace is required to extract signal.")

        # Collect per-role stats across all traces
        run_counts: dict[AgentRole, int] = defaultdict(int)
        success_counts: dict[AgentRole, int] = defaultdict(int)
        token_sums: dict[AgentRole, float] = defaultdict(float)
        review_scores: list[float] = []

        for trace in traces:
            if trace.review and isinstance(trace.review, ReviewOutput):
                review_scores.append(trace.review.score)
            for nr in trace.node_results:
                run_counts[nr.role] += 1
                if nr.success:
                    success_counts[nr.role] += 1
                token_sums[nr.role] += nr.tokens_used

        avg_tokens_per_role = {
            role: token_sums[role] / max(run_counts[role], 1)
            for role in run_counts
        }
        max_avg_tokens = max(avg_tokens_per_role.values(), default=1.0)

        pipeline_avg_review = (
            sum(review_scores) / len(review_scores) if review_scores else None
        )

        # Build per-role metrics
        metrics: list[NodePerformanceMetrics] = []
        for role in run_counts:
            success_rate = success_counts[role] / run_counts[role]
            avg_tokens = avg_tokens_per_role[role]
            avg_review = pipeline_avg_review if role == AgentRole.REVIEWER else None
            bottleneck = _compute_bottleneck_score(
                success_rate, avg_review, avg_tokens, max_avg_tokens
            )
            metrics.append(
                NodePerformanceMetrics(
                    role=role,
                    run_count=run_counts[role],
                    success_rate=success_rate,
                    avg_tokens=avg_tokens,
                    avg_review_score=avg_review,
                    bottleneck_score=bottleneck,
                )
            )

        metrics.sort(key=lambda m: m.bottleneck_score, reverse=True)
        weakest = metrics[0].role

        return OptimizationSignal(
            node_metrics=metrics,
            weakest_node=weakest,
            total_runs=len(traces),
            avg_review_score=pipeline_avg_review,
        )

    async def optimize(
        self,
        config: GraphConfig,
        traces: list[HyperagentOutput],
    ) -> GraphConfig:
        """Return an updated GraphConfig with an improved prompt for the weakest node.

        The optimizer identifies the highest-bottleneck node, collects failure
        examples from the traces, and asks the LLM to rewrite that node's system
        prompt with full pipeline context — objective, upstream inputs, downstream
        expectations, and observed failure patterns.
        """
        signal = self.extract_signal(traces)
        target_role = signal.weakest_node

        current_prompt = self._current_prompt(config, target_role)
        failure_examples = self._collect_failures(traces, target_role)

        await logger.ainfo(
            "optimizer_start",
            target_role=target_role,
            bottleneck_score=signal.node_metrics[0].bottleneck_score,
            total_runs=signal.total_runs,
            avg_review_score=signal.avg_review_score,
            n_failure_examples=len(failure_examples),
        )

        improved_prompt = await self._propose_prompt(
            config, signal, target_role, current_prompt, failure_examples
        )

        new_node_configs = dict(config.node_configs)
        new_node_configs[target_role] = NodeConfig(
            role=target_role, system_prompt=improved_prompt
        )

        await logger.ainfo(
            "optimizer_complete",
            target_role=target_role,
            prompt_length_before=len(current_prompt),
            prompt_length_after=len(improved_prompt),
        )

        return config.model_copy(update={"node_configs": new_node_configs})

    # --- Private helpers -----------------------------------------------------

    def _current_prompt(self, config: GraphConfig, role: AgentRole) -> str:
        """Return the active prompt for the given role (override or default)."""
        nc = config.node_configs.get(role)
        if nc and nc.system_prompt:
            return nc.system_prompt
        # Lazy import to avoid circular dependency
        from maistro.agents.graph import _SYSTEM_PROMPTS

        return _SYSTEM_PROMPTS.get(role, "")

    def _collect_failures(
        self, traces: list[HyperagentOutput], role: AgentRole
    ) -> list[str]:
        """Extract up to 5 short failure output snippets for the given role."""
        failures = []
        for trace in traces:
            for nr in trace.node_results:
                if nr.role == role and not nr.success and nr.output:
                    failures.append(nr.output[:300])
                    if len(failures) >= 5:
                        return failures
        return failures

    async def _propose_prompt(
        self,
        config: GraphConfig,
        signal: OptimizationSignal,
        role: AgentRole,
        current_prompt: str,
        failure_examples: list[str],
    ) -> str:
        """Ask the LLM to write an improved system prompt for the target role."""
        node_metric = next((m for m in signal.node_metrics if m.role == role), None)

        success_rate = node_metric.success_rate if node_metric else 1.0
        run_count = node_metric.run_count if node_metric else 0
        bottleneck = node_metric.bottleneck_score if node_metric else 0.0

        rank = next(
            (i + 1 for i, m in enumerate(signal.node_metrics) if m.role == role), 1
        )
        rank_suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank, "th")

        review_context = (
            f"- Pipeline average review score: {signal.avg_review_score:.1f}/10"
            if signal.avg_review_score is not None
            else ""
        )

        failures_text = (
            "\n\n".join(f"  [{i+1}] {f}" for i, f in enumerate(failure_examples))
            if failure_examples
            else "  No recorded failures — optimize for quality improvement."
        )

        other_roles = [r for r in config.nodes if r != role]
        other_nodes_text = ", ".join(other_roles) if other_roles else "none"

        meta_prompt = f"""\
## Pipeline Objective
{self.task_description}

## Pipeline Topology
{_describe_pipeline(config)}

## Node Being Optimized: [{role.upper()}]
Receives from upstream: {_ROLE_UPSTREAM.get(role, "task inputs")}
Must produce: {_ROLE_OUTPUT_SPEC.get(role, "structured output")}
Downstream consumer: {_ROLE_DOWNSTREAM.get(role, "next pipeline node")}
Other nodes in the pipeline: {other_nodes_text}

## Current System Prompt
```
{current_prompt}
```

## Performance Signal ({run_count} recent runs across {signal.total_runs} total)
- Success rate: {success_rate:.0%}
{review_context}
- Bottleneck score: {bottleneck:.2f}/1.0 ({rank}{rank_suffix} most impactful bottleneck)

## Observed Failure Patterns
{failures_text}

## Rewrite Instructions
Write an improved system prompt for the [{role.upper()}] node so it acts as a \
**coordinated team member** rather than an isolated agent.

The improved prompt MUST:
1. Open with the shared pipeline objective so the node aligns local decisions \
   with global goals
2. Explicitly state what input it receives (format + content)
3. State clearly what it must produce and in what format
4. Describe what the downstream node needs from its output
5. Address the specific failure patterns listed above with concrete guidance
6. Be actionable and specific — avoid generic instructions that apply to any LLM

Return ONLY the new system prompt text, nothing else.\
"""

        agent = _build_optimizer_agent(self.model, self.base_url)
        result = await agent.run(meta_prompt)
        return result.output.strip()
