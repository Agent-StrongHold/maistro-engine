"""Shared test fixtures and configuration."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_task_queue() -> None:
    """Reset the global task queue between tests to prevent state leakage."""
    import maistro.tasks.queue as queue_module
    queue_module._queue = None
