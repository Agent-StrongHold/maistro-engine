"""Tests for GatewayClient — retry logic and error handling."""

from __future__ import annotations

import pytest
import respx
from httpx import Response, HTTPStatusError

from orchestrator.gateway_client import GatewayClient, GatewayError


@pytest.fixture
def client() -> GatewayClient:
    return GatewayClient("http://mock-gateway:9090", max_retries=3)


class TestRetryLogic:
    """Retry behavior tests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_retries_on_502(self, client: GatewayClient):
        """Should retry on 502 Bad Gateway."""
        route = respx.get("http://mock-gateway:9090/health")
        route.side_effect = [
            Response(502),
            Response(502),
            Response(200, json={"status": "ok"}),
        ]

        result = await client.health()
        assert result == {"status": "ok"}
        assert route.call_count == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_retries_on_503(self, client: GatewayClient):
        """Should retry on 503 Service Unavailable."""
        route = respx.get("http://mock-gateway:9090/health")
        route.side_effect = [
            Response(503),
            Response(200, json={"status": "ok"}),
        ]

        result = await client.health()
        assert result == {"status": "ok"}
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self, client: GatewayClient):
        """Should raise GatewayError after max retries exceeded."""
        respx.get("http://mock-gateway:9090/health").mock(
            return_value=Response(503)
        )

        with pytest.raises(GatewayError, match="failed after 3 attempts"):
            await client.health()

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_retry_on_400(self, client: GatewayClient):
        """Should not retry on client errors (4xx)."""
        route = respx.post("http://mock-gateway:9090/v1/chat/completions")
        route.mock(return_value=Response(400, json={"error": "bad request"}))

        with pytest.raises(HTTPStatusError):
            await client.chat([{"role": "user", "content": "hi"}])

        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_retry_on_404(self, client: GatewayClient):
        """Should not retry on 404 Not Found."""
        route = respx.get("http://mock-gateway:9090/health")
        route.mock(return_value=Response(404))

        with pytest.raises(HTTPStatusError):
            await client.health()

        assert route.call_count == 1


class TestSafeResponseParsing:
    """Safe response parsing tests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_empty_choices(self, client: GatewayClient):
        """Should raise GatewayError on empty choices array."""
        respx.post("http://mock-gateway:9090/v1/chat/completions").mock(
            return_value=Response(200, json={"choices": []})
        )

        with pytest.raises(GatewayError, match="Empty choices"):
            await client.chat([{"role": "user", "content": "hi"}])

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_missing_choices(self, client: GatewayClient):
        """Should raise GatewayError when choices key is missing."""
        respx.post("http://mock-gateway:9090/v1/chat/completions").mock(
            return_value=Response(200, json={})
        )

        with pytest.raises(GatewayError, match="Empty choices"):
            await client.chat([{"role": "user", "content": "hi"}])

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_valid_response(self, client: GatewayClient):
        """Should parse valid response correctly."""
        respx.post("http://mock-gateway:9090/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [{"message": {"content": "Hello!"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            )
        )

        result = await client.chat([{"role": "user", "content": "hi"}])
        assert result.content == "Hello!"
        assert result.usage["prompt_tokens"] == 10

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_missing_usage(self, client: GatewayClient):
        """Should handle missing usage gracefully."""
        respx.post("http://mock-gateway:9090/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": "Hello!"}}]},
            )
        )

        result = await client.chat([{"role": "user", "content": "hi"}])
        assert result.content == "Hello!"
        assert result.usage == {}


class TestUltraThink:
    """Ultra Think API tests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_ultra_think_request(self, client: GatewayClient):
        """Should send correct ultra-think request."""
        route = respx.post("http://mock-gateway:9090/v1/ultra-think").mock(
            return_value=Response(
                200,
                json={"task_id": "test", "candidates": [], "errors": []},
            )
        )

        result = await client.ultra_think(
            task_id="test-task",
            messages=[{"role": "user", "content": "test"}],
            project_id="test-project",
            tier=2,
        )

        assert route.called
        assert result["task_id"] == "test"


class TestProjectLoad:
    """Project loading tests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_load_project(self, client: GatewayClient):
        """Should load project context."""
        route = respx.post("http://mock-gateway:9090/v1/project/load").mock(
            return_value=Response(
                200,
                json={"project_id": "test", "cache_reused": False},
            )
        )

        result = await client.load_project(
            project_id="test",
            layer0_text="# Constraints",
        )

        assert route.called
        assert result["project_id"] == "test"
