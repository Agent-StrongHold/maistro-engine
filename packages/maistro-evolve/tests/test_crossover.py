"""Tests for crossover.py — recombination of PipelineGenomes (codebase gap-scan)."""

from __future__ import annotations

from datetime import UTC, datetime

from maistro_evolve.crossover import crossover, crossover_and_mutate
from maistro_evolve.types import (
    DAGEdgeGenome,
    DAGTopology,
    EvalWeights,
    NodeGenome,
    PipelineGenome,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(nid: str, role: str = "worker") -> NodeGenome:
    return NodeGenome(
        id=nid,
        role=role,
        strategy="react",
        model="gpt-4o",
        temperature=0.5,
        max_tokens=1024,
        system_prompt="You are helpful.",
        max_tool_rounds=5,
    )


def _genome(
    gid: str = "g0",
    name: str = "base",
    entry: str = "e",
    extra_nodes: list[NodeGenome] | None = None,
    extra_edges: list[DAGEdgeGenome] | None = None,
    generation: int = 1,
    weights: EvalWeights | None = None,
) -> PipelineGenome:
    nodes = [_node(entry, role="queen")] + (extra_nodes or [])
    return PipelineGenome(
        id=gid,
        name=name,
        topology=DAGTopology(
            nodes=nodes,
            edges=extra_edges or [],
            entry_node=entry,
            max_cycles=3,
            beam_width=1,
            use_scout=False,
        ),
        eval_weights=weights or EvalWeights(),
        harness_params={},
        fitness_score=None,
        eval_scores={},
        generation=generation,
        parent_a_id=None,
        parent_b_id=None,
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# crossover
# ---------------------------------------------------------------------------


class TestCrossover:
    def test_returns_pipeline_genome(self):
        a = _genome("a", entry="ea")
        b = _genome("b", entry="eb")
        child = crossover(a, b)
        assert isinstance(child, PipelineGenome)

    def test_child_entry_node_comes_from_parent_a(self):
        a = _genome("a", entry="entry_a")
        b = _genome("b", entry="entry_b")
        child = crossover(a, b)
        assert child.topology.entry_node == "entry_a"

    def test_entry_node_id_preserved_exactly(self):
        a = _genome("a", entry="entry_a")
        b = _genome("b", entry="entry_b")
        child = crossover(a, b)
        node_ids = {n.id for n in child.topology.nodes}
        assert "entry_a" in node_ids

    def test_child_generation_is_max_plus_one(self):
        a = _genome("a", generation=3)
        b = _genome("b", generation=5)
        child = crossover(a, b)
        assert child.generation == 6

    def test_child_generation_equal_parents(self):
        a = _genome("a", generation=4)
        b = _genome("b", generation=4)
        child = crossover(a, b)
        assert child.generation == 5

    def test_parent_ids_recorded(self):
        a = _genome("pid_a")
        b = _genome("pid_b")
        child = crossover(a, b)
        assert child.parent_a_id == "pid_a"
        assert child.parent_b_id == "pid_b"

    def test_eval_weights_averaged(self):
        w_a = EvalWeights(
            ifeval=0.2,
            bfcl=0.1,
            swebench=0.2,
            terminalbench=0.1,
            tau_bench=0.1,
            gaia=0.1,
            ragas=0.1,
            osworld=0.1,
        )
        w_b = EvalWeights(
            ifeval=0.0,
            bfcl=0.3,
            swebench=0.2,
            terminalbench=0.1,
            tau_bench=0.1,
            gaia=0.1,
            ragas=0.1,
            osworld=0.1,
        )
        a = _genome("a", weights=w_a)
        b = _genome("b", weights=w_b)
        child = crossover(a, b)
        expected_ifeval = round((0.2 + 0.0) / 2.0, 4)
        assert child.eval_weights.ifeval == expected_ifeval

    def test_child_has_all_nodes_from_both_parents(self):
        w1 = _node("w1")
        w2 = _node("w2")
        a = _genome("a", entry="ea", extra_nodes=[w1])
        b = _genome("b", entry="eb", extra_nodes=[w2])
        child = crossover(a, b)
        # entry from a + w1 (from other_a) + w2 (from other_b) = 3 nodes
        # parent_b's entry node is excluded from other_b (crossover uses parent_a's entry)
        assert len(child.topology.nodes) == 3

    def test_child_fitness_cleared(self):
        a = _genome("a")
        b = _genome("b")
        child = crossover(a, b)
        assert child.fitness_score is None

    def test_child_eval_scores_cleared(self):
        a = _genome("a")
        b = _genome("b")
        child = crossover(a, b)
        assert child.eval_scores == {}

    def test_edges_from_both_parents_remapped(self):
        e_a = DAGEdgeGenome(id="edge_a", from_node="ea", to_node="wa", condition=None)
        e_b = DAGEdgeGenome(id="edge_b", from_node="eb", to_node="wb", condition="success")
        wa = _node("wa")
        wb = _node("wb")
        a = _genome("a", entry="ea", extra_nodes=[wa], extra_edges=[e_a])
        b = _genome("b", entry="eb", extra_nodes=[wb], extra_edges=[e_b])
        child = crossover(a, b)
        # All edge node references must point to valid child nodes
        child_node_ids = {n.id for n in child.topology.nodes}
        for edge in child.topology.edges:
            assert edge.from_node in child_node_ids

    def test_max_cycles_takes_max_of_parents(self):
        from maistro_evolve.types import DAGTopology

        a = _genome("a")
        b = _genome("b")
        # Override max_cycles by building manually
        a.topology.__dict__  # pydantic model, need rebuild
        a2 = PipelineGenome(
            **{
                **a.model_dump(),
                "topology": DAGTopology(**{**a.topology.model_dump(), "max_cycles": 2}),
            }
        )
        b2 = PipelineGenome(
            **{
                **b.model_dump(),
                "topology": DAGTopology(**{**b.topology.model_dump(), "max_cycles": 7}),
            }
        )
        child = crossover(a2, b2)
        assert child.topology.max_cycles == 7

    def test_use_scout_is_or_of_parents(self):
        from maistro_evolve.types import DAGTopology

        a2 = PipelineGenome(
            **{
                **_genome("a").model_dump(),
                "topology": DAGTopology(
                    **{**_genome("a").topology.model_dump(), "use_scout": False}
                ),
            }
        )
        b2 = PipelineGenome(
            **{
                **_genome("b").model_dump(),
                "topology": DAGTopology(
                    **{**_genome("b").topology.model_dump(), "use_scout": True}
                ),
            }
        )
        child = crossover(a2, b2)
        assert child.topology.use_scout is True

    def test_harness_params_from_parent_a(self):
        a = _genome("a")
        b = _genome("b")
        a_params = PipelineGenome(**{**a.model_dump(), "harness_params": {"timeout": 30}})
        child = crossover(a_params, b)
        assert child.harness_params == {"timeout": 30}


# ---------------------------------------------------------------------------
# crossover_and_mutate
# ---------------------------------------------------------------------------


class TestCrossoverAndMutate:
    def test_returns_pipeline_genome(self):
        a = _genome("a", entry="ea")
        b = _genome("b", entry="eb")
        result = crossover_and_mutate(a, b)
        assert isinstance(result, PipelineGenome)

    def test_entry_node_still_in_topology(self):
        a = _genome("a", entry="ea")
        b = _genome("b", entry="eb")
        for _ in range(10):
            result = crossover_and_mutate(a, b, mutation_rate=1.0)
            node_ids = {n.id for n in result.topology.nodes}
            assert result.topology.entry_node in node_ids

    def test_temperature_in_range_after_mutation(self):
        a = _genome("a", entry="ea")
        b = _genome("b", entry="eb")
        for _ in range(10):
            result = crossover_and_mutate(a, b, mutation_rate=1.0)
            for node in result.topology.nodes:
                assert 0.0 <= node.temperature <= 1.0

    def test_eval_weights_sum_to_one_after_mutation(self):
        a = _genome("a", entry="ea")
        b = _genome("b", entry="eb")
        for _ in range(10):
            result = crossover_and_mutate(a, b, mutation_rate=1.0)
            total = sum(getattr(result.eval_weights, f) for f in EvalWeights.model_fields)
            assert abs(total - 1.0) < 1e-3

    def test_zero_mutation_rate_child_preserves_crossover_structure(self):
        a = _genome("a", entry="ea")
        b = _genome("b", entry="eb")
        result = crossover_and_mutate(a, b, mutation_rate=0.0)
        # With rate=0, topology/nodes from crossover should be mostly intact
        # entry node preserved (no topology mutations at rate=0)
        node_ids = {n.id for n in result.topology.nodes}
        assert result.topology.entry_node in node_ids
