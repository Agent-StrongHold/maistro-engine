from __future__ import annotations

from typing import Any

from .types import EvalResult, PipelineGenome


def extract_signal(
    genome: PipelineGenome,
    eval_results: list[EvalResult],
) -> dict[str, Any]:
    if not eval_results:
        return {"weakest_benchmark": None, "score": 0.0, "suggestion": "no eval results"}

    worst = min(eval_results, key=lambda r: r.score)
    weakest_node_id: str | None = None
    if genome.topology.nodes:
        worst_node = min(
            genome.topology.nodes,
            key=lambda n: genome.eval_scores.get("ifeval", 0.5) if n.role == "queen" else 0.5,
        )
        weakest_node_id = worst_node.id

    return {
        "weakest_benchmark": worst.benchmark,
        "score": worst.score,
        "suggestion": f"Improve {worst.benchmark} performance (current: {worst.score:.3f})",
        "weakest_node_id": weakest_node_id,
    }


async def optimize_prompt(
    genome: PipelineGenome,
    weakest_node_id: str,
    signal: dict[str, Any],
    llm_call: Any = None,
) -> str:
    target_node = None
    for n in genome.topology.nodes:
        if n.id == weakest_node_id:
            target_node = n
            break
    if target_node is None:
        return genome.topology.nodes[0].system_prompt if genome.topology.nodes else ""

    meta_prompt = (
        f"You are an expert at optimizing AI agent system prompts.\n"
        f"The agent scored {signal.get('score', 0):.3f} on {signal.get('weakest_benchmark', 'unknown')}.\n"
        f"Suggestion: {signal.get('suggestion', '')}\n"
        f"Current prompt:\n{target_node.system_prompt}\n\n"
        f"Return an improved system prompt that addresses the weakness."
    )

    if llm_call is not None:
        try:
            result = await llm_call(meta_prompt)
            return result
        except Exception:
            pass

    return target_node.system_prompt.rstrip() + " Focus on accuracy and completeness."


async def optimize_topology(
    genome: PipelineGenome,
    signal: dict[str, Any],
    llm_call: Any = None,
) -> dict[str, Any]:
    meta_prompt = (
        f"You are an expert at optimizing AI agent pipeline topologies.\n"
        f"The pipeline scored {signal.get('score', 0):.3f} on {signal.get('weakest_benchmark', 'unknown')}.\n"
        f"Current topology has {len(genome.topology.nodes)} nodes and {len(genome.topology.edges)} edges.\n"
        f"Entry node strategy: {genome.topology.nodes[0].strategy if genome.topology.nodes else 'none'}\n"
        f"Suggestion: {signal.get('suggestion', '')}\n\n"
        f"Suggest topology improvements as JSON: "
        f'{{"add_node": {{"role": "...", "strategy": "..."}}, "remove_node_id": "...", "reason": "..."}}'
    )

    if llm_call is not None:
        try:
            result = await llm_call(meta_prompt)
            return {"suggestion": result, "source": "llm"}
        except Exception:
            pass

    return {
        "suggestion": f"Consider adding a scout node to improve {signal.get('weakest_benchmark', 'general')} performance.",
        "source": "heuristic",
    }
