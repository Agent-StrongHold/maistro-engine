from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DAGEdgeGenome(BaseModel):
    id: str
    from_node: str
    to_node: str | None
    condition: str | None


class NodeGenome(BaseModel):
    id: str
    role: str
    strategy: str
    model: str
    temperature: float
    max_tokens: int
    system_prompt: str
    max_tool_rounds: int


class DAGTopology(BaseModel):
    nodes: list[NodeGenome]
    edges: list[DAGEdgeGenome]
    entry_node: str
    max_cycles: int
    beam_width: int
    use_scout: bool


class EvalWeights(BaseModel):
    ifeval: float = 0.15
    bfcl: float = 0.15
    swebench: float = 0.20
    terminalbench: float = 0.10
    tau_bench: float = 0.15
    gaia: float = 0.10
    ragas: float = 0.10
    osworld: float = 0.05


class PipelineGenome(BaseModel):
    id: str
    name: str
    topology: DAGTopology
    eval_weights: EvalWeights
    harness_params: dict[str, Any] = {}
    fitness_score: float | None = None
    eval_scores: dict[str, float] = {}
    generation: int = 0
    parent_a_id: str | None = None
    parent_b_id: str | None = None
    created_at: str
    updated_at: str
    # RSI safety: promotion to live traffic requires an explicit human
    # approval gate (set externally, e.g. via human.approve_draft) — winning
    # tournament/fitness evaluation alone never sets this. Defaults closed.
    approved_for_promotion: bool = False
    # Set by PopulationStore.promote(); tracks which genome is currently
    # serving live traffic, and what to roll back to if it regresses.
    is_active: bool = False
    rollback_target_id: str | None = None


class EvalResult(BaseModel):
    benchmark: str
    score: float
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    samples_evaluated: int = 0
    metadata: dict[str, Any] = {}


class FitnessComponents(BaseModel):
    weighted_eval_score: float
    cost_efficiency: float
    latency_efficiency: float
    diversity_bonus: float
    total: float
    passed_hard_gate: bool
    gate_failures: list[str] = []
