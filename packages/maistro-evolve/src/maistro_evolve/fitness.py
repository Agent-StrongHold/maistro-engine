from __future__ import annotations

from .types import FitnessComponents, PipelineGenome


def _check_hard_gate(genome: PipelineGenome) -> tuple[bool, list[str]]:
    failures: list[str] = []
    scores = genome.eval_scores

    if "ifeval" not in scores:
        failures.append("missing ifeval score")
    elif scores["ifeval"] <= 0.3:
        failures.append(f"ifeval score too low: {scores['ifeval']:.3f}")

    if "bfcl" not in scores:
        failures.append("missing bfcl score")
    elif scores["bfcl"] <= 0.3:
        failures.append(f"bfcl score too low: {scores['bfcl']:.3f}")

    return len(failures) == 0, failures


def _weighted_eval_score(genome: PipelineGenome) -> float:
    if not genome.eval_scores:
        return 0.0
    total = 0.0
    for field_name in genome.eval_weights.model_fields:
        weight = getattr(genome.eval_weights, field_name)
        score = genome.eval_scores.get(field_name, 0.0)
        total += weight * score
    return total


def _cost_efficiency(genome: PipelineGenome) -> float:
    cost = genome.harness_params.get("total_cost_usd", 0.0)
    if cost <= 0.0:
        return 1.0
    return 1.0 / (1.0 + cost)


def _latency_efficiency(genome: PipelineGenome) -> float:
    latency = genome.harness_params.get("avg_latency_seconds", 0.0)
    if latency <= 0.0:
        return 1.0
    return 1.0 / (1.0 + latency)


def _diversity_bonus(genome: PipelineGenome, population: list[PipelineGenome]) -> float:
    if len(population) < 2:
        return 0.0
    from .diversity import trait_vector, _euclidean

    v = trait_vector(genome)
    distances = []
    for other in population:
        if other.id != genome.id:
            distances.append(_euclidean(v, trait_vector(other)))
    if not distances:
        return 0.0
    avg_dist = sum(distances) / len(distances)
    return min(avg_dist / 5.0, 1.0)


def compute_fitness(
    genome: PipelineGenome,
    population: list[PipelineGenome],
) -> FitnessComponents:
    passed, gate_failures = _check_hard_gate(genome)

    w_eval = _weighted_eval_score(genome)
    cost_eff = _cost_efficiency(genome)
    lat_eff = _latency_efficiency(genome)
    div_bonus = _diversity_bonus(genome, population)

    if not passed:
        total = 0.0
    else:
        total = (
            w_eval * 0.7
            + cost_eff * 0.15
            + lat_eff * 0.1
            + div_bonus * 0.05
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
