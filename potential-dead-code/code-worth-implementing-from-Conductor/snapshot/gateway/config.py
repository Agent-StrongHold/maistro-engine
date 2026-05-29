"""Gateway configuration — all settings overridable via CONDUCTOR_ env vars."""

from __future__ import annotations

import threading

from pydantic_settings import BaseSettings


class GatewayConfig(BaseSettings):
    """Configuration for the Inference Gateway.

    Slot layout:
        - template_slot_id: Reserved for pre-warmed project context (never used for generation)
        - worker_slot_ids: Pool of slots for actual generation
        - Total slots = 1 (template) + N (workers). Adjust based on your llama-server --parallel flag.

    Important: worker_slot_ids count should match llama-server's --parallel minus 1.
    """

    # Inference engine connection
    llama_server_url: str = "http://localhost:8080"

    # Slot layout (adjust based on llama-server --parallel value)
    template_slot_id: int = 0
    worker_slot_ids: list[int] = [1, 2, 3, 4]  # Default: --parallel 5

    # KV cache persistence — MUST match llama-server --slot-save-path
    kv_cache_dir: str = "./kv-cache"

    # Ultra Think tier configuration
    # candidates_per_tier: how many candidates to generate at each tier
    tier1_candidates: int = 1
    tier2_candidates: int = 3
    tier3_candidates: int = 5
    default_max_tokens: int = 4096

    # Timeouts (in seconds)
    generation_timeout_seconds: int = 300
    slot_restore_timeout_seconds: int = 30
    prefix_warm_timeout_seconds: int = 120  # Timeout for warming template slot

    # Client configuration
    http_client_timeout_seconds: int = 600  # Total request timeout

    # Health check configuration
    health_check_path: str = "/health"  # Endpoint to check on inference server

    # Metrics
    metrics_log_path: str = "./metrics/gateway.jsonl"

    # Logging
    log_format: str = "text"  # "text" or "json"

    model_config = {"env_prefix": "CONDUCTOR_"}


# Thread-safe singleton
_config_lock = threading.Lock()
_config_instance: GatewayConfig | None = None


def get_config() -> GatewayConfig:
    """Return a thread-safe singleton config instance."""
    global _config_instance
    if _config_instance is None:
        with _config_lock:
            if _config_instance is None:
                _config_instance = GatewayConfig()
    return _config_instance


def reset_config() -> None:
    """Reset config for testing purposes."""
    global _config_instance
    with _config_lock:
        _config_instance = None
