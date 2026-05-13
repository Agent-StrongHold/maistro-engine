"""In-memory learning store — self-improving corrections (ADR-015)."""

from __future__ import annotations

import logging

from maistro.memory.types import Learning

logger = logging.getLogger(__name__)

MAX_LEARNINGS = 10_000


class InMemoryLearningStore:
    """In-memory learning store. All queries are org-scoped for multi-tenant isolation."""

    def __init__(self, max_learnings: int = MAX_LEARNINGS) -> None:
        self._learnings: list[Learning] = []
        self._next_id = 1
        self._max = max_learnings

    async def store(self, learning: Learning) -> int:
        new_keys = set(learning.trigger_keys)
        for existing in self._learnings:
            if existing.tool_name != learning.tool_name:
                continue
            if existing.agent_id != learning.agent_id:
                continue
            if existing.org_id != learning.org_id:
                continue
            if existing.status != "active":
                continue
            existing_keys = set(existing.trigger_keys)
            union = existing_keys | new_keys
            overlap = len(existing_keys & new_keys) / max(len(union), 1)
            if overlap >= 0.5:
                existing.learning = learning.learning
                existing.trigger_keys = learning.trigger_keys
                return existing.id or 0

        if len(self._learnings) >= self._max:
            self._learnings.pop(0)

        learning.id = self._next_id
        self._next_id += 1
        self._learnings.append(learning)
        return learning.id

    async def find_relevant(
        self,
        user_text: str,
        *,
        agent_id: str | None = None,
        org_id: str = "",
        max_results: int = 10,
    ) -> list[Learning]:
        text_lower = user_text.lower()
        scored: list[tuple[float, Learning]] = []
        for lr in self._learnings:
            if lr.status != "active":
                continue
            if agent_id and lr.agent_id != agent_id:
                continue
            if org_id and lr.org_id != org_id:
                continue
            if not org_id and lr.org_id:
                continue
            score = sum(1.0 for k in lr.trigger_keys if k and k in text_lower)
            if score > 0:
                scored.append((score, lr))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:max_results]]

    async def mark_used(self, learning_ids: list[int]) -> None:
        id_set = set(learning_ids)
        for lr in self._learnings:
            if lr.id in id_set:
                lr.hit_count += 1

    async def check_auto_promotions(
        self,
        threshold: int = 5,
        *,
        org_id: str = "",
    ) -> list[Learning]:
        promoted: list[Learning] = []
        for lr in self._learnings:
            if lr.status != "active" or lr.hit_count < threshold:
                continue
            if org_id and lr.org_id != org_id:
                continue
            if not org_id and lr.org_id:
                continue
            lr.status = "promoted"
            promoted.append(lr)
        return promoted

    async def get_promoted(
        self,
        task_type: str | None = None,
        *,
        org_id: str = "",
    ) -> list[Learning]:
        results: list[Learning] = []
        for lr in self._learnings:
            if lr.status != "promoted":
                continue
            if org_id and lr.org_id != org_id:
                continue
            if not org_id and lr.org_id:
                continue
            results.append(lr)
        return results

    async def list_all(self, org_id: str = "", limit: int = 200) -> list[Learning]:
        results: list[Learning] = []
        for lr in self._learnings:
            if org_id and org_id != "__system__" and lr.org_id != org_id:
                continue
            results.append(lr)
            if len(results) >= limit:
                break
        return results
