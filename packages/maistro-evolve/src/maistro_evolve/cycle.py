from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .crossover import crossover_and_mutate
from .diversity import emergency_spawn, population_diversity
from .fitness import compute_fitness
from .harness import EvalHarness
from .optimizer import extract_signal, optimize_topology
from .population import PopulationStore
from .reflect import reflective_improve
from .tournament import EloTournament
from .types import PipelineGenome

# Hard, non-overridable ceilings on per-cycle resource/compute consumption.
# These are RSI safety bounds (not tuning knobs): an evolution loop with no
# enforced upper limit on eval batch size, population size, or self-improve
# fan-out can be pointed at an unboundedly large config and consume
# unboundedly large compute/cost in a single run_cycle() call. Pydantic's
# Field(le=...) rejects out-of-range values at construction time — there is
# no way to build an EvolutionConfig that exceeds these caps.
MAX_EVAL_BATCH_SIZE = 50
MAX_POPULATION_SIZE = 200
MAX_TOURNAMENT_SIZE = 20
MAX_SELF_IMPROVE_TOP_N = 10
MAX_SELF_IMPROVE_CANDIDATES = 10


class EvolutionConfig(BaseModel):
    population_size: int = Field(default=20, gt=0, le=MAX_POPULATION_SIZE)
    mutation_rate: float = 0.3
    cull_pct: float = 0.3
    breed_pct: float = 0.2
    eval_batch_size: int = Field(default=5, ge=0, le=MAX_EVAL_BATCH_SIZE)
    target_benchmarks: list[str] = ["ifeval", "bfcl", "swebench", "tau_bench"]
    diversity_threshold: float = 1.0
    tournament_size: int = Field(default=3, gt=0, le=MAX_TOURNAMENT_SIZE)
    self_improve: bool = True
    self_improve_top_n: int = Field(default=3, ge=0, le=MAX_SELF_IMPROVE_TOP_N)
    self_improve_candidates: int = Field(default=2, ge=0, le=MAX_SELF_IMPROVE_CANDIDATES)
    self_improve_accept_margin: float = 0.0
    reflect_history_window: int = Field(default=5, ge=0)
    node_attribution: bool = True


