"""Memory store protocols for dependency injection (ADR-014)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from maistro.memory.types import EpisodicMemory, Learning, Outcome


@runtime_checkable
class LearningStore(Protocol):
    async def store(self, learning: Learning) -> int: ...

    async def find_relevant(
        self,
        user_text: str,
        *,
        agent_id: str | None = None,
        org_id: str = "",
        max_results: int = 10,
    ) -> list[Learning]: ...

    async def mark_used(self, learning_ids: list[int]) -> None: ...

    async def check_auto_promotions(
        self, threshold: int = 5, *, org_id: str = ""
    ) -> list[Learning]: ...

    async def get_promoted(
        self, task_type: str | None = None, *, org_id: str = ""
    ) -> list[Learning]: ...


@runtime_checkable
class EpisodicStore(Protocol):
    async def store(self, memory: EpisodicMemory) -> str: ...

    async def retrieve(
        self,
        query: str,
        *,
        agent_id: str | None = None,
        user_id: str | None = None,
        team_id: str | None = None,
        org_id: str | None = None,
        limit: int = 5,
    ) -> list[EpisodicMemory]: ...

    async def reinforce(self, memory_id: str, delta: float = 0.05) -> None: ...


@runtime_checkable
class OutcomeStore(Protocol):
    async def record(self, outcome: Outcome) -> int: ...

    async def get_task_completion_rate(
        self,
        task_type: str = "",
        days: int = 7,
        org_id: str = "",
    ) -> dict[str, Any]: ...
