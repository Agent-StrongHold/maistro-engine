"""Shared test fixtures and configuration."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _reset_singletons() -> Iterator[None]:
    """Reset all global singletons between tests to prevent state leakage."""
    yield

    # Task queue
    import maistro.tasks.queue as queue_module
    queue_module._queue = None

    # Sandbox containers
    import maistro.tools.sandbox.server as sandbox_server
    sandbox_server._containers.clear()

    # Langfuse tracing
    import maistro.observability.tracing as tracing_module
    tracing_module._langfuse = None

    # Task runner
    import maistro.main as main_module
    main_module._runner = None
