"""Environment-backed settings for Hive Conductor backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load from process env and optional `.env` in cwd (e.g. `backend/`)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI-compatible LiteLLM proxy base URL (must include /v1), e.g. https://litellm.internal.example.com/v1
    # Use the **API** host (not `*-admin*` UIs). No admin-only routes are called from Hive.
    litellm_api_base: str | None = None
    litellm_api_key: SecretStr | None = None
    chat_default_model: str = "gpt-4o"
    # Prefer OpenAI Responses when the gateway supports it; ``auto`` falls back to chat.completions.
    llm_http_variant: Literal["auto", "responses", "chat_completions"] = "auto"

    # maistro-core integration (embed mode — one process, one port)
    # Set MAISTRO_ROUTER_API_KEY to enable real agent routing; omit to run in stub mode.
    maistro_router_api_key: str | None = None
    maistro_agents_dir: str = "agents"
    maistro_llm_base_url: str | None = None  # e.g. http://litellm:4000/v1
    maistro_llm_api_key: SecretStr | None = None
    maistro_model: str = "gpt-4o"


@lru_cache
def get_settings() -> Settings:
    return Settings()
