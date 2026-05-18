from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel

from .crossover import crossover_and_mutate
from .diversity import emergency_spawn, population_diversity
from .fitness import compute_fitness
from .harness import EvalHarness
from .population import PopulationStore
from .types import PipelineGenome


class EvolutionConfig(BaseModel):
    population_size: int = 20
    mutation_rate: float = 0.3
    cull_pct: float = 0.3
    breed_pct: float = 0.2
    eval_batch_size: int = 5
    target_benchmarks: list[str] = ["ifeval", "bfcl", "swebench", "tau_bench"]
    diversity_threshold: float = 1.0


class EvolutionCycle:
    def __init__(self, harness: EvalHarness | None = None) -> None:
        self.harness = harness or EvalHarness()

    async def _evaluate_unevaluated(
        self,
        population: PopulationStore,
        config: EvolutionConfig,
        llm_call: Any = None,
    ) -> None:
        all_genomes = population.list_all()
        unevaluated = [
            g for g in all_genomes
            if g.fitness_score is None or not g.eval_scores
        ]
        batch = unevaluated[: config.eval_batch_size]
        for genome in batch:
            results = await self.harness.evaluate_genome(
                genome, config.target_benchmarks, llm_call
            )
            for r in results:
                genome.eval_scores[r.benchmark] = r.score
                genome.harness_params["total_cost_usd"] = (
                    genome.harness_params.get("total_cost_usd", 0.0) + r.cost_usd
                )
                genome.harness_params["avg_latency_seconds"] = (
                    genome.harness_params.get("avg_latency_seconds", 0.0) + r.duration_seconds
                ) / max(len(genome.eval_scores), 1)
            from datetime import datetime, timezone
            genome.updated_at = datetime.now(timezone.utc).isoformat()
            population.add(genome)

    def _compute_all_fitness(
        self, population: PopulationStore
    ) -> list[PipelineGenome]:
        all_genomes = population.list_all()
        for g in all_genomes:
            components = compute_fitness(g, all_genomes)
            g.fitness_score = components.total
            from datetime import datetime, timezone
            g.updated_at = datetime.now(timezone.utc).isoformat()
            population.add(g)
        return population.list_all()

    async def run_cycle(
        self,
        population: PopulationStore,
        llm_call: Any = None,
        config: EvolutionConfig | None = None,
    ) -> PopulationStore:
        cfg = config or EvolutionConfig()

        await self._evaluate_unevaluated(population, cfg, llm_call)
        self._compute_all_fitness(population)

        population.cull_bottom(cfg.cull_pct)

        breeding_pool = population.get_breeding_pool(
            max(2, int(cfg.population_size * cfg.breed_pct))
        )
        current_count = len(population.list_all())
        needed = max(0, cfg.population_size - current_count)

        for _ in range(needed):
            if len(breeding_pool) >= 2:
                a, b = random.sample(breeding_pool, 2)
            else:
                a = breeding_pool[0] if breeding_pool else None
                b = None
            if a and b:
                child = crossover_and_mutate(a, b, cfg.mutation_rate)
                population.add(child)

        current_genomes = population.list_all()
        div = population_diversity(current_genomes)
        if div < cfg.diversity_threshold:
            spawn_count = max(2, cfg.population_size // 5)
            spawned = emergency_spawn(current_genomes, spawn_count)
            for g in spawned:
                population.add(g)

        return population