class EvolutionCycle:
    def __init__(
        self,
        harness: EvalHarness | None = None,
        tournament: EloTournament | None = None,
    ) -> None:
        self.harness = harness or EvalHarness()
        self.tournament = tournament or EloTournament()

    async def _evaluate_unevaluated(
        self,
        population: PopulationStore,
        config: EvolutionConfig,
        llm_call: Any = None,
    ) -> None:
        all_genomes = population.list_all()
        unevaluated = [g for g in all_genomes if g.fitness_score is None or not g.eval_scores]
        batch = unevaluated[: config.eval_batch_size]
        for genome in batch:
            results = await self.harness.evaluate_genome(genome, config.target_benchmarks, llm_call)
            for r in results:
                genome.eval_scores[r.benchmark] = r.score
                genome.harness_params["total_cost_usd"] = (
                    genome.harness_params.get("total_cost_usd", 0.0) + r.cost_usd
                )
                genome.harness_params["avg_latency_seconds"] = (
                    genome.harness_params.get("avg_latency_seconds", 0.0) + r.duration_seconds
                ) / max(len(genome.eval_scores), 1)
            genome.updated_at = datetime.now(UTC).isoformat()
            population.add(genome)

    async def _run_tournament_battles(
        self,
        population: PopulationStore,
        config: EvolutionConfig,
    ) -> None:
        all_genomes = population.list_all()
        if len(all_genomes) < 2:
            return

        scored = [g for g in all_genomes if g.eval_scores]
        if len(scored) < 2:
            return

        pairs_to_battle: list[tuple[PipelineGenome, PipelineGenome]] = []
        shuffled = list(scored)
        random.shuffle(shuffled)
        for i in range(0, len(shuffled) - 1, 2):
            pairs_to_battle.append((shuffled[i], shuffled[i + 1]))

        for a, b in pairs_to_battle:
            common_benchmarks = set(a.eval_scores.keys()) & set(b.eval_scores.keys())
            for bench in common_benchmarks:
                self.tournament.record_battle(
                    benchmark=bench,
                    genome_a_id=a.id,
                    genome_b_id=b.id,
                    score_a=a.eval_scores[bench],
                    score_b=b.eval_scores[bench],
                )

        for g in scored:
            avg_elo = self.tournament.get_avg_elo(g.id)
            if avg_elo > 0:
                g.harness_params["avg_elo"] = avg_elo

    def _compute_all_fitness(self, population: PopulationStore) -> list[PipelineGenome]:
        all_genomes = population.list_all()
        for g in all_genomes:
            components = compute_fitness(g, all_genomes)
            g.fitness_score = components.total
            g.updated_at = datetime.now(UTC).isoformat()
            population.add(g)
        return population.list_all()

    def _tournament_select_parents(
        self,
        population: PopulationStore,
        config: EvolutionConfig,
        count: int,
    ) -> list[PipelineGenome]:
        all_genomes = population.list_all()
        if not all_genomes:
            return []

        parent_ids: list[str] = []
        for _ in range(count * 2):
            selected = self.tournament.tournament_select(
                [g.id for g in all_genomes],
                tournament_size=config.tournament_size,
            )
            if selected:
                parent_ids.append(selected)

        genome_map = {g.id: g for g in all_genomes}
        return [genome_map[pid] for pid in parent_ids if pid in genome_map]

    async def _self_improve_top(
        self,
        population: PopulationStore,
        config: EvolutionConfig,
        llm_call: Any = None,
    ) -> None:
        if not config.self_improve or llm_call is None:
            return

        all_genomes = population.list_all()
        scored = [g for g in all_genomes if g.fitness_score is not None and g.fitness_score > 0]
        if not scored:
            return

        scored.sort(key=lambda g: g.fitness_score or 0.0, reverse=True)
        top = scored[: config.self_improve_top_n]

        for genome in top:
            from .types import EvalResult

            eval_results = [EvalResult(benchmark=k, score=v) for k, v in genome.eval_scores.items()]
            signal = extract_signal(genome, eval_results)

            # Assemble OPRO-style history from prior reflection cycles on this genome.
            stored_history: list[tuple[str, float]] = genome.harness_params.get(
                "reflection_history", []
            )
            window = config.reflect_history_window
            prompt_history = stored_history[-window:] if window > 0 else []

            # Propose-then-verify (GEPA-style): the parent is never mutated in
            # place; an accepted challenger joins the pool as its child.
            outcome = await reflective_improve(
                genome,
                self.harness,
                llm_call,
                benchmarks=config.target_benchmarks,
                num_candidates=config.self_improve_candidates,
                accept_margin=config.self_improve_accept_margin,
                prompt_history=prompt_history,
                node_attribution=config.node_attribution,
            )
            if outcome is not None and outcome.accepted and outcome.challenger is not None:
                population.add(outcome.challenger)

            # Persist new excerpt + score so future cycles have a trajectory to learn from.
            if (
                outcome is not None
                and outcome.best_candidate_prompt_excerpt is not None
                and outcome.best_candidate_score is not None
            ):
                updated_history = [
                    *stored_history,
                    (outcome.best_candidate_prompt_excerpt, outcome.best_candidate_score),
                ]
                if window > 0:
                    updated_history = updated_history[-window:]
                genome.harness_params["reflection_history"] = updated_history

            topo_signal = await optimize_topology(genome, signal, llm_call)
            genome.harness_params["last_optimization"] = {
                "signal": signal,
                "reflection": outcome.summary() if outcome is not None else None,
                "topology_suggestion": topo_signal,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            genome.updated_at = datetime.now(UTC).isoformat()
            population.add(genome)

    async def run_cycle(
        self,
        population: PopulationStore,
        llm_call: Any = None,
        config: EvolutionConfig | None = None,
    ) -> PopulationStore:
        cfg = config or EvolutionConfig()

        await self._evaluate_unevaluated(population, cfg, llm_call)

        await self._run_tournament_battles(population, cfg)

        self._compute_all_fitness(population)

        population.cull_bottom(cfg.cull_pct)

        if self.tournament.get_stats()["total_genomes_rated"] >= 2:
            parents = self._tournament_select_parents(population, cfg, cfg.population_size)
            current_count = len(population.list_all())
            needed = max(0, cfg.population_size - current_count)
            for i in range(0, min(needed, len(parents) - 1), 2):
                a = parents[i]
                b = parents[i + 1] if i + 1 < len(parents) else parents[0]
                child = crossover_and_mutate(a, b, cfg.mutation_rate)
                population.add(child)
        else:
            breeding_pool = population.get_breeding_pool(
                max(2, int(cfg.population_size * cfg.breed_pct))
            )
            current_count = len(population.list_all())
            needed = max(0, cfg.population_size - current_count)
            for _ in range(needed):
                pa: PipelineGenome | None
                pb: PipelineGenome | None
                if len(breeding_pool) >= 2:
                    pa, pb = random.sample(breeding_pool, 2)
                else:
                    pa = breeding_pool[0] if breeding_pool else None
                    pb = None
                if pa and pb:
                    child = crossover_and_mutate(pa, pb, cfg.mutation_rate)
                    population.add(child)

        await self._self_improve_top(population, cfg, llm_call)

        current_genomes = population.list_all()
        div = population_diversity(current_genomes)
        if div < cfg.diversity_threshold:
            spawn_count = max(2, cfg.population_size // 5)
            spawned = emergency_spawn(current_genomes, spawn_count)
            for g in spawned:
                population.add(g)

        return population
