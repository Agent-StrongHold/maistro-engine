from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from maistro.graph.node import NodeExecutor
from maistro.graph.run import GraphRun, evaluate_condition
from maistro.graph.types import (
    GraphConfig,
    GraphTask,
    HyperagentOutput,
)


def _ensure_node_configs(config: GraphConfig | None, parallel_generations: int) -> None:
    """Backfill a NodeConfig for every role, applying the beam width when the
    caller asked for parallel generations. Mutates ``config`` in place."""
    if config is None:
        return
    from maistro.graph.types import NodeConfig as _NC

    for role in config.nodes:
        if role not in config.node_configs:
            config.node_configs[role] = _NC(role=role)
        if parallel_generations > 1:
            config.node_configs[role].beam_width = parallel_generations


async def run_graph(
    task: GraphTask,
    llm_call: Callable[..., Awaitable[str]],
    *,
    model: str = "default",
    max_retries: int = 3,
    timeout: float = 120.0,
    initial_backoff: float = 1.0,
    parallel_generations: int = 1,
    temperature: float | None = None,
    run_id: str | None = None,
    event_callbacks: list[Callable[[Any], Awaitable[None]]] | None = None,
    node_executors: dict[str, NodeExecutor] | None = None,
) -> HyperagentOutput:
    from maistro.resilience.backoff import BackoffConfig

    backoff_config = BackoffConfig(base_delay=initial_backoff)

    config = task.graph_config
    _ensure_node_configs(config, parallel_generations)

    graph_run = GraphRun(
        run_id=run_id or "",
        task=task,
        config=config,
        event_callbacks=event_callbacks or [],
        node_executors=node_executors or {},
    )

    return await graph_run.start(
        llm_call,
        model=model,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        backoff_config=backoff_config,
    )


__all__ = ["GraphRun", "evaluate_condition", "run_graph"]
