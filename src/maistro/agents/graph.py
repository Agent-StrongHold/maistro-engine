"""Hyperagent graph execution engine — Phase 2 node-dispatch loop.

Executes GRAPH-mode tasks by iterating sub-agent nodes according to a
GraphConfig, routing between them based on edge conditions evaluated against
accumulated node outputs, and returning a HyperagentOutput that carries the
full per-node trace.

Control flow:
    1. Start at GraphConfig.entry node.
    2. Build a role-specific prompt from accumulated state.
    3. Dispatch to the sub-agent for that role; collect typed output.
    4. Evaluate outgoing edges — first matching condition wins.
    5. Repeat until no edge matches, a node fails, or max_cycles is reached.
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

# Sentinel — distinguishes "field value is None" from "path not resolvable"
_MISSING = object()

# ---------------------------------------------------------------------------
# JSON-mode fallback schemas (for Ollama models without structured-output support)
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


@functools.lru_cache(maxsize=32)
def _build_node_agent(
    role: AgentRole,
    model: str,
    base_url: str | None,
    use_json_mode: bool,
) -> Agent:
    """Build and cache a pydantic-ai sub-agent for the given role."""
    system_prompt = _SYSTEM_PROMPTS.get(role, PLANNER_SYSTEM)
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

    return Agent(
        model=model,
        system_prompt=system_prompt,
        output_type=output_type,
        retries=2,
    )


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


def _build_node_prompt(
    task: TaskCreate,
    role: AgentRole,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,  # noqa: ARG001 — reserved for future reviewer-retry context
) -> str:
    if role == AgentRole.PLANNER:
        return _planner_prompt(task)
    if role == AgentRole.CODER:
        return _coder_prompt(task, plan) if plan else _planner_prompt(task)
    if role == AgentRole.REVIEWER:
        if code is None:
            return f"Task: {task.description}\n\nNo code output available to review."
        return _reviewer_prompt(task, plan, code)
    # SCOUT or CONDUCTOR as a regular node — fall back to raw task description
    return f"Task: {task.description}\nWorkspace: {task.workspace}"


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
    # Treat "is" / "is not" as equality — avoids identity surprises with non-singletons
    if op.strip() in ("is", "=="):
        return lhs == rhs
    if op.strip() in ("is not", "!="):
        return lhs != rhs
    try:
        if op.strip() == "<":
            return lhs < rhs  # type: ignore[operator]
        if op.strip() == ">":
            return lhs > rhs  # type: ignore[operator]
        if op.strip() == "<=":
            return lhs <= rhs  # type: ignore[operator]
        if op.strip() == ">=":
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

    Supported forms: ``review.approved is False``, ``review.score < 7.0``,
    ``code.tests_added == True``.  Returns False if the path cannot be resolved
    or the condition is malformed — the edge is skipped, not crashed.
    """
    for op in _OPERATORS:
        if op in condition:
            lhs_str, rhs_str = condition.split(op, 1)
            lhs = _resolve_path(lhs_str.strip(), plan, code, review)
            if lhs is _MISSING:
                return False
            rhs = _parse_rhs(rhs_str.strip())
            return _compare(lhs, op, rhs)
    return False


# ---------------------------------------------------------------------------
# Edge routing
# ---------------------------------------------------------------------------


def _next_node(
    config: GraphConfig,
    current: AgentRole,
    plan: PlanOutput | None,
    code: CodeOutput | None,
    review: ReviewOutput | None,
) -> AgentRole | None:
    """Return the first outgoing edge whose condition is satisfied, or None."""
    for edge in config.edges:
        if edge.from_role != current:
            continue
        if edge.to_role is None:
            return None
        if edge.condition is None or evaluate_condition(edge.condition, plan, code, review):
            return edge.to_role
    return None


# ---------------------------------------------------------------------------
# Node dispatch
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


def _parse_node_json(
    role: AgentRole, raw: str
) -> PlanOutput | CodeOutput | ReviewOutput:
    data = json.loads(raw)
    output_type = _OUTPUT_TYPES.get(role, PlanOutput)
    return output_type.model_validate(data)  # type: ignore[return-value]


async def _dispatch_node(
    role: AgentRole,
    prompt: str,
    tier_config: TierConfig,
    resolved_model: str,
    base_url: str | None,
    use_json_mode: bool,
) -> tuple[PlanOutput | CodeOutput | ReviewOutput, int]:
    """Run one sub-agent node; return (typed_output, tokens_used)."""
    if not llm_circuit.allow_request():
        raise CircuitOpenError(llm_circuit)

    agent = _build_node_agent(role, resolved_model, base_url, use_json_mode)
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

            typed_output: PlanOutput | CodeOutput | ReviewOutput
            if use_json_mode:
                typed_output = _parse_node_json(role, result.output)
            else:
                typed_output = result.output  # type: ignore[assignment]

            return typed_output, tokens

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
# Graph executor — public entry point
# ---------------------------------------------------------------------------


async def run_graph_task(task: TaskCreate) -> HyperagentOutput:
    """Execute a task as a hyperagent graph.

    Iterates sub-agent nodes per task.graph_config, routes between them by
    evaluating edge conditions against accumulated outputs, and returns a
    HyperagentOutput with the full per-node trace.
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
        model=resolved_model,
        description=task.description[:DESCRIPTION_LOG_PREVIEW_LEN],
    )

    node_results: list[GraphNodeResult] = []
    plan: PlanOutput | None = None
    code: CodeOutput | None = None
    review: ReviewOutput | None = None

    current: AgentRole | None = config.entry
    cycle = 0

    while current is not None and cycle < config.max_cycles:
        await logger.ainfo("graph_node_dispatch", role=current, cycle=cycle)

        prompt = _build_node_prompt(task, current, plan, code, review)
        node_success = True
        output_str = ""
        tokens = 0
        next_role: AgentRole | None = None

        try:
            raw_output, tokens = await _dispatch_node(
                current, prompt, tier_config, resolved_model, base_url, use_json_mode
            )
            output_str = str(raw_output)[:500]

            if current == AgentRole.PLANNER and isinstance(raw_output, PlanOutput):
                plan = raw_output
            elif current == AgentRole.CODER and isinstance(raw_output, CodeOutput):
                code = raw_output
            elif current == AgentRole.REVIEWER and isinstance(raw_output, ReviewOutput):
                review = raw_output

        except Exception as exc:
            node_success = False
            output_str = f"error: {exc}"
            await logger.aerror("graph_node_failed", role=current, cycle=cycle, error=str(exc))

        next_role = _next_node(config, current, plan, code, review) if node_success else None

        node_results.append(
            GraphNodeResult(
                role=current,
                success=node_success,
                output=output_str,
                tokens_used=tokens,
                next_node=next_role,
            )
        )

        cycle += 1
        current = next_role

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
    )

    await logger.ainfo(
        "graph_complete",
        success=success,
        total_cycles=cycle,
        nodes_run=[r.role for r in node_results],
        review_approved=review.approved if review else None,
        review_score=review.score if review else None,
    )

    return result
