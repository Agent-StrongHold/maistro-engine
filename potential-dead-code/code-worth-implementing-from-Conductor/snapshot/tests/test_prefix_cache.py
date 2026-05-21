"""Tests for the Prefix Cache Manager."""

from __future__ import annotations

import json
import pytest
import respx
from httpx import Response
from pathlib import Path

from gateway.config import GatewayConfig
from gateway.slot_manager import SlotManager
from gateway.prefix_cache import PrefixCacheManager
import httpx


@pytest.fixture
def config(tmp_path: Path) -> GatewayConfig:
    return GatewayConfig(
        llama_server_url="http://mock-llama:8080",
        template_slot_id=0,
        worker_slot_ids=[1, 2, 3, 4],
        kv_cache_dir=str(tmp_path / "kv-cache"),
    )


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


class TestCacheMiss:
    """Cache miss behavior tests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_cache_miss_computes_and_saves(
        self, config: GatewayConfig, client: httpx.AsyncClient
    ):
        """On cache miss, should compute prefix and save template."""
        respx.post("http://mock-llama:8080/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [{"message": {"content": ""}}],
                    "usage": {"prompt_tokens": 500},
                },
            )
        )
        respx.post("http://mock-llama:8080/slots/0?action=save").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        slot_mgr = SlotManager(config, client)
        cache = PrefixCacheManager(config, slot_mgr, client)

        reused = await cache.ensure_project_loaded(
            project_id="test-project",
            layer0_text="# Project Constraints\n\nBe excellent.",
        )

        assert reused is False

        meta_path = Path(config.kv_cache_dir) / "projects" / "test-project" / "template.meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["project_id"] == "test-project"
        assert meta["token_count"] == 500


class TestCacheHit:
    """Cache hit behavior tests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_cache_hit_skips_computation(
        self, config: GatewayConfig, client: httpx.AsyncClient
    ):
        """On cache hit (same content hash), should not recompute."""
        respx.post("http://mock-llama:8080/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": ""}}], "usage": {"prompt_tokens": 100}},
            )
        )
        respx.post("http://mock-llama:8080/slots/0?action=save").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        slot_mgr = SlotManager(config, client)
        cache = PrefixCacheManager(config, slot_mgr, client)

        layer0 = "# Constraints\n\nTest content."
        await cache.ensure_project_loaded("proj", layer0)

        respx.reset()

        reused = await cache.ensure_project_loaded("proj", layer0)
        assert reused is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_content_change_triggers_recompute(
        self, config: GatewayConfig, client: httpx.AsyncClient
    ):
        """Changed content should trigger recomputation."""
        respx.post("http://mock-llama:8080/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": ""}}], "usage": {"prompt_tokens": 100}},
            )
        )
        respx.post("http://mock-llama:8080/slots/0?action=save").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        slot_mgr = SlotManager(config, client)
        cache = PrefixCacheManager(config, slot_mgr, client)

        # First load
        await cache.ensure_project_loaded("proj", "Original content")

        # Second load with different content
        reused = await cache.ensure_project_loaded("proj", "Modified content")
        assert reused is False  # Should recompute


class TestInvalidation:
    """Cache invalidation tests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_invalidate_forces_recompute(
        self, config: GatewayConfig, client: httpx.AsyncClient
    ):
        """After invalidation, should recompute even with same content."""
        respx.post("http://mock-llama:8080/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": ""}}], "usage": {"prompt_tokens": 100}},
            )
        )
        respx.post("http://mock-llama:8080/slots/0?action=save").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        slot_mgr = SlotManager(config, client)
        cache = PrefixCacheManager(config, slot_mgr, client)

        layer0 = "# Constraints"
        await cache.ensure_project_loaded("proj", layer0)

        cache.invalidate("proj")

        reused = await cache.ensure_project_loaded("proj", layer0)
        assert reused is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_project(
        self, config: GatewayConfig, client: httpx.AsyncClient
    ):
        """Invalidating nonexistent project should not raise."""
        slot_mgr = SlotManager(config, client)
        cache = PrefixCacheManager(config, slot_mgr, client)

        # Should not raise
        cache.invalidate("nonexistent-project")
