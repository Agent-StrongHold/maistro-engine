from __future__ import annotations

from maistro.graph.definitions import Edge, Graph, GraphTemplate, Node, NodeTemplate


def test_node_template_instantiation_is_independent_and_records_exact_provenance() -> None:
    template = NodeTemplate(
        template_id="node-template",
        workspace_id="workspace-1",
        version=3,
        name="Researcher",
        node_type="agent",
        parameters={"model": "primary", "nested": {"temperature": 0.2}},
        binding_ids=["search"],
    )

    first = template.instantiate(node_id="node-1")
    second = template.instantiate(node_id="node-2")

    assert first.source_template is not None
    assert first.source_template.template_id == "node-template"
    assert first.source_template.template_version == 3
    assert first.source_template.template_hash == template.content_hash
    assert second.source_template == first.source_template

    first.parameters["nested"]["temperature"] = 0.9
    first.binding_ids.append("filesystem")

    assert second.parameters["nested"]["temperature"] == 0.2
    assert second.binding_ids == ["search"]
    assert template.parameters["nested"]["temperature"] == 0.2
    assert template.binding_ids == ["search"]


def test_template_change_does_not_retroactively_change_existing_node() -> None:
    original = NodeTemplate(
        template_id="node-template",
        workspace_id="workspace-1",
        version=1,
        name="Coder",
        node_type="agent",
        parameters={"model": "v1"},
    )
    instance = original.instantiate(node_id="node-1")

    updated = original.model_copy(
        deep=True,
        update={"version": 2, "parameters": {"model": "v2"}},
    )

    assert instance.parameters == {"model": "v1"}
    assert instance.source_template is not None
    assert instance.source_template.template_version == 1
    assert updated.instantiate().source_template.template_version == 2


def test_graph_template_instantiation_allocates_independent_topology() -> None:
    source = Node(node_id="source", node_type="agent", name="Source", parameters={"x": [1]})
    sink = Node(node_id="sink", node_type="transform", name="Sink")
    template = GraphTemplate(
        template_id="graph-template",
        workspace_id="workspace-1",
        version=4,
        name="Pipeline",
        nodes=[source, sink],
        edges=[Edge(edge_id="edge", from_node="source", to_node="sink")],
        metadata={"labels": ["canonical"]},
    )

    first = template.instantiate(graph_id="graph-1")
    second = template.instantiate(graph_id="graph-2")

    assert first.source_template is not None
    assert first.source_template.template_id == "graph-template"
    assert first.source_template.template_version == 4
    assert first.source_template.template_hash == template.content_hash

    first_ids = {node.node_id for node in first.nodes}
    second_ids = {node.node_id for node in second.nodes}
    assert first_ids.isdisjoint(second_ids)
    assert first.edges[0].from_node in first_ids
    assert first.edges[0].to_node in first_ids
    assert second.edges[0].from_node in second_ids
    assert second.edges[0].to_node in second_ids

    first.nodes[0].parameters["x"].append(2)
    first.metadata["labels"].append("changed")

    assert second.nodes[0].parameters["x"] == [1]
    assert template.nodes[0].parameters["x"] == [1]
    assert second.metadata["labels"] == ["canonical"]
    assert template.metadata["labels"] == ["canonical"]


def test_objects_can_be_saved_as_new_templates_without_inheriting_object_identity() -> None:
    node = Node(
        node_id="live-node",
        node_type="agent",
        name="Edited Coder",
        parameters={"model": "new-model"},
    )
    node_template = NodeTemplate.from_node(
        node,
        workspace_id="workspace-1",
        template_id="saved-node-template",
        version=1,
    )

    graph = Graph(
        graph_id="live-graph",
        name="Edited Pipeline",
        nodes=[node],
    )
    graph_template = GraphTemplate.from_graph(
        graph,
        workspace_id="workspace-1",
        template_id="saved-graph-template",
        version=1,
    )

    new_node = node_template.instantiate()
    new_graph = graph_template.instantiate()

    assert new_node.node_id != node.node_id
    assert new_node.source_template is not None
    assert new_node.source_template.template_id == "saved-node-template"
    assert new_graph.graph_id != graph.graph_id
    assert new_graph.source_template is not None
    assert new_graph.source_template.template_id == "saved-graph-template"
    assert new_graph.nodes[0].node_id != node.node_id
