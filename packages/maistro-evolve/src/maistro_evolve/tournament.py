from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


_DEFAULT_ELO = 1200.0
_K_FACTOR = 32.0


@dataclass
class GenomeRating:
    genome_id: str
    benchmark: str
    elo: float = _DEFAULT_ELO
    wins: int = 0
    losses: int = 0
    draws: int = 0

    @property
    def total_battles(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def win_rate(self) -> float:
        if self.total_battles == 0:
            return 0.0
        return (self.wins + 0.5 * self.draws) / self.total_battles


@dataclass
class GenomeBattle:
    id: int = 0
    benchmark: str = ""
    genome_a_id: str = ""
    genome_b_id: str = ""
    winner_id: str = ""
    score_a: float = 0.0
    score_b: float = 0.0
    timestamp: float = field(default_factory=time.time)


class EloTournament:
    def __init__(self, k_factor: float = _K_FACTOR) -> None:
        self._ratings: dict[tuple[str, str], GenomeRating] = {}
        self._battles: list[GenomeBattle] = []
        self._next_id: int = 1
        self._k_factor = k_factor

    def _get_rating(self, genome_id: str, benchmark: str) -> GenomeRating:
        key = (genome_id, benchmark)
        if key not in self._ratings:
            self._ratings[key] = GenomeRating(genome_id=genome_id, benchmark=benchmark)
        return self._ratings[key]

    def record_battle(
        self,
        benchmark: str,
        genome_a_id: str,
        genome_b_id: str,
        score_a: float,
        score_b: float,
    ) -> GenomeBattle:
        if score_a > score_b:
            winner_id = genome_a_id
        elif score_b > score_a:
            winner_id = genome_b_id
        else:
            winner_id = "draw"

        battle = GenomeBattle(
            id=self._next_id,
            benchmark=benchmark,
            genome_a_id=genome_a_id,
            genome_b_id=genome_b_id,
            winner_id=winner_id,
            score_a=score_a,
            score_b=score_b,
        )
        self._next_id += 1
        self._battles.append(battle)

        ra = self._get_rating(genome_a_id, benchmark)
        rb = self._get_rating(genome_b_id, benchmark)

        expected_a = 1 / (1 + math.pow(10, (rb.elo - ra.elo) / 400))
        expected_b = 1 - expected_a

        if winner_id == genome_a_id:
            actual_a, actual_b = 1.0, 0.0
            ra.wins += 1
            rb.losses += 1
        elif winner_id == genome_b_id:
            actual_a, actual_b = 0.0, 1.0
            ra.losses += 1
            rb.wins += 1
        else:
            actual_a, actual_b = 0.5, 0.5
            ra.draws += 1
            rb.draws += 1

        ra.elo += self._k_factor * (actual_a - expected_a)
        rb.elo += self._k_factor * (actual_b - expected_b)

        return battle

    def get_elo(self, genome_id: str, benchmark: str) -> float:
        return self._get_rating(genome_id, benchmark).elo

    def get_avg_elo(self, genome_id: str) -> float:
        ratings = [r for r in self._ratings.values() if r.genome_id == genome_id]
        if not ratings:
            return _DEFAULT_ELO
        return sum(r.elo for r in ratings) / len(ratings)

    def get_leaderboard(self, benchmark: str | None = None) -> list[dict[str, Any]]:
        genome_elos: dict[str, list[float]] = {}
        for key, rating in self._ratings.items():
            if benchmark is not None and rating.benchmark != benchmark:
                continue
            genome_elos.setdefault(rating.genome_id, []).append(rating.elo)

        entries = []
        for gid, elos in genome_elos.items():
            avg = sum(elos) / len(elos)
            r = self._get_rating(gid, benchmark or "overall")
            entries.append({
                "genome_id": gid,
                "avg_elo": round(avg, 1),
                "total_battles": r.total_battles,
                "win_rate": r.win_rate,
            })
        entries.sort(key=lambda e: e["avg_elo"], reverse=True)
        return entries

    def tournament_select(
        self,
        genome_ids: list[str],
        benchmark: str | None = None,
        tournament_size: int = 3,
    ) -> str | None:
        if not genome_ids:
            return None
        import random
        candidates = random.sample(
            genome_ids, min(tournament_size, len(genome_ids))
        )
        best = max(
            candidates,
            key=lambda gid: self.get_avg_elo(gid) if benchmark is None else self.get_elo(gid, benchmark),
        )
        return best

    def get_battle_history(
        self,
        genome_id: str | None = None,
        benchmark: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        filtered = self._battles
        if genome_id:
            filtered = [
                b for b in filtered
                if b.genome_a_id == genome_id or b.genome_b_id == genome_id
            ]
        if benchmark:
            filtered = [b for b in filtered if b.benchmark == benchmark]
        return [
            {
                "id": b.id,
                "benchmark": b.benchmark,
                "genome_a": b.genome_a_id,
                "genome_b": b.genome_b_id,
                "winner": b.winner_id,
                "score_a": b.score_a,
                "score_b": b.score_b,
                "timestamp": b.timestamp,
            }
            for b in filtered[-limit:]
        ]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_battles": len(self._battles),
            "total_genomes_rated": len({r.genome_id for r in self._ratings.values()}),
            "benchmarks_tracked": len({r.benchmark for r in self._ratings.values()}),
        }
