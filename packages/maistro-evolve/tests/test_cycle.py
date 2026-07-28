from __future__ import annotations

from datetime import UTC, datetime

import pytest

from maistro_evolve.cycle import EvolutionConfig, EvolutionCycle
from maistro_evolve.harness import EvalHarness
from maistro_evolve.population import PopulationStore
from maistro_evolve.tournament import EloTournament
from maistro_evolve.types import DAGTopology, EvalWeights, NodeGenome, PipelineGenome


def _genome(name="test"):
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
                    system_prompt="test",
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


class TestPopulationStore:
    def test_add_and_get(self):
        store = PopulationStore()
        g = _genome("a")
        store.add(g)
        assert store.get("g-a") is not None
        assert store.get("g-a").id == "g-a"

    def test_get_missing_returns_none(self):
        store = PopulationStore()
        assert store.get("nonexistent") is None

    def test_list_all(self):
        store = PopulationStore()
        store.add(_genome("a"))
        store.add(_genome("b"))
        assert len(store.list_all()) == 2

    def test_remove(self):
        store = PopulationStore()
        store.add(_genome("a"))
        store.remove("g-a")
        assert store.get("g-a") is None

    def test_get_champion_none_when_empty(self):
        store = PopulationStore()
        assert store.get_champion() is None

    def test_get_champion_returns_highest_fitness(self):
        store = PopulationStore()
        g1 = _genome("a")
        g1.fitness_score = 50.0
        g1.eval_scores = {"ifeval": 0.8, "bfcl": 0.7}
        g2 = _genome("b")
        g2.fitness_score = 80.0
        g2.eval_scores = {"ifeval": 0.9, "bfcl": 0.8}
        store.add(g1)
        store.add(g2)
        champ = store.get_champion()
        assert champ is not None
        assert champ.id == "g-b"

    def test_cull_bottom_removes_lowest(self):
        store = PopulationStore()
        for i in range(10):
            g = _genome(str(i))
            g.fitness_score = float(i) * 10
            store.add(g)
        removed = store.cull_bottom(0.3)
        assert removed == 3
        remaining = store.list_all()
        assert len(remaining) == 7
        assert all(g.fitness_score >= 30.0 for g in remaining)

    def test_get_breeding_pool(self):
        store = PopulationStore()
        for i in range(10):
            g = _genome(str(i))
            g.fitness_score = float(i) * 10
            store.add(g)
        pool = store.get_breeding_pool(3)
        assert len(pool) == 3
        assert pool[0].fitness_score >= pool[1].fitness_score

    def test_lineage_follows_parents(self):
        store = PopulationStore()
        g1 = _genome("a")
        g2 = _genome("b")
        g3 = _genome("c")
        g3.parent_a_id = "g-a"
        store.add(g1)
        store.add(g2)
        store.add(g3)
        lineage = store.get_lineage("g-c")
        assert len(lineage) == 2
        assert lineage[0].id == "g-c"
        assert lineage[1].id == "g-a"


class TestEvolutionCycle:
    @pytest.mark.asyncio
    async def test_cycle_creates_children(self):
        population = PopulationStore()
        for i in range(6):
            population.add(_genome(f"s{i}"))

        harness = EvalHarness(benchmark_fidelity="stub")
        tournament = EloTournament()
        config = EvolutionConfig(
            population_size=10,
            eval_batch_size=2,
            target_benchmarks=["ifeval", "bfcl"],
            self_improve=False,
        )

        cycle = EvolutionCycle(harness=harness, tournament=tournament)
        await cycle.run_cycle(population, llm_call=None, config=config)

        assert len(population.list_all()) >= 6

    @pytest.mark.asyncio
    async def test_cycle_populates_tournament(self):
        population = PopulationStore()
        for i in range(4):
            g = _genome(f"s{i}")
            g.eval_scores = {"ifeval": 0.5 + i * 0.1, "bfcl": 0.4 + i * 0.1}
            g.fitness_score = float(i) * 10
            population.add(g)

        harness = EvalHarness(benchmark_fidelity="stub")
        tournament = EloTournament()
        config = EvolutionConfig(
            population_size=6,
            target_benchmarks=["ifeval", "bfcl"],
            self_improve=False,
        )

        cycle = EvolutionCycle(harness=harness, tournament=tournament)
        await cycle.run_cycle(population, llm_call=None, config=config)

        stats = tournament.get_stats()
        assert stats["total_battles"] > 0

    @pytest.mark.asyncio
    async def test_cycle_with_self_improve(self):
        population = PopulationStore()
        g = _genome("top")
        g.eval_scores = {"ifeval": 0.8, "bfcl": 0.7, "gaia": 0.6}
        g.fitness_score = 60.0
        population.add(g)
        for i in range(3):
            population.add(_genome(f"fill{i}"))

        harness = EvalHarness(benchmark_fidelity="stub")
        tournament = EloTournament()
        config = EvolutionConfig(
            population_size=5,
            target_benchmarks=["ifeval", "bfcl"],
            self_improve=True,
            self_improve_top_n=1,
        )

        cycle = EvolutionCycle(harness=harness, tournament=tournament)
        await cycle.run_cycle(population, llm_call=None, config=config)

        genomes = population.list_all()
        assert len(genomes) >= 4


class TestEvalHarness:
    def test_stub_harness(self):
        harness = EvalHarness(benchmark_fidelity="stub")
        assert len(harness._benchmarks) == 8

    def test_real_harness(self):
        harness = EvalHarness(benchmark_fidelity="proxy")
        assert len(harness._benchmarks) == 8
        for name in [
            "ifeval",
            "bfcl",
            "swebench",
            "terminalbench",
            "tau_bench",
            "gaia",
            "ragas",
            "osworld",
        ]:
            assert name in harness._benchmarks

    @pytest.mark.asyncio
    async def test_evaluate_genome_stubs(self):
        harness = EvalHarness(benchmark_fidelity="stub")
        g = _genome("eval")
        results = await harness.evaluate_genome(g)
        assert len(results) == 8
        for r in results:
            assert 0.0 <= r.score <= 1.0
            assert r.metadata.get("stub") is True

    @pytest.mark.asyncio
    async def test_evaluate_genome_real_no_llm(self):
        harness = EvalHarness(benchmark_fidelity="proxy")
        g = _genome("eval")
        results = await harness.evaluate_genome(g, benchmarks=["ifeval", "gaia"])
        assert len(results) == 2
        for r in results:
            assert 0.0 <= r.score <= 1.0
            assert r.metadata.get("fidelity") == "proxy"
