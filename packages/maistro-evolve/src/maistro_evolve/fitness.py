from __future__ import annotations

from .types import FitnessComponents, PipelineGenome

_HARD_GATE_THRESHOLDS: dict[str, float] = {
    "ifeval": 0.25,
    "bfcl": 0.20,
    "swebench": 0.15,
    "tau_bench": 0.20,
    "gaia": 0.30,
    "ragas": 0.25,
    "terminalbench": 0.20,
    "osworld": 0.15,
}

_FITNESS_WEIGHTS = {
    "eval_score": 0.65,
    "cost_efficiency": 0.15,
    "latency_efficiency": 0.10,
    "diversity_bonus": 0.05,
    "elo_bonus": 0.05,
}


def _check_hard_gate(genome: PipelineGenome) -> tuple[bool, list[str]]:
    failures: list[str] = []
    scores = genome.eval_scores

    for bench, threshold in _HARD_GATE_THRESHOLDS.items():
        if bench not in scores:
            failures.append(f"missing {bench} score")
        elif scores[bench] < threshold:
            failures.append(f"{bench} score {scores[bench]:.3f} below gate {threshold}")

    return len(failures) == 0, failures


def _weighted_eval_score(genome: PipelineGenome) -> float:
    if not genome.eval_scores:
        return 0.0
    total = 0.0
    for field_name in type(genome.eval_weights).model_fields:
        weight = getattr(genome.eval_weights, field_name)
        score = genome.eval_scores.get(field_name, 0.0)
        total += weight * score
    return total


def _cost_efficiency(genome: PipelineGenome) -> float:
    cost: float = genome.harness_params.get("total_cost_usd", 0.0)
    if cost <= 0.0:
        return 1.0
    return 1.0 / (1.0 + cost)


def _latency_efficiency(genome: PipelineGenome) -> float:
    latency: float = genome.harness_params.get("avg_latency_seconds", 0.0)
    if latency <= 0.0:
        return 1.0
    return 1.0 / (1.0 + latency)


def _diversity_bonus(genome: PipelineGenome, population: list[PipelineGenome]) -> float:
    if len(population) < 2:
        return 0.0
    from .diversity import _euclidean, trait_vector

    v = trait_vector(genome)
    distances = []
    for other in population:
        if other.id != genome.id:
            distances.append(_euclidean(v, trait_vector(other)))
    if not distances:
        return 0.0
    avg_dist = sum(distances) / len(distances)
    return min(avg_dist / 5.0, 1.0)


def _elo_bonus(genome: PipelineGenome) -> float:
    avg_elo: float = genome.harness_params.get("avg_elo", 0.0)
    if avg_elo <= 0.0:
        return 0.0
    return min(max(0.0, (avg_elo - 1000.0) / 400.0), 1.0)


def compute_fitness(
    genome: PipelineGenome,
    population: list[PipelineGenome],
) -> FitnessComponents:
    passed, gate_failures = _check_hard_gate(genome)

    w_eval = _weighted_eval_score(genome)
    cost_eff = _cost_efficiency(genome)
    lat_eff = _latency_efficiency(genome)
    div_bonus = _diversity_bonus(genome, population)
    elo_bon = _elo_bonus(genome)

    if not passed:
        total = 0.0
    else:
        total = (
            w_eval * _FITNESS_WEIGHTS["eval_score"]
            + cost_eff * _FITNESS_WEIGHTS["cost_efficiency"]
            + lat_eff * _FITNESS_WEIGHTS["latency_efficiency"]
            + div_bonus * _FITNESS_WEIGHTS["diversity_bonus"]
            + elo_bon * _FITNESS_WEIGHTS["elo_bonus"]
        ) * 100.0

    return FitnessComponents(
        weighted_eval_score=w_eval,
        cost_efficiency=cost_eff,
        latency_efficiency=lat_eff,
        diversity_bonus=div_bonus,
        total=total,
        passed_hard_gate=passed,
        gate_failures=gate_failures,
    )
