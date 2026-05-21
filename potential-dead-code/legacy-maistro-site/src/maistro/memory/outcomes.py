"""In-memory outcome store (ADR-017)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from maistro.memory.types import Outcome

MAX_OUTCOMES = 10_000


class InMemoryOutcomeStore:
    def __init__(self, max_outcomes: int = MAX_OUTCOMES) -> None:
        self._outcomes: list[Outcome] = []
        self._next_id = 1
        self._max = max_outcomes

    async def record(self, outcome: Outcome) -> int:
        if len(self._outcomes) >= self._max:
            self._outcomes.pop(0)
        outcome.id = self._next_id
        self._next_id += 1
        self._outcomes.append(outcome)
        return outcome.id

    async def get_task_completion_rate(
        self,
        task_type: str = "",
        days: int = 7,
        org_id: str = "",
    ) -> dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        filtered = [
            o
            for o in self._outcomes
            if o.created_at >= cutoff
            and (not task_type or o.task_type == task_type)
            and self._org_matches(o.org_id, org_id)
        ]

        total = len(filtered)
        succeeded = sum(1 for o in filtered if o.success)
        by_model: dict[str, dict[str, Any]] = {}
        for o in filtered:
            stats = by_model.setdefault(o.model_used, {"total": 0, "succeeded": 0})
            stats["total"] += 1
            if o.success:
                stats["succeeded"] += 1
        for stats in by_model.values():
            stats["rate"] = stats["succeeded"] / max(stats["total"], 1)

        return {
            "total": total,
            "succeeded": succeeded,
            "failed": total - succeeded,
            "rate": succeeded / max(total, 1),
            "by_model": by_model,
            "days": days,
            "task_type": task_type or "all",
        }

    @staticmethod
    def _org_matches(record_org: str, caller_org: str) -> bool:
        if not caller_org:
            return True
        return record_org == caller_org
