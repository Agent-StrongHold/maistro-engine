"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest
import httpx
from pathlib import Path

from gateway.config import GatewayConfig


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def http_client():
    """Shared async HTTP client fixture with proper cleanup."""
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def gateway_config(tmp_path: Path) -> GatewayConfig:
    """Standard gateway config for testing."""
    return GatewayConfig(
        llama_server_url="http://mock-llama:8080",
        template_slot_id=0,
        worker_slot_ids=[1, 2, 3, 4],
        kv_cache_dir=str(tmp_path / "kv-cache"),
        tier1_candidates=1,
        tier2_candidates=3,
        tier3_candidates=5,
    )


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project = tmp_path / "project"
    project.mkdir()
    return project
