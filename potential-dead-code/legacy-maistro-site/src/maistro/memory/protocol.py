"""Working memory protocol — DI interface for graph execution memory backends.

Callers inject a WorkingMemoryProtocol implementation; the graph executor and
optimizer never reference a concrete store directly.

Implementations
───────────────
ObsidianMemoryStore  — human-readable markdown files in an Obsidian vault.
                       Node configs are editable directly in Obsidian;
                       the optimizer picks up human corrections on the next run.
InMemoryStore        — in-process lists/dicts; no persistence; use for tests
                       and ephemeral single-run sessions.
PgVectorMemoryStore  — PostgreSQL + pgvector; production use with semantic
                       search over traces (wires into existing memory/store.py).

All methods are async so implementations can freely use async I/O (db calls,
asyncio.to_thread for file ops) without blocking the event loop.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from maistro.agents.types import AgentRole, HyperagentOutput, NodeConfig, OptimizationSignal


@runtime_checkable
class WorkingMemoryProtocol(Protocol):
    """Injectable backing store for graph execution state.

    The three capabilities that close the optimization loop:
      1. Trace persistence  — optimizer reads traces to compute gradient signal
      2. Signal persistence — next run's blackboard.optimization_history
      3. Node config store  — persists / loads optimized prompts per task type
    """

    async def save_trace(self, run_id: str, trace: HyperagentOutput) -> None:
        """Persist a completed execution trace."""
        ...

    async def load_traces(self, limit: int = 10) -> list[HyperagentOutput]:
        """Return the most recent traces, newest first."""
        ...

    async def save_signal(self, run_id: str, signal: OptimizationSignal) -> None:
        """Persist an optimization signal derived from a trace batch."""
        ...

    async def load_signals(self, limit: int = 5) -> list[OptimizationSignal]:
        """Return the most recent signals, newest first."""
        ...

    async def save_node_config(self, task_type: str, role: AgentRole, config: NodeConfig) -> None:
        """Persist an optimized NodeConfig (improved system prompt) for a task type.

        In Obsidian this becomes an editable markdown file; human edits are
        picked up transparently when load_node_configs is called next time.
        """
        ...

    async def load_node_configs(self, task_type: str) -> dict[AgentRole, NodeConfig]:
        """Return optimized NodeConfigs for the given task type, keyed by role.

        Returns an empty dict when no configs exist yet (first run).
        """
        ...
