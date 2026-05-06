"""Hyperagent graph execution engine — beam search + fan-out parallel dispatch.

Execution model
───────────────
Each "cycle" has a set of *active* nodes.  All active nodes are dispatched
concurrently via asyncio.gather (fan-out).  For each node:

  • If tier_config.parallel_generations > 1 (ULTRA tier), N independent
    completions are requested in parallel (beam search), scored by a per-role
    heuristic, and the highest-scoring candidate is selected.
  • If parallel_generations == 1, a single completion is requested.

After all active nodes complete, accumulated state (plan / code / review) is
updated, then outgoing edges are evaluated against the new state to produce the
next active set.

Edge routing
────────────
Sequential edges (parallel=False, default): at most one fires per source node —
  the first matching condition wins.
Parallel edges (parallel=True): all matching ones fire concurrently.
Both types can co-exist on the same source node.
A terminal edge (to_role=None) stops traversal from that node.
"""

from __future__ import annotations

import asyncio
import functools
import json
import os
import random

import httpx
import structlog
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from maistro.agents.circuit_breaker import CircuitOpenError, llm_circuit
from maistro.agents.prompts import CODER_SYSTEM, PLANNER_SYSTEM, REVIEWER_SYSTEM
from maistro.agents.types import (
    AgentRole,
    CodeOutput,
    GraphBlackboard,
    GraphConfig,
    GraphNodeResult,
    HyperagentOutput,
    LLMProviderError,
    PlanOutput,
    ReviewOutput,
)
from maistro.config.model_resolver import resolve_model
from maistro.config.models import DEFAULT_TIERS, Tier, TierConfig
from maistro.config.settings import get_settings
from maistro.constants import DESCRIPTION_LOG_PREVIEW_LEN
from maistro.observability.metrics import llm_errors_total, llm_requests_total, llm_tokens_used
from maistro.tasks.models import TaskCreate

logger = structlog.get_logger()

_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

# Sentinel — distinguishes "field value is None" from "unresolvable path"
_MISSING = object()

# Type alias for any typed node output
_NodeOutput = PlanOutput | CodeOutput | ReviewOutput

# ---------------------------------------------------------------------------
# JSON-mode fallback schemas (Ollama models without structured-output support)
# ---------------------------------------------------------------------------

_PLANNER_JSON_SCHEMA = """

You MUST respond with valid JSON matching this exact schema (no markdown, no extra text):
{
  "summary": "string — brief plan summary",
  "subtasks": [
    {"title": "string", "description": "string", "file_paths": []}
  ],
  "estimated_files": []
}
"""

_CODER_JSON_SCHEMA = """

You MUST respond with valid JSON matching this exact schema (no markdown, no extra text):
{
  "files_changed": ["string"],
  "description": "string — what was implemented",
  "tests_added": false
}
"""

_REVIEWER_JSON_SCHEMA = """

You MUST respond with valid JSON matching this exact schema (no markdown, no extra text):
{
  "approved": true,
  "score": 8.0,
  "issues": [],
  "suggestions": []
}
"""

_JSON_SCHEMAS: dict[AgentRole, str] = {
    AgentRole.PLANNER: _PLANNER_JSON_SCHEMA,
    AgentRole.CODER: _CODER_JSON_SCHEMA,
    AgentRole.REVIEWER: _REVIEWER_JSON_SCHEMA,
}

_OUTPUT_TYPES: dict[AgentRole, type] = {
    AgentRole.PLANNER: PlanOutput,
    AgentRole.CODER: CodeOutput,
    AgentRole.REVIEWER: ReviewOutput,
}

_SYSTEM_PROMPTS: dict[AgentRole, str] = {
    AgentRole.PLANNER: PLANNER_SYSTEM,
    AgentRole.CODER: CODER_SYSTEM,
    AgentRole.REVIEWER: REVIEWER_SYSTEM,
}

