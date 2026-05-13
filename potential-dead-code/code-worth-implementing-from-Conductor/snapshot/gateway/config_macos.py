"""Gateway configuration for macOS with limited RAM (16GB MacBook Air).

Use with: CONDUCTOR_CONFIG=macos python -m uvicorn gateway.server:app
Or set individual env vars.
"""

from gateway.config import GatewayConfig

# macOS-optimized defaults
MACOS_DEFAULTS = {
    "worker_slot_ids": [1],  # Only 1 worker (2 total slots)
    "tier1_candidates": 1,
    "tier2_candidates": 1,   # No parallel generation on limited RAM
    "tier3_candidates": 2,   # Max 2 candidates
    "default_max_tokens": 2048,  # Shorter generations
    "generation_timeout_seconds": 180,  # Shorter timeout
}


def get_macos_config() -> GatewayConfig:
    """Return config optimized for macOS 16GB."""
    return GatewayConfig(**MACOS_DEFAULTS)
