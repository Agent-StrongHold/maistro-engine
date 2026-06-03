"""Tests for mutate.py — pure genome mutation functions (codebase gap-scan)."""

from __future__ import annotations

from datetime import UTC, datetime

from maistro_evolve.mutate import (
    PROMPT_VARIATIONS,
    mutate_all,
    mutate_eval_weights,
    mutate_node,
    mutate_prompt,
    mutate_topology,
)
from maistro_evolve.types import (
    DAGEdgeGenome,
    DAGTopology,
    EvalWeights,
    NodeGenome,
    PipelineGenome,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _node(nid: str = "n1", role: str = "queen") -> NodeGenome:
    return NodeGenome(
        id=nid,
        role=role,
        strategy="react",
        model="gpt-4o",
        temperature=0.5,
        max_tokens=1024,
        system_prompt="You are a helpful assistant.",
        max_tool_rounds=5,
    )


def _genome(
    name: str = "base",
    extra_nodes: list[NodeGenome] | None = None,
    extra_edges: list[DAGEdgeGenome] | None = None,
) -> PipelineGenome:
    nodes = [_node("entry")] + (extra_nodes or [])
    edges = extra_edges or []
    return PipelineGenome(
        id="g0",
        name=name,
        topology=DAGTopology(
            nodes=nodes,
            edges=edges,
            entry_node="entry",
            max_cycles=3,
            beam_width=1,
            use_scout=False,
        ),
        eval_weights=EvalWeights(),
        harness_params={},
        fitness_score=None,
        eval_scores={},
        generation=2,
        parent_a_id=None,
        parent_b_id=None,
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# mutate_topology
# ---------------------------------------------------------------------------


class TestMutateTopology:
    def test_returns_pipeline_genome(self):
        g = _genome()
        result = mutate_topology(g, rate=1.0)
        assert isinstance(result, PipelineGenome)

    def test_entry_node_preserved(self):
        g = _genome()
        # run many times — entry_node should never disappear
        for _ in range(20):
            result = mutate_topology(g, rate=1.0)
            node_ids = {n.id for n in result.topology.nodes}
            assert result.topology.entry_node in node_ids

    def test_name_suffix(self):
        g = _genome(name="base")
        result = mutate_topology(g, rate=1.0)
        assert result.name == "base-topo-mut"

    def test_parent_a_id_set(self):
        g = _genome()
        result = mutate_topology(g, rate=1.0)
        assert result.parent_a_id == g.id

    def test_parent_b_id_is_none(self):
        g = _genome()
        result = mutate_topology(g, rate=1.0)
        assert result.parent_b_id is None

    def test_fitness_cleared(self):
        g = _genome()
        result = mutate_topology(g, rate=1.0)
        assert result.fitness_score is None

    def test_eval_scores_cleared(self):
        g = _genome()
        result = mutate_topology(g, rate=1.0)
        assert result.eval_scores == {}

    def test_generation_preserved(self):
        g = _genome()
        result = mutate_topology(g, rate=1.0)
        assert result.generation == g.generation

    def test_zero_rate_preserves_structure(self):
        extra = _node("worker", role="worker")
        g = _genome(extra_nodes=[extra])
        result = mutate_topology(g, rate=0.0)
        # rate=0 means no mutations fire — same node count and IDs
        assert len(result.topology.nodes) == len(g.topology.nodes)
        orig_ids = {n.id for n in g.topology.nodes}
        new_ids = {n.id for n in result.topology.nodes}
        assert orig_ids == new_ids

    def test_single_node_not_removed(self):
        # entry is the only node; removal requires > 1 node, so it must survive
        g = _genome()
        for _ in range(20):
            result = mutate_topology(g, rate=1.0)
            assert len(result.topology.nodes) >= 1


# ---------------------------------------------------------------------------
# mutate_node
# ---------------------------------------------------------------------------


class TestMutateNode:
    def test_returns_pipeline_genome(self):
        result = mutate_node(_genome(), rate=1.0)
        assert isinstance(result, PipelineGenome)

    def test_name_suffix(self):
        result = mutate_node(_genome(name="base"), rate=1.0)
        assert result.name == "base-node-mut"

    def test_temperature_stays_in_range(self):
        # temperature is clamped to [0, 1] after gauss perturbation
        g = _genome()
        for _ in range(50):
            result = mutate_node(g, rate=1.0)
            for node in result.topology.nodes:
                assert 0.0 <= node.temperature <= 1.0

    def test_parent_a_id_set(self):
        g = _genome()
        result = mutate_node(g, rate=1.0)
        assert result.parent_a_id == g.id

    def test_zero_rate_leaves_nodes_unchanged(self):
        g = _genome()
        result = mutate_node(g, rate=0.0)
        orig = g.topology.nodes[0]
        res = result.topology.nodes[0]
        assert orig.model == res.model
        assert orig.temperature == res.temperature
        assert orig.max_tokens == res.max_tokens
        assert orig.strategy == res.strategy
        assert orig.max_tool_rounds == res.max_tool_rounds

    def test_eval_weights_preserved(self):
        g = _genome()
        result = mutate_node(g, rate=1.0)
        assert result.eval_weights == g.eval_weights


# ---------------------------------------------------------------------------
# mutate_prompt
# ---------------------------------------------------------------------------


class TestMutatePrompt:
    def test_returns_pipeline_genome(self):
        result = mutate_prompt(_genome(), rate=1.0)
        assert isinstance(result, PipelineGenome)

    def test_name_suffix(self):
        result = mutate_prompt(_genome(name="base"), rate=1.0)
        assert result.name == "base-prompt-mut"

    def test_prompt_extended_when_variation_added(self):
        # rate=1.0 guarantees add-variation fires; check prompt grew
        g = _genome()
        original = g.topology.nodes[0].system_prompt
        # Run many times; at least once the variation-add path fires
        grew = False
        for _ in range(30):
            result = mutate_prompt(g, rate=1.0)
            if result.topology.nodes[0].system_prompt != original:
                grew = True
                break
        assert grew

    def test_added_variation_is_from_known_list(self):
        g = _genome()
        for _ in range(20):
            result = mutate_prompt(g, rate=1.0)
            prompt = result.topology.nodes[0].system_prompt
            # If prompt was extended, the added part must be a known variation
            if prompt != g.topology.nodes[0].system_prompt:
                assert any(prompt.endswith(v) for v in PROMPT_VARIATIONS)

    def test_multi_sentence_prompt_can_shrink(self):
        # Need > 2 sentences for removal to fire
        long_prompt = "You are helpful. You are accurate. You think carefully. You verify."
        node = NodeGenome(
            id="entry",
            role="queen",
            strategy="react",
            model="gpt-4o",
            temperature=0.5,
            max_tokens=1024,
            system_prompt=long_prompt,
            max_tool_rounds=5,
        )
        from maistro_evolve.types import DAGTopology

        g = PipelineGenome(
            id="g-long",
            name="long",
            topology=DAGTopology(
                nodes=[node],
                edges=[],
                entry_node="entry",
                max_cycles=3,
                beam_width=1,
                use_scout=False,
            ),
            eval_weights=EvalWeights(),
            harness_params={},
            fitness_score=None,
            eval_scores={},
            generation=0,
            parent_a_id=None,
            parent_b_id=None,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        )
        shrunk = False
        for _ in range(30):
            result = mutate_prompt(g, rate=1.0)
            if len(result.topology.nodes[0].system_prompt) < len(long_prompt):
                shrunk = True
                break
        assert shrunk

    def test_zero_rate_prompt_unchanged(self):
        g = _genome()
        result = mutate_prompt(g, rate=0.0)
        assert result.topology.nodes[0].system_prompt == g.topology.nodes[0].system_prompt


# ---------------------------------------------------------------------------
# mutate_eval_weights
# ---------------------------------------------------------------------------


class TestMutateEvalWeights:
    def test_returns_pipeline_genome(self):
        result = mutate_eval_weights(_genome(), rate=1.0)
        assert isinstance(result, PipelineGenome)

    def test_name_suffix(self):
        result = mutate_eval_weights(_genome(name="base"), rate=1.0)
        assert result.name == "base-weight-mut"

    def test_weights_sum_to_one(self):
        g = _genome()
        for _ in range(20):
            result = mutate_eval_weights(g, rate=1.0)
            total = sum(getattr(result.eval_weights, f) for f in EvalWeights.model_fields)
            assert abs(total - 1.0) < 1e-3, f"weights sum to {total}"

    def test_all_weights_positive(self):
        g = _genome()
        for _ in range(20):
            result = mutate_eval_weights(g, rate=1.0)
            for field in EvalWeights.model_fields:
                assert getattr(result.eval_weights, field) > 0.0

    def test_zero_rate_returns_genome_with_same_name_suffix(self):
        # rate=0: random.random() > 0 is True → skips mutation, still returns with suffix
        g = _genome(name="base")
        result = mutate_eval_weights(g, rate=0.0)
        assert result.name == "base-weight-mut"

    def test_parent_a_id_set(self):
        g = _genome()
        result = mutate_eval_weights(g, rate=1.0)
        assert result.parent_a_id == g.id


# ---------------------------------------------------------------------------
# mutate_all
# ---------------------------------------------------------------------------


class TestMutateAll:
    def test_returns_pipeline_genome(self):
        result = mutate_all(_genome(), rate=0.5)
        assert isinstance(result, PipelineGenome)

    def test_name_suffix_is_all_mut(self):
        result = mutate_all(_genome(name="base"), rate=0.5)
        assert result.name == "base-all-mut"

    def test_entry_node_preserved(self):
        g = _genome()
        for _ in range(10):
            result = mutate_all(g, rate=1.0)
            node_ids = {n.id for n in result.topology.nodes}
            assert result.topology.entry_node in node_ids

    def test_weights_sum_to_one(self):
        g = _genome()
        for _ in range(10):
            result = mutate_all(g, rate=1.0)
            total = sum(getattr(result.eval_weights, f) for f in EvalWeights.model_fields)
            assert abs(total - 1.0) < 1e-3

    def test_temperature_stays_in_range(self):
        g = _genome()
        for _ in range(10):
            result = mutate_all(g, rate=1.0)
            for node in result.topology.nodes:
                assert 0.0 <= node.temperature <= 1.0

    def test_fitness_cleared(self):
        g = _genome()
        result = mutate_all(g, rate=0.5)
        # fitness_score may have been set during mutation chain but final result should have None
        # (each mutate_* resets it); check the returned value
        assert result.fitness_score is None
