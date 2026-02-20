"""Conductor agent — top-level orchestrator for engineering tasks.

Phase 1: Single Pydantic AI agent that handles plan/code/review in one pass.
Phase 2 will split this into sub-agents (planner, coder, reviewer, scout).

For Ollama models that don't support complex tool schemas, the conductor falls
back to JSON-prompt mode: it instructs the model to return JSON directly and
parses/validates the response with Pydantic.
"""

from __future__ import annotations

import json
import os

import structlog
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from maistro.agents.prompts import CONDUCTOR_SYSTEM
from maistro.agents.types import ConductorOutput, PlanOutput, SubTask
from maistro.config.models import DEFAULT_TIERS, Tier, TierConfig
from maistro.tasks.models import TaskCreate

logger = structlog.get_logger()

# JSON schema appended to the system prompt for Ollama JSON-mode fallback
_CONDUCTOR_JSON_SCHEMA = """\

You MUST respond with valid JSON matching this exact schema (no markdown, no extra text):
{
  "plan": {
    "summary": "string — brief plan summary",
    "subtasks": [
      {"title": "string", "description": "string"}
    ]
  },
  "final_answer": "string — concise summary of what you would implement",
  "success": true
}
"""


def _get_tier_config(tier: int | None) -> TierConfig:
    t = Tier(tier) if tier and tier in [e.value for e in Tier] else Tier.STANDARD
    return DEFAULT_TIERS[t]


def _resolve_model(tier_model: str) -> tuple[str, str | None, bool]:
    """Resolve a tier model name to (pydantic_ai_model, base_url, use_json_mode).

    Returns use_json_mode=True for Ollama models that need JSON-prompt fallback
    instead of tool-based structured output.
    """
    litellm_url = os.environ.get("LITELLM_BASE_URL", "")
    if litellm_url:
        model_name = tier_model.split("/")[-1]
        return f"openai:{model_name}", litellm_url, False

    # Ollama: strip ollama/ prefix, use OpenAI-compat endpoint
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    if tier_model.startswith("ollama/"):
        model_name = tier_model.removeprefix("ollama/")
        return f"openai:{model_name}", ollama_url, True

    # Direct provider access — no base_url override
    return tier_model, None, False


def build_conductor(
    model: str | KnownModelName | None = None,
    base_url: str | None = None,
    use_json_mode: bool = False,
) -> Agent[None, ConductorOutput] | Agent[None, str]:
    """Build a conductor agent with the given model.

    When use_json_mode=True (for Ollama models), returns a str-output agent
    that uses JSON response_format. The caller must parse the JSON into
    ConductorOutput manually.
    """
    system_prompt = CONDUCTOR_SYSTEM
    output_type: type = ConductorOutput

    if use_json_mode:
        # Ollama JSON-mode: prompt for JSON, return raw string
        system_prompt = CONDUCTOR_SYSTEM + _CONDUCTOR_JSON_SCHEMA
        output_type = str

    if base_url:
        model_name = (model or "openai:maistro-default").removeprefix("openai:")
        provider = OpenAIProvider(base_url=base_url, api_key="ollama")
        openai_model = OpenAIChatModel(model_name, provider=provider)
        return Agent(
            model=openai_model,
            system_prompt=system_prompt,
            output_type=output_type,
            retries=3,
            model_settings={
                "extra_body": {"response_format": {"type": "json_object"}},
            } if use_json_mode else None,
        )

    return Agent(
        model=model or "openai:maistro-default",
        system_prompt=system_prompt,
        output_type=output_type,
        retries=3,
    )


def _parse_json_output(raw: str) -> ConductorOutput:
    """Parse raw JSON string from Ollama into a validated ConductorOutput."""
    data = json.loads(raw)
    return ConductorOutput.model_validate(data)


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
    resolved_model, base_url, use_json_mode = _resolve_model(tier_config.model)

    await logger.ainfo(
        "conductor_start",
        tier=tier_config.tier,
        model=resolved_model,
        base_url=base_url or "default",
        json_mode=use_json_mode,
        description=task.description[:80],
    )

    agent = build_conductor(model=resolved_model, base_url=base_url, use_json_mode=use_json_mode)

    constraints_text = "\n".join(f"- {c}" for c in task.constraints) if task.constraints else "None"
    prompt = (
        f"Task: {task.description}\n\n"
        f"Workspace: {task.workspace}\n"
        f"Constraints:\n{constraints_text}"
    )

    result = await agent.run(prompt)

    if use_json_mode:
        # Parse raw JSON string into ConductorOutput
        output = _parse_json_output(result.output)
        await logger.ainfo("conductor_complete", success=output.success, mode="json")
        return output

    await logger.ainfo("conductor_complete", success=result.output.success, mode="tool")
    return result.output
