"""Tests for the SlotManager."""

from __future__ import annotations

import asyncio
import pytest
import respx
from httpx import Response

from gateway.config import GatewayConfig
from gateway.slot_manager import SlotManager
import httpx


@pytest.fixture
def config() -> GatewayConfig:
    return GatewayConfig(
        llama_server_url="http://mock-llama:8080",
        template_slot_id=0,
        worker_slot_ids=[1, 2, 3, 4],
    )


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


class TestSlotAcquisition:
    """Slot acquisition and release tests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_acquire_and_release_worker(self, config: GatewayConfig, client: httpx.AsyncClient):
        """Worker slots can be acquired and released."""
        mgr = SlotManager(config, client)

        assert mgr.available_count == 4

        slot_id = await mgr.acquire_worker("task-1")
        assert slot_id in [1, 2, 3, 4]
        assert mgr.available_count == 3

        mgr.release_worker(slot_id)
        assert mgr.available_count == 4

    @respx.mock
    @pytest.mark.asyncio
    async def test_acquire_all_slots(self, config: GatewayConfig, client: httpx.AsyncClient):
        """Should be able to acquire all worker slots."""
        mgr = SlotManager(config, client)

        slots = []
        for i in range(4):
            slot = await mgr.acquire_worker(f"task-{i}")
            slots.append(slot)

        assert mgr.available_count == 0
        assert set(slots) == {1, 2, 3, 4}

        # Release all
        for slot in slots:
            mgr.release_worker(slot)

        assert mgr.available_count == 4

    @respx.mock
    @pytest.mark.asyncio
    async def test_acquire_timeout(self, config: GatewayConfig, client: httpx.AsyncClient):
        """Should timeout if no slots available."""
        config.generation_timeout_seconds = 0.1  # Short timeout for test
        mgr = SlotManager(config, client)

        # Acquire all slots
        for i in range(4):
            await mgr.acquire_worker(f"task-{i}")

        # Try to acquire another - should timeout
        with pytest.raises(RuntimeError, match="No worker slot available"):
            await mgr.acquire_worker("task-extra", timeout=0.1)


class TestSlotProtection:
    """Template slot protection tests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_slot_0_cannot_be_released(self, config: GatewayConfig, client: httpx.AsyncClient):
        """Template slot (0) should not be releasable as a worker."""
        mgr = SlotManager(config, client)

        with pytest.raises(ValueError, match="template slot"):
            mgr.release_worker(0)

    @respx.mock
    @pytest.mark.asyncio
    async def test_restore_to_template_slot_raises(self, config: GatewayConfig, client: httpx.AsyncClient):
        """Cannot restore into the template slot itself."""
        mgr = SlotManager(config, client)

        with pytest.raises(ValueError, match="template slot"):
            await mgr.restore_template_to_worker("test-project", 0)


class TestSlotAPICalls:
    """Tests for llama-server API interactions."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_save_template_calls_llama_api(self, config: GatewayConfig, client: httpx.AsyncClient):
        """save_template should POST to /slots/0?action=save."""
        route = respx.post("http://mock-llama:8080/slots/0?action=save").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        mgr = SlotManager(config, client)
        elapsed = await mgr.save_template("test-project")

        assert route.called
        assert elapsed > 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_restore_template_to_worker(self, config: GatewayConfig, client: httpx.AsyncClient):
        """restore_template_to_worker should POST to /slots/{worker}?action=restore."""
        route = respx.post("http://mock-llama:8080/slots/2?action=restore").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        mgr = SlotManager(config, client)
        elapsed = await mgr.restore_template_to_worker("test-project", 2)

        assert route.called
        assert elapsed > 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_save_template_handles_error(self, config: GatewayConfig, client: httpx.AsyncClient):
        """save_template should propagate errors."""
        respx.post("http://mock-llama:8080/slots/0?action=save").mock(
            return_value=Response(500, json={"error": "internal error"})
        )

        mgr = SlotManager(config, client)

        with pytest.raises(httpx.HTTPStatusError):
            await mgr.save_template("test-project")
