"""Environment variable sanitization for sandbox containers.

Prevents leaking secrets into sandbox environments. Pattern ported from
OpenClaw's docker.ts env sanitization blocklist.
"""

from __future__ import annotations

import re

# Environment variable names that must never be passed to sandbox containers.
# Uses prefix matching — any env var starting with these strings is blocked.
BLOCKED_PREFIXES = (
    "API_KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "CREDENTIAL",
    "PRIVATE_KEY",
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_",
    "ANTHROPIC_",
    "OPENAI_",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "NPM_TOKEN",
    "PYPI_TOKEN",
    "DOCKER_",
    "KUBECONFIG",
    "SSH_",
    "PGP_",
    "GPG_",
    "LANGFUSE_",
    "LITELLM_",
    "DB_PASSWORD",
    "DATABASE_URL",
    "REDIS_URL",
    "MAISTRO_API",
)

# Exact env var names to block
BLOCKED_EXACT = frozenset({
    "HOME",
    "USER",
    "LOGNAME",
    "HOSTNAME",
    "MAIL",
})

# Pattern for values that look like secrets (base64-ish, hex, JWT)
_SECRET_PATTERN = re.compile(
    r"^(sk-[a-zA-Z0-9]{20,}|"  # OpenAI-style keys
    r"ghp_[a-zA-Z0-9]{36}|"  # GitHub PATs
    r"ghs_[a-zA-Z0-9]{36}|"  # GitHub App tokens
    r"Bearer\s+[a-zA-Z0-9._-]{20,}|"  # Bearer tokens
    r"[a-f0-9]{64}|"  # 256-bit hex keys
    r"eyJ[a-zA-Z0-9._-]{20,})$"  # JWTs
)


def is_blocked_name(name: str) -> bool:
    """Check if an env var name should be blocked from sandbox."""
    upper = name.upper()
    if upper in BLOCKED_EXACT:
        return True
    return any(upper.startswith(prefix) for prefix in BLOCKED_PREFIXES)


def looks_like_secret(value: str) -> bool:
    """Heuristic check if a value looks like a secret/token."""
    return bool(_SECRET_PATTERN.match(value.strip()))


def sanitize_env(env: dict[str, str]) -> dict[str, str]:
    """Filter environment variables, removing anything that looks sensitive.

    Returns a new dict with only safe env vars.
    """
    return {
        k: v
        for k, v in env.items()
        if not is_blocked_name(k) and not looks_like_secret(v)
    }
