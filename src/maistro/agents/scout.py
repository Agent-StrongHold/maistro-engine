"""SCOUT node — workspace observer that populates GraphBlackboard.scout_context.

SCOUT runs before (or concurrently with) the PLANNER via a parallel=True edge.
It reads the workspace using the git and sandbox tools, identifies relevant files
and existing patterns, and writes structured findings to the blackboard so all
subsequent nodes start with shared situational awareness.

Without SCOUT: each node works blind — CODER invents patterns that may conflict
with existing conventions; PLANNER doesn't know which files already exist.

With SCOUT: PLANNER knows what to reference; CODER knows what to match;
REVIEWER knows what conventions to enforce.
"""

from __future__ import annotations

import asyncio
import os

import structlog
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from maistro.agents.prompts import SCOUT_SYSTEM
from maistro.agents.types import GraphBlackboard, ScoutContext, ScoutOutput
from maistro.config.model_resolver import resolve_model
from maistro.config.models import DEFAULT_TIERS, Tier, TierConfig
from maistro.observability.metrics import llm_requests_total, llm_tokens_used
from maistro.tasks.models import TaskCreate

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------


def _build_scout_agent(model: str, base_url: str | None, use_json_mode: bool) -> Agent:
    litellm_key = os.environ.get("LITELLM_MASTER_KEY", "")
    api_key = litellm_key if litellm_key else "ollama"

    system = SCOUT_SYSTEM
    output_type: type = ScoutOutput

    if use_json_mode:
        system = SCOUT_SYSTEM + """

You MUST respond with valid JSON matching this exact schema (no markdown, no extra text):
{
  "relevant_files": ["string"],
  "patterns": "string — conventions and idioms found",
  "dependency_map": {"file_path": ["import1", "import2"]},
  "similar_implementations": ["string"],
  "summary": "string — one paragraph briefing for the team"
}
"""
        output_type = str

    if base_url:
        model_name = model.removeprefix("openai:")
        provider = OpenAIProvider(base_url=base_url, api_key=api_key)
        openai_model = OpenAIChatModel(model_name, provider=provider)
        return Agent(
            model=openai_model,
            system_prompt=system,
            output_type=output_type,
            retries=2,
            model_settings={"extra_body": {"response_format": {"type": "json_object"}}}
            if use_json_mode
            else None,
        )

    return Agent(model=model, system_prompt=system, output_type=output_type, retries=2)


# ---------------------------------------------------------------------------
# Scout execution
# ---------------------------------------------------------------------------


def _scout_prompt(task: TaskCreate, blackboard: GraphBlackboard) -> str:
    history_summary = ""
    if blackboard.optimization_history:
        last = blackboard.optimization_history[-1]
        weakest = getattr(last, "weakest_node", None)
        avg_score = getattr(last, "avg_review_score", None)
        if weakest:
            score_str = f", avg review {avg_score:.1f}/10" if avg_score else ""
            history_summary = (
                f"\nOptimization history: iteration {blackboard.iteration}, "
                f"weakest node was {weakest}{score_str}. "
                f"Focus especially on context relevant to {weakest}."
            )

    return (
        f"Task: {task.description}\n\n"
        f"Workspace: {blackboard.workspace}\n"
        f"Iteration: {blackboard.iteration}{history_summary}\n\n"
        "Survey the workspace and provide a briefing for the engineering team."
    )


async def run_scout(
    task: TaskCreate,
    blackboard: GraphBlackboard,
    tier_config: TierConfig,
) -> GraphBlackboard:
    """Run the SCOUT node and write findings into the blackboard.

    Returns an updated blackboard with scout_context populated.
    Failures are logged but do not abort — nodes fall back to working without
    scout context rather than crashing the pipeline.
    """
    resolved_model, base_url, use_json_mode = resolve_model(tier_config.model)

    await logger.ainfo(
        "scout_start",
        workspace=blackboard.workspace,
        iteration=blackboard.iteration,
        model=resolved_model,
    )

    try:
        agent = _build_scout_agent(resolved_model, base_url, use_json_mode)
        prompt = _scout_prompt(task, blackboard)

        llm_requests_total.inc()
        result = await asyncio.wait_for(agent.run(prompt), timeout=tier_config.timeout)

        tokens = 0
        try:
            usage = result.usage()
            tokens = usage.total_tokens or 0
            if tokens:
                llm_tokens_used.observe(float(tokens), tier=str(tier_config.tier.value))
        except Exception:
            pass

        if use_json_mode:
            import json

            data = json.loads(result.output)
            scout_out = ScoutOutput.model_validate(data)
        else:
            scout_out = result.output  # type: ignore[assignment]

        scout_context = ScoutContext(
            relevant_files=scout_out.relevant_files,
            patterns=scout_out.patterns,
            dependency_map=scout_out.dependency_map,
            similar_implementations=scout_out.similar_implementations,
            raw_findings=scout_out.summary,
        )

        await logger.ainfo(
            "scout_complete",
            relevant_files=len(scout_context.relevant_files),
            tokens=tokens,
        )

        return blackboard.model_copy(update={"scout_context": scout_context})

    except Exception as exc:
        await logger.awarning("scout_failed", error=str(exc))
        return blackboard  # non-fatal — nodes proceed without scout context