# ---------------------------------------------------------------------------
# Sub-agent builders (cached per role + model + base_url + json_mode)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=64)
def _build_node_agent(
    role: AgentRole,
    model: str,
    base_url: str | None,
    use_json_mode: bool,
    system_prompt_override: str | None = None,
) -> Agent:
    """Build and cache a pydantic-ai sub-agent for the given role.

    `system_prompt_override` is set by the GraphOptimizer when it has produced
    an improved prompt for this node; None falls back to the role default.
    """
    system_prompt = system_prompt_override or _SYSTEM_PROMPTS.get(role, PLANNER_SYSTEM)
    output_type: type = _OUTPUT_TYPES.get(role, PlanOutput)

    litellm_key = os.environ.get("LITELLM_MASTER_KEY", "")
    api_key = litellm_key if litellm_key else "ollama"

    if use_json_mode:
        system_prompt = system_prompt + _JSON_SCHEMAS.get(role, "")
        output_type = str

    if base_url:
        model_name = model.removeprefix("openai:")
        provider = OpenAIProvider(base_url=base_url, api_key=api_key)
        openai_model = OpenAIChatModel(model_name, provider=provider)
        return Agent(
            model=openai_model,
            system_prompt=system_prompt,
            output_type=output_type,
            retries=2,
            model_settings={"extra_body": {"response_format": {"type": "json_object"}}}
            if use_json_mode
            else None,
        )

    return Agent(model=model, system_prompt=system_prompt, output_type=output_type, retries=2)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _constraints_text(constraints: list[str]) -> str:
    return "\n".join(f"- {c}" for c in constraints) if constraints else "None"


def _planner_prompt(task: TaskCreate) -> str:
    return (
        f"Task: {task.description}\n\n"
        f"Workspace: {task.workspace}\n"
        f"Constraints:\n{_constraints_text(task.constraints)}"
    )


def _coder_prompt(task: TaskCreate, plan: PlanOutput) -> str:
    subtasks = "\n".join(
        f"{i + 1}. {s.title}: {s.description}" for i, s in enumerate(plan.subtasks)
    )
    return (
        f"Task: {task.description}\n\n"
        f"Workspace: {task.workspace}\n\n"
        f"Plan: {plan.summary}\n\n"
        f"Subtasks:\n{subtasks}"
    )


def _reviewer_prompt(task: TaskCreate, plan: PlanOutput | None, code: CodeOutput) -> str:
    plan_summary = plan.summary if plan else "N/A"
    files = ", ".join(code.files_changed) or "none"
    return (
        f"Task: {task.description}\n\n"
        f"Plan summary: {plan_summary}\n"
        f"Files changed: {files}\n"
        f"Description: {code.description}\n"
        f"Tests added: {code.tests_added}"
    )


def _blackboard_prefix(role: AgentRole, blackboard: GraphBlackboard | None) -> str:
    """Build the shared-context preamble prepended to every node prompt."""
    if blackboard is None:
        return ""
    lines: list[str] = [f"## Pipeline Objective\n{blackboard.task_objective}\n"]

    if blackboard.scout_context:
        sc = blackboard.scout_context
        if sc.relevant_files:
            lines.append("## Workspace Briefing (from SCOUT)")
            lines.append(f"Relevant files: {', '.join(sc.relevant_files[:10])}")
        if sc.patterns:
            lines.append(f"Patterns to follow: {sc.patterns}")
        if sc.similar_implementations:
            lines.append(
                f"Similar existing implementations: "
                f"{', '.join(sc.similar_implementations[:5])}"
            )
        if sc.raw_findings:
            lines.append(f"Scout summary: {sc.raw_findings}")
        lines.append("")

    if blackboard.tool_evaluation and role == AgentRole.REVIEWER:
        te = blackboard.tool_evaluation
        lines.append(
            f"## Sandbox Results\n"
            f"Tests: {te.tests_passed} passed / {te.tests_failed} failed "
            f"(pass rate {te.pass_rate:.0%})\n"
            f"Lint errors: {len(te.lint_errors)}, Type errors: {len(te.type_errors)}\n"
            f"{te.test_output[:400]}\n"
        )

    annotation = blackboard.node_annotations.get(role.value)
    if annotation:
        lines.append(f"## Hyperagent Note for {role.upper()}\n{annotation}\n")

    if blackboard.iteration > 0:
        lines.append(f"## Optimization Context\nIteration {blackboard.iteration}.")

    return "\n".join(lines) + "\n---\n" if len(lines) > 1 else ""


def _build_node_prompt(
    task: TaskCreate,
    role: AgentRole,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,  # reserved for reviewer-retry context
    blackboard: GraphBlackboard | None = None,
) -> str:
    prefix = _blackboard_prefix(role, blackboard)

    if role == AgentRole.PLANNER:
        return prefix + _planner_prompt(task)
    if role == AgentRole.CODER:
        return prefix + (_coder_prompt(task, plan) if plan else _planner_prompt(task))
    if role == AgentRole.REVIEWER:
        if code is None:
            return prefix + f"Task: {task.description}\n\nNo code output available to review."
        return prefix + _reviewer_prompt(task, plan, code)
    return prefix + f"Task: {task.description}\nWorkspace: {task.workspace}"


