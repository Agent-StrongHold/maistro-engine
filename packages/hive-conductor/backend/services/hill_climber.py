"""Hill-Climbing Strategy — generalization over overfitting.

Implements the eval rotation system that ensures DAGs improve broadly,
not just on the specific evals they've been tested against.

Key rules:
  - Never optimize on the same eval combination twice in a row
  - Always include at least 1 eval the DAG has never seen
  - Track per-eval scores over time — flag if one drops while others rise
  - Accept mutations only if: improves on target AND doesn't regress on held-out
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class EvalScore:
    eval_name: str
    score: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PassResult:
    dag_id: str
    pass_number: int
    target_evals: list[str]
    held_out_evals: list[str]
    target_scores: dict[str, int]
    held_out_scores: dict[str, int]
    mutation_accepted: bool
    reason: str


class HillClimber:
    """Manages eval rotation and anti-overfitting for a single DAG."""

    # Two phases of optimization:
    # BUILD: models locked to best (o3-pro, opus-4-6). Optimize prompts/structure only.
    # OPTIMIZE: models are a variable. Try cheaper, keep if quality holds within threshold.
    PHASE_BUILD = "build"
    PHASE_OPTIMIZE = "optimize"

    # Best models — used during build phase, quality ceiling reference during optimize
    BEST_MODELS = ["o3-pro", "claude-opus-4-6"]

    # Candidates for optimize phase — ordered by cost (cheapest first)
    OPTIMIZE_CANDIDATES = [
        "gemini-3.5-flash",      # cheapest
        "gpt-5-mini",            # cheap + good
        "claude-haiku-4-5",      # fast + decent
        "gpt-5-nano",            # ultra cheap
        "gpt-4.1-mini",         # balanced
        "claude-sonnet-4-6",     # strong but cheaper than opus
        "gpt-5",                 # strong
        "o4-mini",               # reasoning, cheaper than o3
    ]

    # Quality floor: optimize-phase model must score within this % of best
    QUALITY_FLOOR_PCT = 0.90  # 90% of best model's score

    def __init__(self, dag_id: str, all_evals: list[str], target_count: int = 3, held_out_count: int = 2, phase: str = "build"):
        self.dag_id = dag_id
        self.all_evals = list(all_evals)
        self.target_count = target_count
        self.held_out_count = held_out_count
        self.phase = phase
        self.pass_number = 0
        self.history: list[PassResult] = []
        self.score_history: dict[str, list[EvalScore]] = {e: [] for e in all_evals}
        self._last_target_combo: frozenset[str] = frozenset()
        self._seen_evals: set[str] = set()
        self._rotation_pool: list[str] = list(all_evals[:target_count + held_out_count])

    def select_evals(self) -> tuple[list[str], list[str]]:
        """Select target and held-out evals for this pass. Enforces anti-overfitting rules."""
        self.pass_number += 1

        # Expand rotation pool each pass
        if self.pass_number > 1 and len(self._rotation_pool) < len(self.all_evals):
            remaining = [e for e in self.all_evals if e not in self._rotation_pool]
            if remaining:
                self._rotation_pool.append(remaining[0])

        # Select targets — never same combo twice in a row
        available = list(self._rotation_pool)
        for _ in range(50):  # max attempts
            targets = random.sample(available, min(self.target_count, len(available)))
            if frozenset(targets) != self._last_target_combo:
                break

        # Must include at least 1 never-seen eval
        unseen = [e for e in self.all_evals if e not in self._seen_evals]
        if unseen and not any(e in unseen for e in targets):
            targets[-1] = unseen[0]

        # Select held-out from remaining pool
        remaining = [e for e in self._rotation_pool if e not in targets]
        held_out = random.sample(remaining, min(self.held_out_count, len(remaining)))

        self._last_target_combo = frozenset(targets)
        self._seen_evals.update(targets)
        self._seen_evals.update(held_out)

        return targets, held_out

    def evaluate_mutation(
        self,
        target_evals: list[str],
        held_out_evals: list[str],
        baseline_scores: dict[str, int],
        mutated_scores: dict[str, int],
    ) -> PassResult:
        """Decide whether to accept a mutation based on scores."""
        # Check target improvement
        target_improved = any(
            mutated_scores.get(e, 0) > baseline_scores.get(e, 0)
            for e in target_evals
        )
        target_no_regression = all(
            mutated_scores.get(e, 0) >= baseline_scores.get(e, 0) - 5  # 5-point tolerance
            for e in target_evals
        )

        # Check held-out non-regression
        held_out_ok = all(
            mutated_scores.get(e, 0) >= baseline_scores.get(e, 0) - 10  # 10-point tolerance
            for e in held_out_evals
        )

        accepted = target_improved and target_no_regression and held_out_ok

        if not target_improved:
            reason = "no improvement on target evals"
        elif not target_no_regression:
            reason = "regression on target evals"
        elif not held_out_ok:
            reason = "regression on held-out evals"
        else:
            reason = "improves target, no held-out regression"

        # Record scores
        now = datetime.now(UTC)
        scores_to_record = mutated_scores if accepted else baseline_scores
        for eval_name, score in scores_to_record.items():
            if eval_name in self.score_history:
                self.score_history[eval_name].append(EvalScore(eval_name, score, now))

        target_scores = {e: mutated_scores.get(e, 0) for e in target_evals}
        held_out_scores = {e: mutated_scores.get(e, 0) for e in held_out_evals}

        result = PassResult(
            dag_id=self.dag_id,
            pass_number=self.pass_number,
            target_evals=target_evals,
            held_out_evals=held_out_evals,
            target_scores=target_scores,
            held_out_scores=held_out_scores,
            mutation_accepted=accepted,
            reason=reason,
        )
        self.history.append(result)
        return result

    def check_score_drift(self) -> list[dict[str, Any]]:
        """Flag evals where score is dropping while others rise."""
        alerts = []
        for eval_name, scores in self.score_history.items():
            if len(scores) < 3:
                continue
            recent = [s.score for s in scores[-5:]]
            if len(recent) >= 3 and recent[-1] < recent[0] - 15:
                # Score dropped >15 points over recent history
                alerts.append({
                    "eval": eval_name,
                    "trend": "declining",
                    "drop": recent[0] - recent[-1],
                    "recent_scores": recent,
                })
        return alerts

    def is_done(self, threshold: int = 75) -> bool:
        """A DAG is 'done' when it scores well on any randomly selected eval subset."""
        if self.pass_number < 10:
            return False
        # Check last 5 passes — all accepted with scores above threshold
        recent = self.history[-5:]
        return all(
            r.mutation_accepted and
            all(s >= threshold for s in r.target_scores.values())
            for r in recent
        )

    @property
    def stats(self) -> dict[str, Any]:
        accepted = sum(1 for r in self.history if r.mutation_accepted)
        return {
            "dag_id": self.dag_id,
            "passes": self.pass_number,
            "accepted": accepted,
            "rejected": self.pass_number - accepted,
            "acceptance_rate": accepted / max(self.pass_number, 1),
            "rotation_pool_size": len(self._rotation_pool),
            "evals_seen": len(self._seen_evals),
            "is_done": self.is_done(),
        }


class HillClimbOrchestrator:
    """Manages hill-climbing across all DAGs."""

    def __init__(self):
        self.climbers: dict[str, HillClimber] = {}

    def register_dag(self, dag_id: str, eval_names: list[str]) -> HillClimber:
        climber = HillClimber(dag_id, eval_names)
        self.climbers[dag_id] = climber
        return climber

    def get_climber(self, dag_id: str) -> HillClimber | None:
        return self.climbers.get(dag_id)

    def full_sweep(self) -> dict[str, dict[str, Any]]:
        """Report stats for all DAGs."""
        return {dag_id: c.stats for dag_id, c in self.climbers.items()}

    def get_alerts(self) -> list[dict[str, Any]]:
        """Get all score drift alerts across all DAGs."""
        alerts = []
        for dag_id, climber in self.climbers.items():
            for alert in climber.check_score_drift():
                alert["dag_id"] = dag_id
                alerts.append(alert)
        return alerts
