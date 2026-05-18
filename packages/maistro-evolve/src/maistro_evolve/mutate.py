from __future__ import annotations

import random
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from .types import (
    DAGEdgeGenome,
    EvalWeights,
    NodeGenome,
    PipelineGenome,
)

MODEL_REGISTRY = [
    "cerebras-qwen-3-235b-a22b-2507",
    "gpt-4o",
    "claude-sonnet-4-20250514",
    "gemini-2.5-pro",
    "mistral-large",
    "gemini-2.5-flash",
]

STRATEGY_LIST = ["react", "plan_execute", "direct", "delegate"]

PROMPT_VARIATIONS = [
    "Think step by step before answering.",
    "Be concise and direct.",
    "Verify your reasoning before concluding.",
    "Consider edge cases.",
    "Prioritize accuracy over speed.",
]


def _fresh_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def mutate_topology(genome: PipelineGenome, rate: float) -> PipelineGenome:
    topo = deepcopy(genome.topology)
    if random.random() < rate and len(topo.nodes) > 1:
        removable = [n for n in topo.nodes if n.id != topo.entry_node]
        if removable:
            victim = random.choice(removable)
            topo.nodes = [n for n in topo.nodes if n.id != victim.id]
            topo.edges = [
                e for e in topo.edges
                if e.from_node != victim.id and e.to_node != victim.id
            ]

    if random.random() < rate:
        new_node = NodeGenome(
            id=_new_id(),
            role=random.choice(["worker", "scout", "drone"]),
            strategy=random.choice(STRATEGY_LIST),
            model=random.choice(MODEL_REGISTRY),
            temperature=round(random.uniform(0.0, 1.0), 2),
            max_tokens=random.choice([256, 512, 1024, 2048, 4096, 8192, 16384]),
            system_prompt="You are a helpful assistant.",
            max_tool_rounds=random.randint(1, 20),
        )
        topo.nodes.append(new_node)
        source = random.choice([n.id for n in topo.nodes])
        topo.edges.append(
            DAGEdgeGenome(
                id=_new_id(),
                from_node=source,
                to_node=new_node.id,
                condition=None,
            )
        )

    if random.random() < rate and topo.edges:
        idx = random.randint(0, len(topo.edges) - 1)
        topo.edges.pop(idx)

    if random.random() < rate and topo.nodes:
        a = random.choice(topo.nodes)
        b_candidates = [n for n in topo.nodes if n.id != a.id]
        if b_candidates:
            b = random.choice(b_candidates)
            topo.edges.append(
                DAGEdgeGenome(
                    id=_new_id(),
                    from_node=a.id,
                    to_node=b.id,
                    condition=random.choice([None, "success", "failure", "timeout"]),
                )
            )

    return PipelineGenome(
        id=_new_id(),
        name=genome.name + "-topo-mut",
        topology=topo,
        eval_weights=deepcopy(genome.eval_weights),
        harness_params=deepcopy(genome.harness_params),
        fitness_score=None,
        eval_scores={},
        generation=genome.generation,
        parent_a_id=genome.id,
        parent_b_id=None,
        created_at=_fresh_timestamp(),
        updated_at=_fresh_timestamp(),
    )


def mutate_node(genome: PipelineGenome, rate: float) -> PipelineGenome:
    topo = deepcopy(genome.topology)
    for node in topo.nodes:
        if random.random() < rate:
            node.model = random.choice(MODEL_REGISTRY)
        if random.random() < rate:
            node.temperature = round(max(0.0, min(1.0, node.temperature + random.gauss(0, 0.15))), 2)
        if random.random() < rate:
            node.max_tokens = random.choice([256, 512, 1024, 2048, 4096, 8192, 16384])
        if random.random() < rate:
            node.strategy = random.choice(STRATEGY_LIST)
        if random.random() < rate:
            node.max_tool_rounds = random.randint(1, 20)
    return PipelineGenome(
        id=_new_id(),
        name=genome.name + "-node-mut",
        topology=topo,
        eval_weights=deepcopy(genome.eval_weights),
        harness_params=deepcopy(genome.harness_params),
        fitness_score=None,
        eval_scores={},
        generation=genome.generation,
        parent_a_id=genome.id,
        parent_b_id=None,
        created_at=_fresh_timestamp(),
        updated_at=_fresh_timestamp(),
    )


def mutate_prompt(genome: PipelineGenome, rate: float) -> PipelineGenome:
    topo = deepcopy(genome.topology)
    for node in topo.nodes:
        if random.random() < rate:
            variation = random.choice(PROMPT_VARIATIONS)
            node.system_prompt = node.system_prompt.rstrip() + " " + variation
        if random.random() < rate:
            sentences = node.system_prompt.split(". ")
            if len(sentences) > 2:
                sentences.pop(random.randint(0, len(sentences) - 1))
                node.system_prompt = ". ".join(sentences)
    return PipelineGenome(
        id=_new_id(),
        name=genome.name + "-prompt-mut",
        topology=topo,
        eval_weights=deepcopy(genome.eval_weights),
        harness_params=deepcopy(genome.harness_params),
        fitness_score=None,
        eval_scores={},
        generation=genome.generation,
        parent_a_id=genome.id,
        parent_b_id=None,
        created_at=_fresh_timestamp(),
        updated_at=_fresh_timestamp(),
    )


def mutate_eval_weights(genome: PipelineGenome, rate: float) -> PipelineGenome:
    if random.random() > rate:
        return PipelineGenome(
            id=_new_id(),
            name=genome.name + "-weight-mut",
            topology=deepcopy(genome.topology),
            eval_weights=deepcopy(genome.eval_weights),
            harness_params=deepcopy(genome.harness_params),
            fitness_score=None,
            eval_scores={},
            generation=genome.generation,
            parent_a_id=genome.id,
            parent_b_id=None,
            created_at=_fresh_timestamp(),
            updated_at=_fresh_timestamp(),
        )
    fields = EvalWeights.model_fields
    new_vals: dict[str, float] = {}
    for name in fields:
        current = getattr(genome.eval_weights, name)
        new_vals[name] = max(0.01, current + random.gauss(0, 0.03))
    total = sum(new_vals.values())
    for name in new_vals:
        new_vals[name] = round(new_vals[name] / total, 4)
    renorm_total = sum(new_vals.values())
    if renorm_total != 1.0:
        first_key = next(iter(new_vals))
        new_vals[first_key] = round(new_vals[first_key] + (1.0 - renorm_total), 4)
    return PipelineGenome(
        id=_new_id(),
        name=genome.name + "-weight-mut",
        topology=deepcopy(genome.topology),
        eval_weights=EvalWeights(**new_vals),
        harness_params=deepcopy(genome.harness_params),
        fitness_score=None,
        eval_scores={},
        generation=genome.generation,
        parent_a_id=genome.id,
        parent_b_id=None,
        created_at=_fresh_timestamp(),
        updated_at=_fresh_timestamp(),
    )


def mutate_all(genome: PipelineGenome, rate: float) -> PipelineGenome:
    current = mutate_topology(genome, rate)
    current = mutate_node(current, rate)
    current = mutate_prompt(current, rate)
    current = mutate_eval_weights(current, rate)
    current.name = genome.name + "-all-mut"
    return current