# ---------------------------------------------------------------------------
# Candidate scoring — heuristic used for beam selection
# ---------------------------------------------------------------------------


def _score_output(role: AgentRole, output: _NodeOutput) -> float:
    """Return a scalar quality score for a beam candidate.

    Higher is better.  These are rough heuristics — the goal is to prefer
    richer, more complete outputs when multiple beams succeed.
    """
    if isinstance(output, ReviewOutput):
        return output.score
    if isinstance(output, PlanOutput):
        return float(len(output.subtasks))
    if isinstance(output, CodeOutput):
        return float(len(output.files_changed)) + (2.0 if output.tests_added else 0.0)
    return 0.0


# ---------------------------------------------------------------------------
# Condition evaluator
# ---------------------------------------------------------------------------

_OPERATORS = [" is not ", " is ", " >= ", " <= ", " != ", " == ", " > ", " < "]


def _resolve_path(
    path: str,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
) -> object:
    parts = path.split(".", 1)
    if len(parts) != 2:
        return _MISSING
    namespace, field = parts
    obj: object = {"plan": plan, "code": code, "review": review}.get(namespace)
    if obj is None:
        return _MISSING
    return getattr(obj, field, _MISSING)


def _parse_rhs(s: str) -> object:
    if s == "True":
        return True
    if s == "False":
        return False
    if s == "None":
        return None
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s.strip("\"'")


def _compare(lhs: object, op: str, rhs: object) -> bool:
    stripped = op.strip()
    if stripped in ("is", "=="):
        return lhs == rhs
    if stripped in ("is not", "!="):
        return lhs != rhs
    try:
        if stripped == "<":
            return lhs < rhs  # type: ignore[operator]
        if stripped == ">":
            return lhs > rhs  # type: ignore[operator]
        if stripped == "<=":
            return lhs <= rhs  # type: ignore[operator]
        if stripped == ">=":
            return lhs >= rhs  # type: ignore[operator]
    except TypeError:
        return False
    return False


def evaluate_condition(
    condition: str,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
) -> bool:
    """Safely evaluate a dotted-path condition string against node outputs.

    Supported: ``review.approved is False``, ``review.score < 7.0``,
    ``code.tests_added == True``.  Returns False if the path is unresolvable
    or the condition is malformed — the edge is skipped, not crashed.
    """
    for op in _OPERATORS:
        if op in condition:
            lhs_str, rhs_str = condition.split(op, 1)
            lhs = _resolve_path(lhs_str.strip(), plan, code, review)
            if lhs is _MISSING:
                return False
            return _compare(lhs, op, _parse_rhs(rhs_str.strip()))
    return False


# ---------------------------------------------------------------------------
# Edge routing
# ---------------------------------------------------------------------------


def _next_nodes(
    config: GraphConfig,
    current: AgentRole,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
) -> list[AgentRole]:
    """Return the next nodes to activate after `current` completes.

    Sequential edges (parallel=False): first matching condition wins — at most
    one sequential next node is returned.
    Parallel edges (parallel=True): all matching ones are returned.
    Both can co-exist; the sequential winner is prepended to parallel matches.
    Terminal edges (to_role=None) stop traversal from this node.
    """
    sequential: AgentRole | None = None
    parallel: list[AgentRole] = []

    for edge in config.edges:
        if edge.from_role != current:
            continue
        if edge.to_role is None:
            continue  # terminal edge — contributes no next node
        cond_met = edge.condition is None or evaluate_condition(
            edge.condition, plan, code, review
        )
        if not cond_met:
            continue
        if edge.parallel:
            parallel.append(edge.to_role)
        elif sequential is None:
            sequential = edge.to_role

    result = [] if sequential is None else [sequential]
    result.extend(parallel)
    return result


# ---------------------------------------------------------------------------
# Node dispatch — single call
# ---------------------------------------------------------------------------


def _get_tier_config(tier: int | None) -> TierConfig:
    t = Tier(tier) if tier and tier in [e.value for e in Tier] else Tier.STANDARD
    return DEFAULT_TIERS[t]


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return False


def _parse_node_json(role: AgentRole, raw: str) -> _NodeOutput:
    data = json.loads(raw)
    return _OUTPUT_TYPES.get(role, PlanOutput).model_validate(data)  # type: ignore[return-value]


