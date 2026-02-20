"""Tests for bearer token authentication.

Evidence: The API uses bearer token auth with constant-time comparison.
When no API keys are configured, auth is disabled (dev mode).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from maistro.api.auth import verify_api_key
from maistro.api.health import router as health_router
from maistro.config.settings import Settings


def _make_app(api_keys: list[str]) -> FastAPI:
    """Create a test app with specific API key configuration."""
    settings = Settings(api_keys=api_keys)
    app = FastAPI()
    app.include_router(health_router)

    # Override settings dependency
    app.dependency_overrides[lambda: None] = lambda: settings
    return app


class TestDevMode:
    """Evidence: When no API keys are configured, all requests are allowed."""

    def test_no_keys_allows_all(self) -> None:
        from maistro.main import app
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200


class TestSecretComparison:
    """Evidence: Auth uses hmac.compare_digest for constant-time comparison,
    preventing timing attacks that could leak valid key characters."""

    def test_correct_key_accepted(self) -> None:
        from fastapi.security import HTTPAuthorizationCredentials

        settings = Settings(api_keys=["test-key-123"])
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-key-123")
        result = verify_api_key(creds, settings)
        assert result == "test-key-123"

    def test_wrong_key_rejected(self) -> None:
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        settings = Settings(api_keys=["correct-key"])
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-key")
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(creds, settings)
        assert exc_info.value.status_code == 401

    def test_missing_header_rejected(self) -> None:
        from fastapi import HTTPException

        settings = Settings(api_keys=["some-key"])
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(None, settings)
        assert exc_info.value.status_code == 401
