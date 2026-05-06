"""In-process memory store — no persistence, use for tests and ephemeral runs."""

from __future__ import annotations

from maistro.agents.types import AgentRole, HyperagentOutput, NodeConfig, OptimizationSignal


class InMemoryStore:
    """WorkingMemoryProtocol backed by plain Python lists and dicts.

    Thread-safe for single-event-loop use (all mutations happen in async
    context; no locking needed for asyncio-only callers).
    """

    def __init__(self) -> None:
        self._traces: list[tuple[str, HyperagentOutput]] = []  # (run_id, trace)
        self._signals: list[tuple[str, OptimizationSignal]] = []  # (run_id, signal)
        self._node_configs: dict[str, dict[AgentRole, NodeConfig]] = {}  # task_type → configs

    async def save_trace(self, run_id: str, trace: HyperagentOutput) -> None:
        self._traces.append((run_id, trace))

    async def load_traces(self, limit: int = 10) -> list[HyperagentOutput]:
        return [t for _, t in self._traces[-limit:]][::-1]

    async def save_signal(self, run_id: str, signal: OptimizationSignal) -> None:
        self._signals.append((run_id, signal))

    async def load_signals(self, limit: int = 5) -> list[OptimizationSignal]:
        return [s for _, s in self._signals[-limit:]][::-1]

    async def save_node_config(
        self, task_type: str, role: AgentRole, config: NodeConfig
    ) -> None:
        self._node_configs.setdefault(task_type, {})[role] = config

    async def load_node_configs(self, task_type: str) -> dict[AgentRole, NodeConfig]:
        return dict(self._node_configs.get(task_type, {}))

    # --- Test helpers ---------------------------------------------------------

    def trace_count(self) -> int:
        return len(self._traces)

    def last_signal(self) -> OptimizationSignal | None:
        return self._signals[-1][1] if self._signals else None

    def clear(self) -> None:
        self._traces.clear()
        self._signals.clear()
        self._node_configs.clear()
