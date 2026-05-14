"""Environment-backed settings for Hive Conductor backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load from process env and optional `.env` in cwd (e.g. `backend/`)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    litellm_api_base: str | None = None
    litellm_api_key: SecretStr | None = None
    chat_default_model: str = "mistral-large"
    llm_http_variant: Literal["auto", "responses", "chat_completions"] = "auto"

    maistro_router_api_key: str | None = None
    maistro_agents_dir: str = "agents"
    maistro_llm_base_url: str | None = None
    maistro_llm_api_key: SecretStr | None = None
    maistro_model: str = "mistral-large"

    conductor_data_dir: str = "~/.conductor"
    conductor_vault_path: str | None = None
    conductor_identity_path: str | None = None
    conductor_state_db: str | None = None
    conductor_admin_public_key: str | None = None
    conductor_user_public_key: str | None = None

    hardware_preset: Literal["potato", "laptop", "desktop", "beast"] = "laptop"


@lru_cache
def get_settings() -> Settings:
    return Settings()
