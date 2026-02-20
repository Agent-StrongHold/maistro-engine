"""Tests for environment variable sanitization.

Evidence source: OpenClaw's docker.ts uses an env var blocklist to prevent
secret leakage into sandbox containers. The blocklist uses prefix matching
and includes all major cloud/API provider prefixes.
"""

from __future__ import annotations

import pytest

from maistro.tools.sandbox.env_sanitize import is_blocked_name, looks_like_secret, sanitize_env


class TestBlockedNames:
    """Evidence: OpenClaw blocks env vars by prefix — any var starting with
    AWS_, AZURE_, GOOGLE_, OPENAI_, etc. is blocked from sandbox."""

    @pytest.mark.parametrize(
        "name",
        [
            "API_KEY", "API_KEY_ANTHROPIC",
            "SECRET_TOKEN", "SECRET_KEY",
            "TOKEN_VALUE",
            "PASSWORD", "PASSWORD_DB",
            "CREDENTIAL_FILE",
            "PRIVATE_KEY",
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "AZURE_SUBSCRIPTION_ID",
            "GCP_PROJECT",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "NPM_TOKEN",
            "PYPI_TOKEN",
            "DOCKER_HOST",
            "KUBECONFIG",
            "SSH_AUTH_SOCK",
            "PGP_KEY",
            "GPG_KEY",
            "LANGFUSE_SECRET_KEY",
            "LITELLM_MASTER_KEY",
            "DB_PASSWORD",
            "DATABASE_URL",
            "REDIS_URL",
            "MAISTRO_API_KEY",
        ],
    )
    def test_blocked_prefixes(self, name: str) -> None:
        assert is_blocked_name(name), f"{name} should be blocked"

    @pytest.mark.parametrize(
        "name",
        ["PATH", "LANG", "TERM", "SHELL", "EDITOR", "PYTHONPATH",
         "NODE_ENV", "DEBUG", "LOG_LEVEL", "PORT"],
    )
    def test_safe_names_allowed(self, name: str) -> None:
        assert not is_blocked_name(name), f"{name} should be allowed"

    def test_case_insensitive(self) -> None:
        """Evidence: Env var blocking should be case-insensitive."""
        assert is_blocked_name("api_key")
        assert is_blocked_name("Api_Key")


class TestLooksLikeSecret:
    """Evidence: OpenClaw also checks env var values for patterns that
    look like secrets (API keys, JWTs, hex strings)."""

    @pytest.mark.parametrize(
        "value",
        [
            "sk-1234567890abcdef1234567890abcdef",      # OpenAI-style key
            "ghp_abcdefghijklmnopqrstuvwxyz1234567890",  # GitHub PAT
            "ghs_abcdefghijklmnopqrstuvwxyz1234567890",  # GitHub App token
            "a" * 64,                                     # 256-bit hex
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",  # JWT
        ],
    )
    def test_secret_patterns_detected(self, value: str) -> None:
        assert looks_like_secret(value), f"Should detect as secret: {value[:20]}..."

    @pytest.mark.parametrize(
        "value",
        ["hello", "true", "8080", "/usr/local/bin", "production",
         "INFO", "utf-8", "en_US.UTF-8"],
    )
    def test_normal_values_not_flagged(self, value: str) -> None:
        assert not looks_like_secret(value)


class TestSanitizeEnv:
    """Integration test: sanitize_env removes both blocked names and secret-looking values."""

    def test_filters_blocked_names(self) -> None:
        env = {
            "PATH": "/usr/bin",
            "AWS_SECRET_KEY": "mysecret",
            "LANG": "en_US.UTF-8",
            "OPENAI_API_KEY": "sk-test",
        }
        result = sanitize_env(env)
        assert "PATH" in result
        assert "LANG" in result
        assert "AWS_SECRET_KEY" not in result
        assert "OPENAI_API_KEY" not in result

    def test_filters_secret_values(self) -> None:
        env = {
            "MY_CUSTOM_VAR": "ghp_abcdefghijklmnopqrstuvwxyz1234567890",
            "NORMAL_VAR": "hello",
        }
        result = sanitize_env(env)
        assert "MY_CUSTOM_VAR" not in result
        assert "NORMAL_VAR" in result

    def test_empty_env(self) -> None:
        assert sanitize_env({}) == {}
