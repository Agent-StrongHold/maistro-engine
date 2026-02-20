"""Shared test fixtures and configuration."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _reset_task_queue() -> None:
    """Reset the global task queue between tests to prevent state leakage."""
    import maistro.tasks.queue as queue_module
    queue_module._queue = None


@pytest.fixture(autouse=True)
def _disable_auth_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable auth requirement for tests (unless test explicitly configures it)."""
    monkeypatch.setenv("REQUIRE_AUTH", "false")
