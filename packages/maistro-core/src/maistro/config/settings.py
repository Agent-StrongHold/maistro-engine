"""Application settings loaded from environment variables and optional YAML config."""

from __future__ import annotations

import functools
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 5432
    name: str = "maistro"
    user: str = "maistro"
    password: str = "maistro"

    pool_size: int = 5
    max_overflow: int = 10
    pool_recycle: int = 1800

    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        )

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


class NtfySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NTFY_")

    base_url: str = ""
    default_topic: str = ""
    access_token: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "maistro-engine"
    debug: bool = False
    # Default to loopback so a careless dev-server start doesn't expose the
    # API on every interface. Container deployments override this via the
    # HOST env var (e.g. HOST=0.0.0.0 in docker-compose for the server svc).
    host: str = "127.0.0.1"
    port: int = 8000

    api_keys: list[str] = Field(default_factory=list, description="Valid API bearer tokens")
    require_auth: bool = Field(
        default=True,
        description="Refuse to start without API keys. Set REQUIRE_AUTH=false for local dev only.",
    )
    github_webhook_secret: str = ""
    ci_webhook_secret: str = ""

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3080"],
        description="Allowed CORS origins",
    )

    default_model: str = "anthropic/claude-sonnet-4-20250514"

    max_tokens_per_task: int = Field(default=100_000, description="Max LLM tokens per task")

    ollama_base_url: str = "http://localhost:11434/v1"
    maistro_dry_run: bool = False
    poc_mode: str = Field(
        default="",
        description="POC mode: empty=engineering, pm=project-management fleet",
        validation_alias="MAISTRO_POC_MODE",
    )

    tier_1_model: str = ""
    tier_2_model: str = ""
    tier_3_model: str = ""
    tier_4_model: str = ""

    max_webhook_body_bytes: int = 1_048_576

    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 10

    task_progress_webhook_url: str = Field(
        default="",
        description="Full URL for optional task progress POST (legacy conductor-router). Empty disables.",
    )
    task_progress_webhook_api_key: str = Field(
        default="",
        description="Bearer token sent with progress webhook requests when non-empty.",
    )

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    litellm: LiteLLMSettings = Field(default_factory=LiteLLMSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    ntfy: NtfySettings = Field(default_factory=NtfySettings)


class RoutingConfig(BaseModel):
    quality_weight: float = 0.6
    cost_weight: float = 0.4
    reserve_pct: float = 0.05
    priority_multipliers: dict[str, float] = Field(
        default_factory=lambda: {
            "P0": 1.5,
            "P1": 1.2,
            "P2": 1.0,
            "P3": 0.9,
            "P4": 0.8,
            "P5": 0.7,
        }
    )


class TaskTypeConfig(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    min_tier: str = "small"
    preferred_strengths: list[str] = Field(default_factory=lambda: ["chat"])


class SessionsConfig(BaseModel):
    max_messages: int = 20
    ttl_seconds: int = 86400


class LearningsConfig(BaseModel):
    rca_enabled: bool = True
    rca_model: str = ""
    promotion_threshold: int = 5


class SecurityConfig(BaseModel):
    warden_enabled: bool = True
    sentinel_enabled: bool = True
    gate_query_improve: bool = True
    gate_model: str = "auto"


class CORSConfig(BaseModel):
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3200"])
    allowed_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )
    allowed_headers: list[str] = Field(
        default_factory=lambda: [
            "Authorization",
            "Content-Type",
        ]
    )
    allow_credentials: bool = True


class RateLimitConfig(BaseModel):
    requests_per_minute: int = 300
    burst_limit: int = 50
    enabled: bool = True


class AuthConfig(BaseModel):
    jwt_secret: str = ""
    jwks_url: str = ""
    issuer: str = ""
    audience: str = ""
    client_id: str = ""
    client_secret: str = ""
    authorization_url: str = ""
    token_url: str = ""
    session_cookie_name: str = "maistro_session"
    session_max_age: int = 3600


class MaistroYamlConfig(BaseModel):
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    models: dict[str, dict[str, Any]] = Field(default_factory=dict)
    task_types: dict[str, TaskTypeConfig] = Field(default_factory=dict)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)
    learnings: LearningsConfig = Field(default_factory=LearningsConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    cors: CORSConfig = Field(default_factory=CORSConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    model_groups: dict[str, dict[str, Any]] = Field(default_factory=dict)
    permissions: dict[str, list[str]] = Field(default_factory=dict)
    database_url: str = ""
    redis_url: str = ""
    agents_dir: str = ""
    litellm_url: str = "http://litellm:4000"
    litellm_key: str = ""
    router_api_key: str = ""
    jwt_secret: str = ""
    phoenix_endpoint: str = ""
    cors_origins: list[str] = Field(default_factory=list)
    max_request_body_bytes: int = 1_048_576
    webhook_secret: str = ""
    cache_breakpoints_enabled: bool = False


_yaml_config: MaistroYamlConfig | None = None


def get_yaml_config() -> MaistroYamlConfig | None:
    return _yaml_config


def set_yaml_config(cfg: MaistroYamlConfig | None) -> None:
    global _yaml_config
    _yaml_config = cfg


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
