from __future__ import annotations

import pytest

from maistro.graph.compat import graph_config_to_graph
from maistro.graph.pm_domain import build_pm_graph_config
from maistro.graph.types import AgentRole, GraphConfig, GraphEdge, NodeConfig


def test_graph_config_to_graph_preserves_pm_topology_and_execution_settings() -> None:
    legacy = build_pm_graph_config(
        max_cycles=3,
        per_role_temperature={AgentRole.RESEARCH: 0.7},
    )

    graph = graph_config_to_graph(legacy, graph_id="pm-graph", name="PM Fleet")

    assert graph.graph_id == "pm-graph"
    assert graph.name == "PM Fleet"
    assert {node.node_id for node in graph.nodes} == {
        "intake",
        "program_manager",
        "research",
        "delivery",
        "risk_dependency",
        "reporting",
    }

    research = next(node for node in graph.nodes if node.node_id == "research")
    assert research.node_type == "research"
    assert research.parameters["temperature"] == 0.7
    assert research.parameters["beam_width"] == 1
    assert research.metadata["legacy_node_config"]["role"] == "research"

    fanout = next(
        edge
        for edge in graph.edges
        if edge.from_node == "program_manager" and edge.to_node == "research"
    )
    assert fanout.metadata["legacy_graph_edge"]["parallel"] is True

    legacy_metadata = graph.metadata["legacy_graph_config"]
    assert legacy_metadata == {
        "entry": "intake",
        "hyperagent": "intake",
        "max_cycles": 3,
        "use_llm_routing": False,
        "run_scout": False,
    }


def test_phase_two_kind_and_learned_edge_scalars_are_preserved_without_normalization() -> None:
    legacy = GraphConfig(
        nodes={
            "fetch": NodeConfig(
                role="worker",
                kind="jira.poll",
                name="Fetch Jira",
                model="tool-model",
                confidence=0.65,
            ),
            "summarize": NodeConfig(
                role="worker",
                kind="llm.summarize",
                name="Summarize",
                temperature=0.15,
            ),
        },
        edges=[
            GraphEdge(
                from_node="fetch",
                to_node="summarize",
                condition="has_issues",
                weight=0.75,
                trust=0.8,
                sign=-1,
                staleness_decay_s=30,
            )
        ],
        entry="fetch",
        hyperagent="summarize",
        use_llm_routing=True,
    )

    graph = graph_config_to_graph(legacy)

    fetch = next(node for node in graph.nodes if node.node_id == "fetch")
    summarize = next(node for node in graph.nodes if node.node_id == "summarize")
    assert fetch.node_type == "jira.poll"
    assert fetch.name == "Fetch Jira"
    assert fetch.parameters["model"] == "tool-model"
    assert fetch.metadata["legacy_node_config"]["confidence"] == 0.65
    assert summarize.node_type == "llm.summarize"
    assert summarize.parameters["temperature"] == 0.15

    edge = graph.edges[0]
    assert edge.condition == "has_issues"
    assert edge.metadata["legacy_graph_edge"] == {
        "parallel": False,
        "weight": 0.75,
        "trust": 0.8,
        "sign": -1,
        "staleness_decay_s": 30,
    }
    assert graph.metadata["legacy_graph_config"]["use_llm_routing"] is True


def test_terminal_sentinel_is_preserved_in_metadata_not_materialized_as_invalid_edge() -> None:
    legacy = GraphConfig(
        nodes=["only"],
        edges=[GraphEdge(from_node="only", to_node=None, condition="done")],
        entry="only",
        hyperagent="only",
    )

    graph = graph_config_to_graph(legacy)

    assert graph.edges == []
    terminal_edges = graph.metadata["legacy_graph_config"]["terminal_edges"]
    assert terminal_edges == [
        {
            "from_role": "only",
            "to_role": None,
            "condition": "done",
            "parallel": False,
            "weight": 1.0,
            "trust": 1.0,
            "sign": 1,
            "staleness_decay_s": 0,
        }
    ]


def test_adapter_rejects_edges_that_reference_nodes_outside_legacy_graph() -> None:
    legacy = GraphConfig(
        nodes=["known"],
        edges=[GraphEdge(from_node="known", to_node="missing")],
        entry="known",
        hyperagent="known",
    )

    with pytest.raises(ValueError, match="unknown target node 'missing'"):
        graph_config_to_graph(legacy)


def test_adapter_uses_canonical_graph_id_factory_when_id_is_not_supplied() -> None:
    graph = graph_config_to_graph(
        GraphConfig(nodes=["one"], entry="one", hyperagent="one")
    )

    assert graph.graph_id
    assert graph.graph_id != "None"
