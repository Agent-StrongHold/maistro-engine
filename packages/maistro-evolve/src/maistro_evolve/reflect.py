"""Reflective prompt evolution for the self-improve step.

Adopts the conceptual ideas of GEPA (reflective prompt evolution) and
MIPROv2 (grounded instruction proposal) without taking a DSPy dependency:

- GEPA: re-run the weakest benchmark to collect per-sample failure traces,
  have the LLM reflect on those traces to rewrite a single node's prompt,
  and only accept a candidate that verifiably scores better. Accepted
  candidates enter the population as children (lineage preserved) instead
  of overwriting the parent in place.
- MIPROv2: ground the proposal meta-prompt in a program (topology) summary
  and a benchmark summary, and diversify candidates with randomized
  proposal tips, evaluating each candidate against the metric before
  acceptance.

Per SPEC-202 signal honesty, candidates verified only by stub benchmark
scores are never accepted — optimizing against noise is not improvement.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from .harness import EvalHarness
from .types import NodeGenome, PipelineGenome

# MIPROv2-style grounding: describe what each benchmark measures so the
# proposal targets the skill, not the benchmark name.
BENCHMARK_SUMMARIES: dict[str, str] = {
    "ifeval": (
        "instruction following — satisfy explicit constraints "
        "(word counts, keywords, format, casing) exactly"
    ),
    "bfcl": (
        "function calling — choose the right tool and emit a well-formed "
        "call with correct arguments"
    ),
    "swebench": "software engineering — localize and patch repository bugs so tests pass",
    "terminalbench": "terminal use — solve tasks with correct shell commands",
    "tau_bench": "tool-agent dialogues — follow domain policy while using tools across turns",
    "gaia": "general assistant reasoning — multi-step questions requiring planning and precision",
    "ragas": "retrieval-augmented generation — ground answers in provided context only",
    "osworld": "OS/GUI control — translate goals into correct desktop interactions",
}

# MIPROv2-style proposal tips: a different tip per candidate diversifies the
# search instead of asking the same meta-question k times.
PROPOSAL_TIPS: list[str] = [
    "State output-format constraints explicitly and place them at the end of the prompt.",
    "Be concise: remove vague filler and keep only directives that change behavior.",
    "Add a short step-by-step procedure the agent must follow before answering.",
    "Add a final self-check instruction to re-verify every constraint before responding.",
    "Rephrase the role and goal to be sharper and more specific to the failing task type.",
]

_MAX_FEEDBACK_ENTRIES = 5


class ReflectionOutcome(BaseModel):
    benchmark: str
    target_node_id: str
    baseline_score: float
    candidate_count: int = 0
    best_candidate_score: float | None = None
    accepted: bool = False
    challenger_id: str | None = None
    reason: str | None = None
    challenger: PipelineGenome | None = None

    def summary(self) -> dict[str, Any]:
        return self.model_dump(exclude={"challenger"})


def summarize_topology(genome: PipelineGenome) -> str:
    nodes = ", ".join(
        f"{n.role}/{n.strategy}({n.model}, t={n.temperature})" for n in genome.topology.nodes
    )
    return (
        f"{len(genome.topology.nodes)} node(s), {len(genome.topology.edges)} edge(s), "
        f"entry={genome.topology.entry_node}; nodes: {nodes}"
    )


def summarize_failures(metadata: dict[str, Any], max_entries: int = _MAX_FEEDBACK_ENTRIES) -> str:
    failures = metadata.get("failures") or []
    lines: list[str] = []
    for entry in failures[:max_entries]:
        instruction = entry.get("instruction", "")
        failed_rules = ", ".join(entry.get("failed_rules", []))
        excerpt = entry.get("response_excerpt", "")
        line = f"- task: {instruction}"
        if failed_rules:
            line += f"\n  violated: {failed_rules}"
        if excerpt:
            line += f"\n  response excerpt: {excerpt}"
        lines.append(line)
    return "\n".join(lines)


def build_reflection_prompt(
    genome: PipelineGenome,
    node: NodeGenome,
    benchmark: str,
    score: float,
    failure_feedback: str,
    tip: str,
) -> str:
    bench_summary = BENCHMARK_SUMMARIES.get(benchmark, benchmark)
    parts = [
        "You are improving the system prompt of one node in an AI agent pipeline.",
        f"Pipeline: {summarize_topology(genome)}",
        f"Target node: {node.role}/{node.strategy} (model={node.model})",
        f"Weakest benchmark: {benchmark} ({bench_summary}). Current score: {score:.3f}.",
    ]
    if failure_feedback:
        parts.append(f"Observed failures on this benchmark:\n{failure_feedback}")
    parts.append(f"Current system prompt:\n{node.system_prompt}")
    parts.append(
        "First diagnose why this prompt produces the failures above, then write an "
        f"improved system prompt that fixes them. Tip: {tip}\n"
        "Return ONLY the new system prompt text, with no commentary."
    )
    return "\n\n".join(parts)


async def propose_candidates(
    genome: PipelineGenome,
    node: NodeGenome,
    benchmark: str,
    score: float,
    failure_feedback: str,
    llm_call: Any,
    num_candidates: int,
) -> list[str]:
    if num_candidates <= len(PROPOSAL_TIPS):
        tips = random.sample(PROPOSAL_TIPS, num_candidates)
    else:
        tips = PROPOSAL_TIPS + [
            random.choice(PROPOSAL_TIPS) for _ in range(num_candidates - len(PROPOSAL_TIPS))
        ]

    candidates: list[str] = []
    for tip in tips:
        meta_prompt = build_reflection_prompt(genome, node, benchmark, score, failure_feedback, tip)
        try:
            raw = await llm_call(meta_prompt)
        except Exception:
            continue
        text = str(raw).strip()
        if text and text != node.system_prompt and text not in candidates:
            candidates.append(text)
    return candidates


def spawn_challenger(genome: PipelineGenome, node_id: str, new_prompt: str) -> PipelineGenome:
    child = genome.model_copy(deep=True)
    now = datetime.now(UTC).isoformat()
    child.id = uuid.uuid4().hex[:12]
    child.name = f"reflect-{genome.id[:6]}"
    child.generation = genome.generation + 1
    child.parent_a_id = genome.id
    child.parent_b_id = None
    child.fitness_score = None
    child.eval_scores = {}
    child.harness_params = {"origin": "reflective_improve"}
    child.created_at = now
    child.updated_at = now
    for node in child.topology.nodes:
        if node.id == node_id:
            node.system_prompt = new_prompt
            break
    return child


def _target_node(genome: PipelineGenome) -> NodeGenome:
    # Benchmarks execute the entry node's prompt (see benchmarks.prompt_builder),
    # so that is the node whose prompt a weak score reflects.
    for node in genome.topology.nodes:
        if node.id == genome.topology.entry_node:
            return node
    return genome.topology.nodes[0]


def _weakest_benchmark(genome: PipelineGenome, benchmarks: list[str] | None) -> str | None:
    scores = {
        bench: score
        for bench, score in genome.eval_scores.items()
        if benchmarks is None or bench in benchmarks
    }
    if not scores:
        return None
    return min(scores.items(), key=lambda kv: kv[1])[0]


async def reflective_improve(
    genome: PipelineGenome,
    harness: EvalHarness,
    llm_call: Any,
    *,
    benchmarks: list[str] | None = None,
    num_candidates: int = 2,
    accept_margin: float = 0.0,
) -> ReflectionOutcome | None:
    if llm_call is None or not genome.topology.nodes:
        return None

    weakest = _weakest_benchmark(genome, benchmarks)
    if weakest is None:
        return None
    node = _target_node(genome)

    # Fresh rollout on the weakest benchmark: gives an up-to-date baseline
    # score plus the per-sample failure traces the reflection feeds on.
    baseline_results = await harness.evaluate_genome(genome, [weakest], llm_call)
    if not baseline_results:
        return None
    baseline = baseline_results[0]

    if baseline.metadata.get("stub"):
        return ReflectionOutcome(
            benchmark=weakest,
            target_node_id=node.id,
            baseline_score=baseline.score,
            reason="stub_signal",
        )

    feedback = summarize_failures(baseline.metadata)
    candidates = await propose_candidates(
        genome, node, weakest, baseline.score, feedback, llm_call, num_candidates
    )

    best_challenger: PipelineGenome | None = None
    best_score: float | None = None
    for text in candidates:
        challenger = spawn_challenger(genome, node.id, text)
        results = await harness.evaluate_genome(challenger, [weakest], llm_call)
        if not results:
            continue
        score = results[0].score
        challenger.eval_scores[weakest] = score
        challenger.harness_params["total_cost_usd"] = results[0].cost_usd
        if best_score is None or score > best_score:
            best_score = score
            best_challenger = challenger

    accepted = (
        best_score is not None
        and best_challenger is not None
        and best_score > baseline.score + accept_margin
    )
    return ReflectionOutcome(
        benchmark=weakest,
        target_node_id=node.id,
        baseline_score=baseline.score,
        candidate_count=len(candidates),
        best_candidate_score=best_score,
        accepted=accepted,
        challenger_id=best_challenger.id if accepted and best_challenger else None,
        reason=None if accepted else "no_candidate_beat_baseline",
        challenger=best_challenger if accepted else None,
    )
