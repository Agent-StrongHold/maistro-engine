"""Conductor agent — top-level orchestrator for engineering tasks.

Phase 1: Single Pydantic AI agent that handles plan/code/review in one pass.
Phase 2 will split this into sub-agents (planner, coder, reviewer, scout).
"""

from __future__ import annotations

import os

import structlog
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from maistro.agents.prompts import CONDUCTOR_SYSTEM
from maistro.agents.types import ConductorOutput, PlanOutput, SubTask
from maistro.config.models import Tier, TierConfig, get_tier_config
from maistro.tasks.models import TaskCreate

logger = structlog.get_logger()


def _get_tier_config(tier: int | None) -> TierConfig:
    t = Tier(tier) if tier and tier in [e.value for e in Tier] else Tier.STANDARD
    return get_tier_config(t)


def _resolve_model(tier_model: str) -> tuple[str, str | None]:
    """Resolve a tier model name to a Pydantic AI model string + base_url.

    Returns (model_string, base_url) where base_url is set for Ollama/LiteLLM.
    """
    litellm_url = os.environ.get("LITELLM_BASE_URL", "")
    if litellm_url:
        model_name = tier_model.split("/")[-1]
        return f"openai:{model_name}", litellm_url

    # Ollama: strip ollama/ prefix, use OpenAI-compat endpoint
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    if tier_model.startswith("ollama/"):
        model_name = tier_model.removeprefix("ollama/")
        return f"openai:{model_name}", ollama_url

    # Direct provider access — no base_url override
    return tier_model, None


def build_conductor(
    model: str | KnownModelName | None = None,
    base_url: str | None = None,
) -> Agent[None, ConductorOutput]:
    """Build a conductor agent with the given model.

    The conductor is a single agent (Phase 1) that handles the full
    plan → code → review pipeline via structured output.
    """
    if base_url:
        # Use OpenAI-compatible provider with custom base_url (for Ollama / LiteLLM)
        model_name = (model or "openai:maistro-default").removeprefix("openai:")
        provider = OpenAIProvider(base_url=base_url, api_key="ollama")
        openai_model = OpenAIChatModel(model_name, provider=provider)
        return Agent(
            model=openai_model,
            system_prompt=CONDUCTOR_SYSTEM,
            output_type=ConductorOutput,
            retries=3,
        )

    return Agent(
        model=model or "openai:maistro-default",
        system_prompt=CONDUCTOR_SYSTEM,
        output_type=ConductorOutput,
        retries=3,
    )


async def run_task(task: TaskCreate) -> ConductorOutput:
    """Execute a full engineering task through the conductor pipeline.

    This is the main entry point for task execution. It:
    1. Selects the appropriate tier/model configuration
    2. Builds the conductor agent
    3. Runs the agent with the task description
    4. Returns structured output

    If MAISTRO_DRY_RUN=1 is set, returns a mock result without calling any LLM.
    """
    # Dry-run mode — return mock result without LLM call
    if os.environ.get("MAISTRO_DRY_RUN", "").strip() in ("1", "true", "yes"):
        await logger.ainfo("conductor_dry_run", description=task.description[:80])
        return ConductorOutput(
            plan=PlanOutput(
                summary=f"[DRY RUN] Plan for: {task.description}",
                subtasks=[
                    SubTask(
                        title="Analyze requirements",
                        description=task.description,
                    ),
                    SubTask(
                        title="Implement solution",
                        description="Write the code changes",
                    ),
                    SubTask(
                        title="Add tests",
                        description="Write test coverage",
                    ),
                ],
            ),
            final_answer=f"[DRY RUN] Task planned: {task.description}",
            success=True,
        )

    tier_config = _get_tier_config(task.tier)
    resolved_model, base_url = _resolve_model(tier_config.model)

    await logger.ainfo(
        "conductor_start",
        tier=tier_config.tier,
        model=resolved_model,
        base_url=base_url or "default",
        description=task.description[:80],
    )

    agent = build_conductor(model=resolved_model, base_url=base_url)

    constraints_text = "\n".join(f"- {c}" for c in task.constraints) if task.constraints else "None"
    prompt = (
        f"Task: {task.description}\n\n"
        f"Workspace: {task.workspace}\n"
        f"Constraints:\n{constraints_text}"
    )

    result = await agent.run(prompt)
    await logger.ainfo("conductor_complete", success=result.output.success)
    return result.output
