"""In-memory episodic store (ADR-016)."""

from __future__ import annotations

from maistro.memory.episodic.tiers import reinforce as _reinforce
from maistro.memory.scopes import build_scope_filter, matches_scope
from maistro.memory.types import EpisodicMemory


def _scope_identity(mem: EpisodicMemory) -> tuple[str, str, str, str | None, str | None]:
    """Scope key for dedup: same content under a different owner is distinct."""
    return (mem.scope, mem.org_id, mem.team_id, mem.agent_id, mem.user_id)


class InMemoryEpisodicStore:
    def __init__(self) -> None:
        self._memories: list[EpisodicMemory] = []

    async def store(self, memory: EpisodicMemory) -> str:
        """Store a memory, deduping on (content_hash, scope identity).

        If an active (non-deleted) memory with identical content already
        exists in the same scope, skip the insert and return the existing
        memory_id. This stops duplicate observations from accumulating and
        double-weighting each other during retrieval.
        """
        for existing in self._memories:
            if existing.deleted:
                continue
            if (
                existing.content_hash == memory.content_hash
                and _scope_identity(existing) == _scope_identity(memory)
            ):
                return existing.memory_id
        self._memories.append(memory)
        return memory.memory_id

    async def retrieve(
        self,
        query: str,
        *,
        agent_id: str | None = None,
        user_id: str | None = None,
        team_id: str | None = None,
        org_id: str | None = None,
        limit: int = 5,
    ) -> list[EpisodicMemory]:
        scope_filters = build_scope_filter(
            agent_id=agent_id,
            user_id=user_id,
            team_id=team_id,
            org_id=org_id,
        )
        query_words = set(query.lower().split())
        scored: list[tuple[float, EpisodicMemory]] = []

        for mem in self._memories:
            if mem.deleted:
                continue
            if not matches_scope(mem, scope_filters):
                continue
            mem_words = set(mem.content.lower().split())
            overlap = len(mem_words & query_words)
            if overlap > 0:
                scored.append((overlap * mem.weight, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in scored[:limit]]

    async def reinforce(self, memory_id: str, delta: float = 0.05) -> None:
        for i, mem in enumerate(self._memories):
            if mem.memory_id == memory_id:
                self._memories[i] = _reinforce(mem, delta)
                break
