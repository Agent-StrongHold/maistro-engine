from __future__ import annotations

from typing import Any

from maistro.graph.definitions import Edge, Graph, Node
from maistro.graph.types import AgentRole, GraphConfig, GraphEdge, NodeConfig


def _identifier(value: AgentRole | str) -> str:
    return value.value if isinstance(value, AgentRole) else str(value)


def _node_config(config: GraphConfig, node_id: str) -> NodeConfig | None:
    direct = config.node_configs.get(node_id)
    if direct is not None:
        return direct
    for key, value in config.node_configs.items():
        if _identifier(key) == node_id:
            return value
    return None


def _node_type(node_id: str, config: NodeConfig | None) -> str:
    if config is None:
        return node_id
    if config.kind:
        return config.kind
    if config.role:
        return _identifier(config.role)
    return node_id


def _parameters(config: NodeConfig | None) -> dict[str, Any]:
    if config is None:
        return {}
    return {
        "system_prompt": config.system_prompt,
        "temperature": config.temperature,
        "beam_width": config.beam_width,
        "model": config.model,
        "max_tokens": config.max_tokens,
    }


def _edge_metadata(edge: GraphEdge) -> dict[str, Any]:
    return {
        "legacy_graph_edge": {
            "parallel": edge.parallel,
            "weight": edge.weight,
            "trust": edge.trust,
            "sign": edge.sign,
            "staleness_decay_s": edge.staleness_decay_s,
        }
    }


def graph_config_to_graph(
    config: GraphConfig,
    *,
    graph_id: str | None = None,
    name: str = "Legacy Graph",
    description: str = "",
) -> Graph:
    """Project a legacy ``GraphConfig`` into the canonical definition model.

    This adapter is deliberately lossless rather than opinionated. Legacy
    ``kind`` values are preserved as ``Node.node_type`` when available, while
    the complete legacy node and graph configuration is retained in metadata.
    NodeType normalization can therefore happen later without discarding the
    source representation.

    ``GraphEdge.to_role is None`` is a legacy terminal sentinel rather than a
    real topology edge. Canonical ``Edge`` requires two real nodes, so terminal
    sentinels are preserved in graph metadata instead of being silently
    converted into invalid edges.
    """

    nodes: list[Node] = []
    node_ids: set[str] = set()

    for legacy_node in config.nodes:
        node_id = _identifier(legacy_node)
        node_ids.add(node_id)
        legacy_config = _node_config(config, node_id)
        metadata: dict[str, Any] = {"legacy_node_id": node_id}
        if legacy_config is not None:
            metadata["legacy_node_config"] = legacy_config.model_dump(mode="json")

        nodes.append(
            Node(
                node_id=node_id,
                node_type=_node_type(node_id, legacy_config),
                name=(legacy_config.name if legacy_config and legacy_config.name else node_id),
                parameters=_parameters(legacy_config),
                metadata=metadata,
            )
        )

    edges: list[Edge] = []
    terminal_edges: list[dict[str, Any]] = []
    for legacy_edge in config.edges:
        from_node = _identifier(legacy_edge.from_role)
        if from_node not in node_ids:
            raise ValueError(f"legacy edge references unknown source node {from_node!r}")

        if legacy_edge.to_role is None:
            terminal_edges.append(legacy_edge.model_dump(mode="json"))
            continue

        to_node = _identifier(legacy_edge.to_role)
        if to_node not in node_ids:
            raise ValueError(f"legacy edge references unknown target node {to_node!r}")

        edges.append(
            Edge(
                from_node=from_node,
                to_node=to_node,
                condition=legacy_edge.condition,
                metadata=_edge_metadata(legacy_edge),
            )
        )

    legacy_metadata: dict[str, Any] = {
        "entry": _identifier(config.entry),
        "hyperagent": _identifier(config.hyperagent),
        "max_cycles": config.max_cycles,
        "use_llm_routing": config.use_llm_routing,
        "run_scout": config.run_scout,
    }
    if terminal_edges:
        legacy_metadata["terminal_edges"] = terminal_edges

    graph_values: dict[str, Any] = {
        "name": name,
        "description": description,
        "nodes": nodes,
        "edges": edges,
        "metadata": {"legacy_graph_config": legacy_metadata},
    }
    if graph_id is not None:
        graph_values["graph_id"] = graph_id
    return Graph(**graph_values)
