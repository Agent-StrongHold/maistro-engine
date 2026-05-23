"""Graph runner — bridges hive-conductor DAGs to maistro-core graph executor.

Converts a DAGFile dict from the store into a GraphConfig, builds an
LLM callable from settings, and runs the graph.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from config import get_settings

logger = logging.getLogger(__name__)


async def execute_dag(dag_data: dict) -> dict[str, Any]:
    from maistro.graph.executor import run_graph
    from maistro.graph.types import (
        GraphBlackboard,
        GraphConfig,
        GraphEdge,
        NodeConfig,
    )

    nodes_cfg = {}
    for n in dag_data.get("nodes", []):
        nodes_cfg[n["id"]] = NodeConfig(
            role=n.get("role", "worker"),
            name=n.get("name", n["id"]),
            model=n.get("model"),
            system_prompt=n.get("prompt"),
            temperature=0.3,
            max_tokens=4096,
        )

    edges = []
    for e in dag_data.get("edges", []):
        edges.append(GraphEdge(
            from_node=e["from_node"],
            to_node=e.get("to_node"),
            condition=e.get("condition"),
        ))

    entry_node = dag_data.get("entry_node")
    if not entry_node and dag_data.get("nodes"):
        entry_node = dag_data["nodes"][0]["id"]

    config = GraphConfig(
        nodes=nodes_cfg,
        edges=edges,
        entry=entry_node or "",
        max_cycles=dag_data.get("max_cycles", 10),
        run_scout=dag_data.get("run_scout", False),
    )

    blackboard = GraphBlackboard(
        task_objective=dag_data.get("name", "Unnamed DAG"),
        workspace=dag_data.get("workspace", "/tmp/maistro-workspace"),  # nosec B108
    )

    llm_call = _build_llm_call()

    result = await run_graph(
        task=dag_data.get("description", dag_data.get("name", "")),
        config=config,
        blackboard=blackboard,
        llm_call=llm_call,
    )
    return {
        "status": "completed",
        "cycles": result.total_cycles,
        "node_results": {
            nr.node_id: {
                "role": nr.role,
                "response": nr.selected_candidate or "",
                "success": nr.success,
            }
            for nr in result.node_results
        },
        "annotations": dict(blackboard.node_annotations) if blackboard.node_annotations else {},
    }


def genome_to_dag(genome: Any) -> dict[str, Any]:
    """Convert an evolved PipelineGenome into a DAG dict for execute_dag."""
    nodes = []
    for n in genome.topology.nodes:
        nodes.append({
            "id": n.id,
            "name": f"{n.role}-{n.id[:6]}",
            "role": n.role,
            "model": n.model,
            "prompt": n.system_prompt,
            "strategy": n.strategy,
            "temperature": n.temperature,
            "max_tokens": n.max_tokens,
            "max_tool_rounds": n.max_tool_rounds,
        })

    edges = []
    for e in genome.topology.edges:
        edges.append({
            "id": e.id,
            "from_node": e.from_node,
            "to_node": e.to_node,
            "condition": e.condition,
        })

    return {
        "name": genome.name,
        "description": f"Evolved pipeline (gen={genome.generation}, fitness={genome.fitness_score})",
        "nodes": nodes,
        "edges": edges,
        "entry_node": genome.topology.entry_node,
        "max_cycles": genome.topology.max_cycles,
        "run_scout": genome.topology.use_scout,
        "genome_id": genome.id,
        "evolved": True,
    }


async def execute_champion() -> dict[str, Any]:
    """Run the current evolution champion's pipeline through the graph executor."""
    try:
        from services.evolution import get_evolution_service
        svc = get_evolution_service()
    except RuntimeError:
        return {"status": "error", "error": "evolution service not started"}

    if svc.population is None:
        return {"status": "error", "error": "population not initialized"}

    champion = svc.population.get_champion()
    if champion is None:
        return {"status": "error", "error": "no champion yet"}

    dag_data = genome_to_dag(champion)
    result = await execute_dag(dag_data)
    result["genome_id"] = champion.id
    result["fitness"] = champion.fitness_score
    result["generation"] = champion.generation
    return result


def _build_llm_call():
    settings = get_settings()
    base = settings.maistro_llm_base_url or settings.litellm_api_base
    key = settings.maistro_llm_api_key or settings.litellm_api_key

    if not base:
        async def _stub_llm(messages: list[dict], **kwargs: Any) -> str:
            return json.dumps({"response": "stub: no LLM configured", "done": True})
        return _stub_llm

    raw_key = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key) if key else ""

    async def _httpx_llm(messages: list[dict], **kwargs: Any) -> str:
        model = kwargs.get("model", settings.chat_default_model)
        temperature = kwargs.get("temperature", 0.3)
        max_tokens = kwargs.get("max_tokens", 4096)
        headers = {"Content-Type": "application/json"}
        if raw_key:
            headers["Authorization"] = f"Bearer {raw_key}"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{base}/v1/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    return _httpx_llm


async def execute_dag_streaming(dag_data: dict):
    """Yield progress events as the DAG executes, one per node completion."""
    from maistro.graph.executor import run_graph
    from maistro.graph.types import GraphBlackboard, GraphConfig, GraphEdge, NodeConfig

    nodes_cfg = {}
    for n in dag_data.get("nodes", []):
        nodes_cfg[n["id"]] = NodeConfig(
            role=n.get("role", "worker"),
            name=n.get("name", n["id"]),
            model=n.get("model"),
            system_prompt=n.get("prompt"),
            temperature=0.3,
            max_tokens=4096,
        )

    edges = []
    for e in dag_data.get("edges", []):
        edges.append(GraphEdge(
            from_node=e["from_node"],
            to_node=e.get("to_node"),
            condition=e.get("condition"),
        ))

    entry_node = dag_data.get("entry_node") or (dag_data["nodes"][0]["id"] if dag_data.get("nodes") else "")

    config = GraphConfig(
        nodes=nodes_cfg,
        edges=edges,
        entry=entry_node,
        max_cycles=dag_data.get("max_cycles", 10),
        run_scout=dag_data.get("run_scout", False),
    )

    blackboard = GraphBlackboard(
        task_objective=dag_data.get("name", "Unnamed DAG"),
        workspace=dag_data.get("workspace", "/tmp/maistro-workspace"),  # nosec B108
    )
    llm_call = _build_llm_call()

    yield {"status": "started", "node_count": len(nodes_cfg), "entry": entry_node}

    try:
        result = await run_graph(
            task=dag_data.get("description", dag_data.get("name", "")),
            config=config,
            blackboard=blackboard,
            llm_call=llm_call,
        )
        for nr in result.node_results:
            yield {
                "status": "node_complete",
                "node_id": nr.node_id,
                "role": nr.role,
                "response": nr.selected_candidate or "",
                "success": nr.success,
            }
        yield {
            "status": "completed",
            "cycles": result.total_cycles,
            "annotations": dict(blackboard.node_annotations) if blackboard.node_annotations else {},
        }
    except Exception as exc:
        yield {"status": "failed", "error": str(exc)}
