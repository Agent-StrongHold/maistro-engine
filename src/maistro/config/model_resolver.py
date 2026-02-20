"""Model resolution — maps tier model names to Pydantic AI model strings.

Extracted from agents/conductor.py to keep infrastructure concerns
(URL manipulation, settings reads) separate from agent logic.
"""

from __future__ import annotations

from maistro.config.settings import get_settings


def resolve_model(tier_model: str) -> tuple[str, str | None]:
    """Resolve a tier model name to a Pydantic AI model string + base_url.

    Returns (model_string, base_url) where base_url is set for Ollama/LiteLLM.
    """
    settings = get_settings()

    if settings.litellm.base_url and settings.litellm.base_url != "http://localhost:4000":
        model_name = tier_model.split("/")[-1]
        return f"openai:{model_name}", settings.litellm.base_url

    # Ollama: strip ollama/ prefix, use OpenAI-compat endpoint
    if tier_model.startswith("ollama/"):
        model_name = tier_model.removeprefix("ollama/")
        return f"openai:{model_name}", settings.ollama_base_url

    # Direct provider access — no base_url override
    return tier_model, None
