from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from maistro_evolve.benchmarks.ifeval import run_ifeval
from maistro_evolve.cycle import EvolutionConfig, EvolutionCycle
from maistro_evolve.harness import EvalHarness
from maistro_evolve.population import PopulationStore
from maistro_evolve.reflect import (
    build_reflection_prompt,
    reflective_improve,
    spawn_challenger,
    summarize_failures,
)
from maistro_evolve.tournament import EloTournament
from maistro_evolve.types import (
    DAGTopology,
    EvalResult,
    EvalWeights,
    NodeGenome,
    PipelineGenome,
)


def _genome(name: str = "test", prompt: str = "test") -> PipelineGenome:
    return PipelineGenome(
        id=f"g-{name}",
        name=name,
        topology=DAGTopology(
            nodes=[
                NodeGenome(
                    id="q1",
                    role="queen",
                    strategy="react",
                    model="gpt-4",
                    temperature=0.3,
                    max_tokens=4096,
                    system_prompt=prompt,
                    max_tool_rounds=5,
                )
            ],
            edges=[],
            entry_node="q1",
            max_cycles=3,
            beam_width=1,
            use_scout=False,
        ),
        eval_weights=EvalWeights(),
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )


_FAILURE_METADATA = {
    "runner": "real",
    "failures": [
        {
            "instruction": "Reply in exactly two sentences.",
            "failed_rules": ["sentence_count=2"],
            "response_excerpt": "One. Two. Three.",
            "score": 0.8,
        }
    ],
}


def _keyed_harness() -> EvalHarness:
    """Harness whose ifeval score depends on the entry prompt content."""
    harness = EvalHarness(use_real_benchmarks=False)

    async def runner(genome: PipelineGenome, llm_call: Any) -> EvalResult:
        prompt = genome.topology.nodes[0].system_prompt
        score = 0.9 if "improved" in prompt else 0.4
        return EvalResult(benchmark="ifeval", score=score, metadata=dict(_FAILURE_METADATA))

    harness.register_benchmark("ifeval", runner)
    return harness


async def _llm_improved(prompt: Any, **kwargs: Any) -> str:
    return "improved prompt"


async def _llm_worse(prompt: Any, **kwargs: Any) -> str:
    return "a different but not better prompt"


class TestReflectHelpers:
    def test_summarize_failures_formats_entries(self):
        text = summarize_failures(_FAILURE_METADATA)
        assert "Reply in exactly two sentences." in text
        assert "sentence_count=2" in text
        assert "One. Two. Three." in text

    def test_summarize_failures_empty(self):
        assert summarize_failures({}) == ""
        assert summarize_failures({"failures": []}) == ""

    def test_build_reflection_prompt_grounding(self):
        g = _genome(prompt="be helpful")
        node = g.topology.nodes[0]
        feedback = summarize_failures(_FAILURE_METADATA)
        prompt = build_reflection_prompt(g, node, "ifeval", 0.4, feedback, "Be concise.")
        assert "be helpful" in prompt  # current prompt included
        assert "instruction following" in prompt  # benchmark summary grounding
        assert "queen/react" in prompt  # topology grounding
        assert "sentence_count=2" in prompt  # failure feedback
        assert "Be concise." in prompt  # proposal tip

    def test_spawn_challenger_lineage_and_reset(self):
        g = _genome()
        g.eval_scores = {"ifeval": 0.4}
        g.fitness_score = 50.0
        child = spawn_challenger(g, "q1", "improved prompt")
        assert child.id != g.id
        assert child.parent_a_id == g.id
        assert child.parent_b_id is None
        assert child.generation == g.generation + 1
        assert child.fitness_score is None
        assert child.eval_scores == {}
        assert child.harness_params["origin"] == "reflective_improve"
        assert child.topology.nodes[0].system_prompt == "improved prompt"
        # parent untouched
        assert g.topology.nodes[0].system_prompt == "test"


