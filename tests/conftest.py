"""Shared test fixtures and configuration."""

from __future__ import annotations

import os

import pytest

# Force dry-run mode in tests to avoid real LLM calls
os.environ.setdefault("MAISTRO_DRY_RUN", "1")

# High rate limits in tests to avoid 429s
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "6000")
os.environ.setdefault("RATE_LIMIT_BURST", "1000")


@pytest.fixture(autouse=True)
def _reset_singletons() -> None:
    """Reset global singletons between tests to prevent state leakage."""
    import maistro.tasks.queue as queue_module
    queue_module._queue = None

    # Clear cached settings so test env vars are picked up
    from maistro.config.settings import get_settings
    get_settings.cache_clear()


@pytest.fixture()
def task_queue():
    """Create a fresh TaskQueue instance for testing."""
    from maistro.tasks.queue import TaskQueue
    return TaskQueue()


@pytest.fixture()
def mock_executor():
    """Create a mock task executor that returns dry-run results."""
    from maistro.agents.types import ConductorOutput, PlanOutput, SubTask

    async def executor(task):
        return ConductorOutput(
            plan=PlanOutput(
                summary=f"[TEST] Plan for: {task.description}",
                subtasks=[SubTask(title="Test task", description=task.description)],
            ),
            final_answer=f"[TEST] Done: {task.description}",
            success=True,
        )
    return executor
