"""Application settings loaded from environment variables."""

from __future__ import annotations

import functools

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "maistro"
    user: str = "maistro"
    password: str = "maistro"

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class LiteLLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LITELLM_")

    base_url: str = "http://localhost:4000"
    master_key: str = ""


class LangfuseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LANGFUSE_")

    host: str = "http://localhost:3000"
    public_key: str = ""
    secret_key: str = ""
    enabled: bool = True


class SandboxSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SANDBOX_")

    image: str = "python:3.12-slim"
    memory_limit: str = "512m"
    cpu_count: int = 2
    timeout: int = 300
    network_disabled: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "maistro-engine"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Auth
    api_keys: list[str] = Field(default_factory=list, description="Valid API bearer tokens")
    github_webhook_secret: str = ""
    ci_webhook_secret: str = ""

    # Default LLM model for agents
    default_model: str = "anthropic/claude-sonnet-4-20250514"

    # Request limits
    max_webhook_body_bytes: int = 1_048_576  # 1 MB

    # Sub-configs
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    litellm: LiteLLMSettings = Field(default_factory=LiteLLMSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)


@functools.lru_cache()
def get_settings() -> Settings:
    return Settings()
