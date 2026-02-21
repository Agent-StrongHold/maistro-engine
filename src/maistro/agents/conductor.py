"""Conductor agent — top-level orchestrator for engineering tasks.

Phase 1: Single Pydantic AI agent that handles plan/code/review in one pass.
Phase 2 will split this into sub-agents (planner, coder, reviewer, scout).

For Ollama models that don't support complex tool schemas, the conductor falls
back to JSON-prompt mode: it instructs the model to return JSON directly and
parses/validates the response with Pydantic.
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
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from maistro.agents.circuit_breaker import CircuitOpenError, llm_circuit
from maistro.agents.prompts import CONDUCTOR_SYSTEM
from maistro.agents.types import ConductorOutput, LLMProviderError, PlanOutput, SubTask
from maistro.config.model_resolver import resolve_model
from maistro.config.models import DEFAULT_TIERS, Tier, TierConfig
from maistro.config.settings import get_settings
from maistro.constants import DESCRIPTION_LOG_PREVIEW_LEN
from maistro.observability.metrics import llm_errors_total, llm_requests_total
from maistro.observability.tracing import trace_agent
from maistro.tasks.models import TaskCreate

logger = structlog.get_logger()

# HTTP status codes that indicate transient failures worth retrying
_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

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


@functools.lru_cache(maxsize=16)
def build_conductor(
    model: str | KnownModelName | None = None,
    base_url: str | None = None,
    use_json_mode: bool = False,
) -> Agent[None, ConductorOutput] | Agent[None, str]:
    """Build a conductor agent with the given model.

    When use_json_mode=True (for Ollama models), returns a str-output agent
    that uses JSON response_format. The caller must parse the JSON into
    ConductorOutput manually.

    Agents are cached by (model, base_url, use_json_mode) to avoid re-compiling schemas.
    """
    system_prompt = CONDUCTOR_SYSTEM
    output_type: type = ConductorOutput

    litellm_key = os.environ.get("LITELLM_MASTER_KEY", "")
    api_key = litellm_key if litellm_key else "ollama"

    if use_json_mode:
        system_prompt = CONDUCTOR_SYSTEM + _CONDUCTOR_JSON_SCHEMA
        output_type = str

    if base_url:
        model_name = (model or "openai:maistro-default").removeprefix("openai:")
        provider = OpenAIProvider(base_url=base_url, api_key=api_key)
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


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception represents a transient failure worth retrying."""
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return False


def _parse_json_output(raw: str) -> ConductorOutput:
    """Parse raw JSON string from Ollama into a validated ConductorOutput."""
    data = json.loads(raw)
    return ConductorOutput.model_validate(data)


async def _run_with_retry(
    agent: Agent,
    prompt: str,
    tier_config: TierConfig,
    use_json_mode: bool = False,
) -> ConductorOutput:
    """Run the agent with timeout and retry logic for transient failures."""
    if not llm_circuit.allow_request():
        raise CircuitOpenError(llm_circuit)

    last_exc: Exception | None = None

    for attempt in range(tier_config.max_llm_retries):
        try:
            llm_requests_total.inc()
            result = await asyncio.wait_for(
                agent.run(prompt), timeout=tier_config.timeout
            )
            llm_circuit.record_success()

            if use_json_mode:
                return _parse_json_output(result.output)
            return result.output
        except TimeoutError as exc:
            last_exc = exc
            await logger.awarning(
                "llm_timeout",
                attempt=attempt + 1,
                max_retries=tier_config.max_llm_retries,
                timeout=tier_config.timeout,
            )
        except Exception as exc:
            if _is_retryable(exc):
                last_exc = exc
                await logger.awarning(
                    "llm_transient_error",
                    attempt=attempt + 1,
                    max_retries=tier_config.max_llm_retries,
                    error=str(exc),
                )
            else:
                llm_circuit.record_failure()
                llm_errors_total.inc(error_type="non_retryable")
                raise

        llm_circuit.record_failure()
        llm_errors_total.inc(error_type="retryable")

        # Exponential backoff with jitter before retry
        if attempt < tier_config.max_llm_retries - 1:
            delay = tier_config.initial_backoff * (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(delay)

    raise LLMProviderError(
        f"LLM call failed after {tier_config.max_llm_retries} retries: {last_exc}"
    )


@trace_agent("conductor")
async def run_task(task: TaskCreate) -> ConductorOutput:
    """Execute a full engineering task through the conductor pipeline.

    This is the main entry point for task execution. It:
    1. Selects the appropriate tier/model configuration
    2. Builds the conductor agent
    3. Runs the agent with timeout and retry logic
    4. Returns structured output

    If maistro_dry_run is set in settings, returns a mock result without calling any LLM.
    """
    settings = get_settings()

    # Dry-run mode — return mock result without LLM call
    if settings.maistro_dry_run:
        await logger.ainfo("conductor_dry_run", description=task.description[:DESCRIPTION_LOG_PREVIEW_LEN])
        return ConductorOutput(
            plan=PlanOutput(
                summary=f"[DRY RUN] Plan for: {task.description}",
                subtasks=[
                    SubTask(title="Analyze requirements", description=task.description),
                    SubTask(title="Implement solution", description="Write the code changes"),
                    SubTask(title="Add tests", description="Write test coverage"),
                ],
            ),
            final_answer=f"[DRY RUN] Task planned: {task.description}",
            success=True,
        )

    # MAJ-08: Enforce token budget from settings
    max_tokens = settings.max_tokens_per_task

    tier_config = _get_tier_config(task.tier)
    resolved_model, base_url, use_json_mode = resolve_model(tier_config.model)

    await logger.ainfo(
        "conductor_start",
        tier=tier_config.tier,
        model=resolved_model,
        base_url=base_url or "default",
        json_mode=use_json_mode,
        max_tokens=max_tokens,
        description=task.description[:DESCRIPTION_LOG_PREVIEW_LEN],
    )

    agent = build_conductor(model=resolved_model, base_url=base_url, use_json_mode=use_json_mode)

    constraints_text = "\n".join(f"- {c}" for c in task.constraints) if task.constraints else "None"
    prompt = (
        f"Task: {task.description}\n\n"
        f"Workspace: {task.workspace}\n"
        f"Constraints:\n{constraints_text}"
    )

    result = await _run_with_retry(agent, prompt, tier_config, use_json_mode=use_json_mode)
    await logger.ainfo("conductor_complete", success=result.success)
    return result