class TestReflectiveImprove:
    @pytest.mark.asyncio
    async def test_accepts_verified_better_candidate(self):
        g = _genome()
        g.eval_scores = {"ifeval": 0.4, "bfcl": 0.8}
        outcome = await reflective_improve(
            g, _keyed_harness(), _llm_improved, benchmarks=["ifeval", "bfcl"]
        )
        assert outcome is not None
        assert outcome.benchmark == "ifeval"  # weakest selected
        assert outcome.accepted is True
        assert outcome.challenger is not None
        assert outcome.challenger.parent_a_id == g.id
        assert outcome.challenger.eval_scores["ifeval"] == 0.9
        assert outcome.best_candidate_score == 0.9
        # parent prompt never mutated in place
        assert g.topology.nodes[0].system_prompt == "test"

    @pytest.mark.asyncio
    async def test_rejects_candidate_that_does_not_beat_baseline(self):
        g = _genome()
        g.eval_scores = {"ifeval": 0.4}
        outcome = await reflective_improve(g, _keyed_harness(), _llm_worse)
        assert outcome is not None
        assert outcome.accepted is False
        assert outcome.challenger is None
        assert outcome.reason == "no_candidate_beat_baseline"

    @pytest.mark.asyncio
    async def test_stub_signal_never_accepted(self):
        g = _genome()
        g.eval_scores = {"ifeval": 0.4}
        stub_harness = EvalHarness(use_real_benchmarks=False)
        outcome = await reflective_improve(g, stub_harness, _llm_improved)
        assert outcome is not None
        assert outcome.accepted is False
        assert outcome.reason == "stub_signal"
        assert outcome.candidate_count == 0  # no LLM proposals wasted on noise

    @pytest.mark.asyncio
    async def test_no_llm_or_no_scores_returns_none(self):
        g = _genome()
        assert await reflective_improve(g, _keyed_harness(), None) is None
        g2 = _genome("noscores")
        assert await reflective_improve(g2, _keyed_harness(), _llm_improved) is None

    @pytest.mark.asyncio
    async def test_outcome_summary_excludes_challenger(self):
        g = _genome()
        g.eval_scores = {"ifeval": 0.4}
        outcome = await reflective_improve(g, _keyed_harness(), _llm_improved)
        assert outcome is not None
        summary = outcome.summary()
        assert "challenger" not in summary
        assert summary["accepted"] is True
        assert summary["challenger_id"] == outcome.challenger.id


class TestIfevalFailureTraces:
    @pytest.mark.asyncio
    async def test_records_failure_traces_with_llm(self):
        async def bad_llm(messages: Any, **kwargs: Any) -> str:
            return "x"

        result = await run_ifeval(_genome(), bad_llm)
        failures = result.metadata.get("failures")
        assert failures, "imperfect responses must produce failure traces"
        assert len(failures) <= 5
        for entry in failures:
            assert entry["instruction"]
            assert entry["failed_rules"]

    @pytest.mark.asyncio
    async def test_no_traces_without_llm(self):
        result = await run_ifeval(_genome(), None)
        assert result.metadata.get("failures") == []


class TestCycleIntegration:
    @pytest.mark.asyncio
    async def test_self_improve_adds_challenger_child(self):
        population = PopulationStore()
        top = _genome("top")
        # all benchmarks above hard gates so the genome can be self-improved;
        # ifeval is the weakest among target benchmarks
        top.eval_scores = {
            "ifeval": 0.4,
            "bfcl": 0.6,
            "swebench": 0.6,
            "tau_bench": 0.6,
            "gaia": 0.6,
            "ragas": 0.6,
            "terminalbench": 0.6,
            "osworld": 0.6,
        }
        top.fitness_score = 60.0
        population.add(top)
        for i in range(3):
            population.add(_genome(f"fill{i}"))

        config = EvolutionConfig(
            population_size=5,
            target_benchmarks=["ifeval"],
            self_improve=True,
            self_improve_top_n=1,
            self_improve_candidates=1,
        )
        cycle = EvolutionCycle(harness=_keyed_harness(), tournament=EloTournament())
        await cycle.run_cycle(population, llm_call=_llm_improved, config=config)

        genomes = population.list_all()
        challengers = [g for g in genomes if g.harness_params.get("origin") == "reflective_improve"]
        assert challengers, "accepted challenger must join the population"
        assert challengers[0].parent_a_id == top.id
        # champion's prompt is never overwritten in place
        surviving_top = population.get(top.id)
        assert surviving_top is not None
        assert surviving_top.topology.nodes[0].system_prompt == "test"
        reflection = surviving_top.harness_params["last_optimization"]["reflection"]
        assert reflection["accepted"] is True
        assert reflection["benchmark"] == "ifeval"
