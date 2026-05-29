"""Tests for Ultra Think parallel generation."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from gateway.config import GatewayConfig
from gateway.slot_manager import SlotManager
from gateway.ultra_think import UltraThink
import httpx


@pytest.fixture
def config() -> GatewayConfig:
    return GatewayConfig(
        llama_server_url="http://mock-llama:8080",
        template_slot_id=0,
        worker_slot_ids=[1, 2, 3, 4],
        tier1_candidates=1,
        tier2_candidates=3,
        tier3_candidates=5,
    )


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


def mock_completion_response(content: str = "Hello, world!") -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }


class TestTierGeneration:
    """Tests for different tier candidate counts."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_tier2_generates_3_candidates(
        self, config: GatewayConfig, client: httpx.AsyncClient
    ):
        """Tier 2 should generate 3 diverse candidates."""
        for slot_id in [1, 2, 3]:
            respx.post(f"http://mock-llama:8080/slots/{slot_id}?action=restore").mock(
                return_value=Response(200, json={"status": "ok"})
            )

        respx.post("http://mock-llama:8080/v1/chat/completions").mock(
            return_value=Response(200, json=mock_completion_response("code here"))
        )

        slot_mgr = SlotManager(config, client)
        ultra = UltraThink(config, slot_mgr, client)

        result = await ultra.generate(
            task_id="test-task",
            messages=[{"role": "user", "content": "Write a hello world"}],
            project_id="test-project",
            tier=2,
        )

        assert result.task_id == "test-task"
        assert result.tier == 2
        assert len(result.candidates) == 3
        assert result.timing.total_ms > 0
        assert slot_mgr.available_count == 4  # All slots released

    @respx.mock
    @pytest.mark.asyncio
    async def test_tier1_generates_1_candidate(
        self, config: GatewayConfig, client: httpx.AsyncClient
    ):
        """Tier 1 should generate only 1 candidate."""
        respx.post("http://mock-llama:8080/slots/1?action=restore").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        respx.post("http://mock-llama:8080/v1/chat/completions").mock(
            return_value=Response(200, json=mock_completion_response())
        )

        slot_mgr = SlotManager(config, client)
        ultra = UltraThink(config, slot_mgr, client)

        result = await ultra.generate(
            task_id="simple-task",
            messages=[{"role": "user", "content": "Fix typo"}],
            project_id="test-project",
            tier=1,
        )

        assert len(result.candidates) == 1
        assert slot_mgr.available_count == 4


class TestErrorHandling:
    """Tests for error handling and slot cleanup."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_generation_failure(
        self, config: GatewayConfig, client: httpx.AsyncClient
    ):
        """Should handle generation failure and still release slots."""
        # Restore succeeds
        for slot_id in [1, 2, 3]:
            respx.post(f"http://mock-llama:8080/slots/{slot_id}?action=restore").mock(
                return_value=Response(200, json={"status": "ok"})
            )

        # Generation fails
        respx.post("http://mock-llama:8080/v1/chat/completions").mock(
            return_value=Response(500, json={"error": "server error"})
        )

        slot_mgr = SlotManager(config, client)
        ultra = UltraThink(config, slot_mgr, client)

        result = await ultra.generate(
            task_id="failing-task",
            messages=[{"role": "user", "content": "test"}],
            project_id="test-project",
            tier=2,
        )

        # Should have errors recorded
        assert len(result.errors) == 3
        assert len(result.candidates) == 0
        # Slots should still be released
        assert slot_mgr.available_count == 4

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_partial_failure(self, config: GatewayConfig, client: httpx.AsyncClient):
        """Should handle partial generation failure."""
        for slot_id in [1, 2, 3]:
            respx.post(f"http://mock-llama:8080/slots/{slot_id}?action=restore").mock(
                return_value=Response(200, json={"status": "ok"})
            )

        # First two succeed, third fails
        completion_route = respx.post("http://mock-llama:8080/v1/chat/completions")
        completion_route.side_effect = [
            Response(200, json=mock_completion_response("result 1")),
            Response(200, json=mock_completion_response("result 2")),
            Response(500, json={"error": "server error"}),
        ]

        slot_mgr = SlotManager(config, client)
        ultra = UltraThink(config, slot_mgr, client)

        result = await ultra.generate(
            task_id="partial-task",
            messages=[{"role": "user", "content": "test"}],
            project_id="test-project",
            tier=2,
        )

        assert len(result.candidates) == 2
        assert len(result.errors) == 1
        assert slot_mgr.available_count == 4


class TestDiversity:
    """Tests for candidate diversity."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_candidates_have_different_ids(
        self, config: GatewayConfig, client: httpx.AsyncClient
    ):
        """Each candidate should have a unique ID."""
        for slot_id in [1, 2, 3]:
            respx.post(f"http://mock-llama:8080/slots/{slot_id}?action=restore").mock(
                return_value=Response(200, json={"status": "ok"})
            )

        respx.post("http://mock-llama:8080/v1/chat/completions").mock(
            return_value=Response(200, json=mock_completion_response())
        )

        slot_mgr = SlotManager(config, client)
        ultra = UltraThink(config, slot_mgr, client)

        result = await ultra.generate(
            task_id="test-task",
            messages=[{"role": "user", "content": "test"}],
            project_id="test-project",
            tier=2,
        )

        candidate_ids = [c.candidate_id for c in result.candidates]
        assert len(set(candidate_ids)) == len(candidate_ids)  # All unique