async def _dispatch_node_single(
    role: AgentRole,
    prompt: str,
    tier_config: TierConfig,
    resolved_model: str,
    base_url: str | None,
    use_json_mode: bool,
    system_prompt_override: str | None = None,
) -> tuple[_NodeOutput, int]:
    """Single completion for one node; returns (typed_output, tokens_used)."""
    if not llm_circuit.allow_request():
        raise CircuitOpenError(llm_circuit)

    agent = _build_node_agent(role, resolved_model, base_url, use_json_mode, system_prompt_override)
    last_exc: Exception | None = None

    for attempt in range(tier_config.max_llm_retries):
        try:
            llm_requests_total.inc()
            result = await asyncio.wait_for(agent.run(prompt), timeout=tier_config.timeout)
            llm_circuit.record_success()

            tokens = 0
            try:
                usage = result.usage()
                tokens = usage.total_tokens or 0
                if tokens:
                    llm_tokens_used.observe(float(tokens), tier=str(tier_config.tier.value))
            except Exception:
                pass

            typed: _NodeOutput = (
                _parse_node_json(role, result.output)
                if use_json_mode
                else result.output  # type: ignore[assignment]
            )
            return typed, tokens

        except Exception as exc:
            if _is_retryable(exc):
                last_exc = exc
                llm_circuit.record_failure()
                llm_errors_total.inc(error_type="retryable")
                await logger.awarning(
                    "graph_node_transient_error",
                    role=role,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < tier_config.max_llm_retries - 1:
                    delay = tier_config.initial_backoff * (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
            else:
                llm_circuit.record_failure()
                llm_errors_total.inc(error_type="non_retryable")
                raise

    raise LLMProviderError(
        f"Node {role} failed after {tier_config.max_llm_retries} retries: {last_exc}"
    )


# ---------------------------------------------------------------------------
# Node dispatch — beam search (N parallel completions, select best)
# ---------------------------------------------------------------------------


async def _dispatch_node_beam(
    role: AgentRole,
    prompt: str,
    tier_config: TierConfig,
    resolved_model: str,
    base_url: str | None,
    use_json_mode: bool,
    system_prompt_override: str | None = None,
) -> tuple[_NodeOutput, int, list[str], int]:
    """Run tier_config.parallel_generations completions concurrently.

    Returns (best_output, total_tokens, candidates_str, selected_index).
    candidates_str holds every successful generation's output (truncated).
    selected_index is the index of the chosen candidate within candidates_str.

    If parallel_generations==1, runs a single call with no overhead.
    """
    n = tier_config.parallel_generations

    if n == 1:
        output, tokens = await _dispatch_node_single(
            role, prompt, tier_config, resolved_model, base_url, use_json_mode,
            system_prompt_override,
        )
        return output, tokens, [str(output)[:500]], 0

    # Launch N completions concurrently
    raw = await asyncio.gather(
        *[
            _dispatch_node_single(
                role, prompt, tier_config, resolved_model, base_url, use_json_mode,
                system_prompt_override,
            )
            for _ in range(n)
        ],
        return_exceptions=True,
    )

    successes: list[tuple[_NodeOutput, int]] = [
        item  # type: ignore[misc]
        for item in raw
        if not isinstance(item, BaseException)
    ]

    if not successes:
        # All beams failed — re-raise the first exception
        for item in raw:
            if isinstance(item, BaseException):
                raise item

    # Score candidates; highest wins
    scored = sorted(
        range(len(successes)),
        key=lambda i: _score_output(role, successes[i][0]),
        reverse=True,
    )
    best_idx = scored[0]
    best_output, _ = successes[best_idx]
    total_tokens = sum(t for _, t in successes)
    candidates_str = [str(o)[:500] for o, _ in successes]

    await logger.ainfo(
        "graph_beam_selected",
        role=role,
        n_beams=n,
        n_succeeded=len(successes),
        selected=best_idx,
        score=_score_output(role, best_output),
    )

    return best_output, total_tokens, candidates_str, best_idx


# ---------------------------------------------------------------------------
# Graph executor — public entry point
# ---------------------------------------------------------------------------


async def run_graph_task(task: TaskCreate) -> HyperagentOutput:
    """Execute a task as a hyperagent graph with beam search and fan-out.

    Each cycle dispatches all currently-active nodes concurrently.  Per-node
    beam search fires parallel_generations completions and selects the best.
    Edge conditions are evaluated against accumulated state after all nodes in
    a cycle complete, so conditions can reference outputs from sibling nodes.
    """
    config = task.graph_config
    assert config is not None, "graph_config required for GRAPH mode"  # noqa: S101

    tier_config = _get_tier_config(task.tier)
    resolved_model, base_url, use_json_mode = resolve_model(tier_config.model)

    await logger.ainfo(
        "graph_start",
        hyperagent=config.hyperagent,
        nodes=config.nodes,
        entry=config.entry,
        max_cycles=config.max_cycles,
        parallel_generations=tier_config.parallel_generations,
        run_scout=config.run_scout,
        use_llm_routing=config.use_llm_routing,
        model=resolved_model,
        description=task.description[:DESCRIPTION_LOG_PREVIEW_LEN],
    )

    # Initialise the shared blackboard
    blackboard = GraphBlackboard(
        task_objective=task.description,
        workspace=task.workspace,
    )

    # SCOUT pre-pass — populate blackboard before the main graph loop
    if config.run_scout:
        from maistro.agents.scout import run_scout

        blackboard = await run_scout(task, blackboard, tier_config)

    node_results: list[GraphNodeResult] = []
    plan: PlanOutput | None = None
    code: CodeOutput | None = None
    review: ReviewOutput | None = None

    active: list[AgentRole] = [config.entry]
    cycle = 0

    while active and cycle < config.max_cycles:
        await logger.ainfo(
            "graph_cycle_start", cycle=cycle, active_nodes=active,
            parallel_generations=tier_config.parallel_generations,
        )

        # --- Dispatch all active nodes concurrently (fan-out + beam) ----------
        # Resolve any optimizer-improved prompts before entering the gather
        prompt_overrides = {
            role: config.node_configs[role].system_prompt
            for role in active
            if role in config.node_configs and config.node_configs[role].system_prompt
        }
        batch = await asyncio.gather(
            *[
                _dispatch_node_beam(
                    role,
                    _build_node_prompt(task, role, plan, code, review, blackboard),
                    tier_config,
                    resolved_model,
                    base_url,
                    use_json_mode,
                    prompt_overrides.get(role),
                )
                for role in active
            ],
            return_exceptions=True,
        )

        parallel_group = cycle if len(active) > 1 else None

        # --- Pass A: update accumulated state for all successful results ------
        for role, result in zip(active, batch):
            if isinstance(result, BaseException):
                continue
            typed_output, _tokens, _candidates, _selected = result
            if role == AgentRole.PLANNER and isinstance(typed_output, PlanOutput):
                plan = typed_output
            elif role == AgentRole.CODER and isinstance(typed_output, CodeOutput):
                code = typed_output
            elif role == AgentRole.REVIEWER and isinstance(typed_output, ReviewOutput):
                review = typed_output

        # --- Pass B: routing + record node results (uses fully-updated state) -
        seen_next: set[AgentRole] = set()
        next_active: list[AgentRole] = []

        for role, result in zip(active, batch):
            node_success = not isinstance(result, BaseException)

            if node_success:
                typed_output, total_tokens, candidates, selected = result  # type: ignore[misc]
                role_next = _next_nodes(config, role, plan, code, review)
                for nxt in role_next:
                    if nxt not in seen_next:
                        next_active.append(nxt)
                        seen_next.add(nxt)
            else:
                total_tokens, candidates, selected, role_next = 0, [], 0, []
                await logger.aerror(
                    "graph_node_failed", role=role, cycle=cycle, error=str(result)
                )

            node_results.append(
                GraphNodeResult(
                    role=role,
                    success=node_success,
                    output=candidates[selected] if candidates else f"error: {result}",
                    tokens_used=total_tokens,
                    next_nodes=role_next,
                    candidates=candidates,
                    selected_candidate=selected,
                    parallel_group=parallel_group,
                )
            )

        active = next_active
        cycle += 1

    # --- Build final output ---------------------------------------------------
    success = bool(node_results) and all(r.success for r in node_results)

    if review and review.approved:
        final_answer = f"Task completed. Review score: {review.score}/10."
    elif review and not review.approved:
        issues = "; ".join(review.issues[:2]) if review.issues else "unspecified issues"
        final_answer = f"Review not approved (score: {review.score}/10): {issues}"
    elif plan:
        final_answer = plan.summary
    else:
        final_answer = ""

    result = HyperagentOutput(
        plan=plan,
        code=code,
        review=review,
        final_answer=final_answer,
        success=success,
        graph_config=config,
        node_results=node_results,
        total_cycles=cycle,
        blackboard=blackboard,
    )

    await logger.ainfo(
        "graph_complete",
        success=success,
        total_cycles=cycle,
        nodes_run=[r.role for r in node_results],
        parallel_generations=tier_config.parallel_generations,
        review_approved=review.approved if review else None,
        review_score=review.score if review else None,
    )

    return result
