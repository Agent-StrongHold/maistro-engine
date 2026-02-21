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

    # Connection pooling (Item 66)
    pool_size: int = 5
    max_overflow: int = 10
    pool_recycle: int = 1800  # seconds

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
    network_disabled: bool = True


class OllamaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OLLAMA_")

    base_url: str = "http://localhost:11434/v1"


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
    require_auth: bool = Field(
        default=True,
        description="Refuse to start without API keys. Set REQUIRE_AUTH=false for local dev only.",
    )
    github_webhook_secret: str = ""
    ci_webhook_secret: str = ""

    # CORS
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3080"],
        description="Allowed CORS origins",
    )

    # Default LLM model for agents
    default_model: str = "anthropic/claude-sonnet-4-20250514"

    # LLM cost controls
    max_tokens_per_task: int = Field(default=100_000, description="Max LLM tokens per task")

    # LLM model routing — consolidated from os.environ.get() calls
    ollama_base_url: str = "http://localhost:11434/v1"
    maistro_dry_run: bool = False

    # Per-tier model overrides
    tier_1_model: str = ""
    tier_2_model: str = ""
    tier_3_model: str = ""
    tier_4_model: str = ""

    # Request limits
    max_webhook_body_bytes: int = 1_048_576  # 1 MB

    # Rate limiting
    rate_limit_per_minute: int = 60  # per-client requests/minute
    rate_limit_burst: int = 10  # burst allowance

    # Sub-configs
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    litellm: LiteLLMSettings = Field(default_factory=LiteLLMSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)


@functools.lru_cache()
def get_settings() -> Settings:
    return Settings()
