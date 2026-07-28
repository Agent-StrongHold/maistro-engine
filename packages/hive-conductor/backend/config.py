"""Environment-backed settings for Hive Conductor backend."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent
# Repo root `.env` (PM POC flags) — uvicorn cwd is usually `backend/`.
_ENV_FILES: tuple[str, ...] = tuple(
    str(p)
    for p in (
        _BACKEND_DIR / ".env",
        _BACKEND_DIR.parent.parent.parent / ".env",
        Path.cwd() / ".env",
    )
    if p.is_file()
)


class Settings(BaseSettings):
    """Load from process env and `.env` (backend dir, then repo root)."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES or ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    litellm_api_base: str | None = None
    litellm_api_key: SecretStr | None = None
    chat_default_model: str = "cerebras-qwen-3-235b-a22b-2507"
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

    # Open Design renderer plugin (SPEC-070426-6ea8). Off by default; when enabled the
    # design service registers the provider and /design/skills gains web/video skills.
    open_design_enabled: bool = False
    open_design_url: str = "http://127.0.0.1:7456"
    open_design_token: SecretStr | None = None

    # CORS allow-list. Defaults to local-dev origins; set CORS_ORIGINS (JSON list)
    # in deployment. Wildcard "*" is intentionally NOT the default — wildcard with
    # credentials is rejected by browsers and flagged as insecure.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8101",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8101",
    ]

    # Mark the session cookie Secure so browsers refuse to send it over plain
    # HTTP. Off by default because the documented dev loop is
    # http://localhost:8101 and a Secure cookie is silently dropped there,
    # which would look like "login does nothing". Turn it on for any
    # deployment reachable over TLS.
    session_cookie_secure: bool = False

    hardware_preset: Literal["potato", "laptop", "desktop", "beast"] = "laptop"
    poc_mode: str = ""
    maistro_base_url: str = "http://localhost:8000"
    # ADR-096: maistro-server is the canonical backend for production task
    # execution. "demo" is the only mode allowed to run an in-process
    # in-process LocalTaskBackend — see SPEC-226.
    hive_mode: Literal["production", "demo"] = "production"

    # Host-health API (:8150) backing the infra_monitor / infra_action capability
    # slots. Token is read from the vault (key HOST_HEALTH_TOKEN) with this env as
    # fallback. URL empty → infra providers are not wired (slots stay SAFE_NOOP).
    host_health_url: str | None = None
    host_health_token: SecretStr | None = None
    infra_autonomy: Literal["approve_all", "auto_safe", "detect_only"] = "auto_safe"
    # self_repair (SPEC-188) cadence; <=0 disables the periodic loop (API still works).
    self_repair_interval_s: int = 90


@lru_cache
def get_settings() -> Settings:
    return Settings()
