"""`agent.synth_dag` — synthesize a DAG at runtime and execute it as a sub-graph.

An orchestrating node takes a natural-language objective, delegates to the
injected `DagSynthesizer` to produce a `GraphConfig`, then runs that config
as a sub-graph via `run_graph()`. This is the "deep agent" pattern: instead of
a pre-wired static topology, the node *writes* the graph at runtime based on
what the task requires.

With no `llm_call` injected the node synthesizes but skips execution (useful
for topology inspection and dry-run tests). With an `llm_call` the synthesized
DAG runs in-process and the result is returned.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from maistro.graph.synth import DagSynthesizer, RuleDagSynthesizer, SynthRequest

from . import register_node
from .base import BaseNode, NodeContext

_MAX_NODE_CEILING = 16  # aligns with fan_out.MAX_PARALLEL_CEILING


class SynthDagIn(BaseModel):
    objective: str = Field(description="What the synthesized DAG should accomplish")
    constraints: list[str] = Field(
        default_factory=list, description="Hard constraints on DAG structure"
    )
    available_kinds: list[str] = Field(
        default_factory=list, description="Node kinds the synthesizer may use"
    )
    max_nodes: int = Field(default=8, ge=2, le=_MAX_NODE_CEILING, description="Node count cap")


class SynthDagOut(BaseModel):
    success: bool = True
    synthesized_nodes: list[str] = Field(default_factory=list)
    rationale: str = ""
    run_output: str = ""
    error: str | None = None


@register_node
class AgentSynthDagNode(BaseNode[SynthDagIn, SynthDagOut]):
    """Synthesize a GraphConfig from an objective, then run it as a sub-graph."""

    kind: ClassVar[str] = "agent.synth_dag"
    kind_category: ClassVar = "composite"
    input_schema: ClassVar[type[BaseModel]] = SynthDagIn
    output_schema: ClassVar[type[BaseModel]] = SynthDagOut
    cost_hint: ClassVar[float] = 8.0
    idempotent: ClassVar[bool] = False
    external_io: ClassVar[bool] = False
    display_name: ClassVar[str] = "Agent: synthesize DAG"
    description: ClassVar[str] = (
        "Turn a natural-language objective into a GraphConfig at runtime, "
        "then execute the synthesized sub-graph."
    )

    def __init__(
        self,
        synthesizer: DagSynthesizer | None = None,
        llm_call: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        self._synthesizer: DagSynthesizer = synthesizer or RuleDagSynthesizer()
        self._llm_call = llm_call

    async def _execute(self, inputs: SynthDagIn, ctx: NodeContext) -> SynthDagOut:
        request = SynthRequest(
            objective=inputs.objective,
            constraints=inputs.constraints,
            available_kinds=inputs.available_kinds,
            max_nodes=inputs.max_nodes,
        )
        synth = await self._synthesizer.synthesize(request)
        synthesized_kinds = [str(n) for n in synth.graph_config.nodes]

        if self._llm_call is None:
            return SynthDagOut(
                success=True,
                synthesized_nodes=synthesized_kinds,
                rationale=synth.rationale,
                run_output="dag synthesized — no llm_call provided, execution skipped",
            )

        from maistro.graph.executor import run_graph
        from maistro.graph.types import GraphTask

        task = GraphTask(
            description=inputs.objective,
            workspace=str(ctx.run_id),
            graph_config=synth.graph_config,
        )
        output = await run_graph(task, self._llm_call)
        return SynthDagOut(
            success=output.success,
            synthesized_nodes=synthesized_kinds,
            rationale=synth.rationale,
            run_output=output.final_answer or "",
            error=None if output.success else "sub-graph execution failed",
        )
