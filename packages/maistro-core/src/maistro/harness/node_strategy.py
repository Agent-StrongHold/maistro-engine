"""Graph-node helper for outbound HarnessRunner execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from maistro.capabilities.registry import CapabilityRegistry
from maistro.capabilities.types import Unavailable
from maistro.graph.node import IterationBudget, NodeRun
from maistro.graph.phases import NodePhase
from maistro.types.config import AgentConfig


@dataclass
class HarnessNodeStrategy:
    registry: CapabilityRegistry
    agent_spec: AgentConfig
    workdir: str
    _sessions: dict[str, str] = field(default_factory=dict)

    async def execute(
        self,
        node_run: NodeRun,
        messages: list[dict[str, Any]],
        *,
        iteration_budget: IterationBudget | None = None,
    ) -> dict[str, Any] | Unavailable:
        if iteration_budget is not None and not iteration_budget.consume():
            unavailable = Unavailable("harness_runner", "iteration budget exhausted")
            _finish_unavailable(node_run, unavailable)
            return unavailable

        provider = await self.registry.resolve("harness_runner")
        if provider is None:
            unavailable = Unavailable("harness_runner")
            _finish_unavailable(node_run, unavailable)
            return unavailable

        runner = provider  # Protocol at runtime; tests assert shape.
        session_id = self._sessions.get(node_run.run_id)
        if session_id is None:
            session_id = await runner.start_session(self.agent_spec, workdir=self.workdir)  # type: ignore[attr-defined]
            self._sessions[node_run.run_id] = session_id

        node_run._transition(NodePhase.RUNNING)
        response = await runner.send(session_id, messages)  # type: ignore[attr-defined]
        node_run.raw_response = json.dumps(response, sort_keys=True)
        node_run.parsed_output = response
        node_run.score = 1.0
        node_run._transition(NodePhase.SUCCEEDED)
        return response


def _finish_unavailable(node_run: NodeRun, unavailable: Unavailable) -> None:
    node_run.raw_response = f"{unavailable.slot}: {unavailable.reason}"
    node_run.parsed_output = unavailable
    node_run.score = 0.0
    node_run._transition(NodePhase.FAILED)
