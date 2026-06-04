"""Kanban-style message board for builder agents and humans."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

CardStatus = Literal["open", "resolved", "todo", "wip", "done"]
CardType = Literal["question", "todo"]


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class BoardComment:
    author: str
    body: str
    created_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class BoardCard:
    card_id: str
    agent: str
    question: str
    card_type: CardType = "question"
    status: CardStatus = "open"
    context: dict[str, str] = field(default_factory=dict)
    comments: tuple[BoardComment, ...] = ()
    resolution: str = ""
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


class MessageBoard:
    """In-memory Kanban board for agent questions during a builder session."""

    def __init__(self) -> None:
        self._cards: dict[str, BoardCard] = {}

    def replace_cards(self, cards: list[BoardCard]) -> None:
        """Replace board contents with previously persisted cards."""
        self._cards = {card.card_id: card for card in cards}

    def cards(self) -> tuple[BoardCard, ...]:
        """Return all cards in stable creation order for persistence/rendering."""
        return tuple(sorted(self._cards.values(), key=lambda item: item.created_at))

    def post_question(
        self,
        *,
        agent: str,
        question: str,
        context: dict[str, str] | None = None,
    ) -> BoardCard:
        card = BoardCard(
            card_id=f"card_{uuid4().hex[:10]}",
            agent=agent,
            question=question,
            context=context or {},
        )
        self._cards[card.card_id] = card
        return card

    def add_todo(
        self,
        *,
        title: str,
        owner: str,
        context: dict[str, str] | None = None,
    ) -> BoardCard:
        card = BoardCard(
            card_id=f"card_{uuid4().hex[:10]}",
            agent=owner,
            question=title,
            card_type="todo",
            status="todo",
            context=context or {},
        )
        self._cards[card.card_id] = card
        return card

    def get(self, card_id: str) -> BoardCard:
        return self._cards[card_id]

    def open_cards(self) -> list[BoardCard]:
        return [
            card
            for card in sorted(self._cards.values(), key=lambda item: item.created_at)
            if card.status == "open"
        ]

    def columns(self) -> dict[str, list[BoardCard]]:
        cards = sorted(self._cards.values(), key=lambda item: item.created_at)
        return {
            "todo": [card for card in cards if card.status == "todo"],
            "wip": [card for card in cards if card.status == "wip"],
            "done": [card for card in cards if card.status == "done"],
        }

    def start(self, card_id: str) -> BoardCard:
        return self._move(card_id, "wip")

    def finish(self, card_id: str, *, summary: str) -> BoardCard:
        current = self.get(card_id)
        updated = replace(
            current,
            status="done",
            resolution=summary,
            updated_at=_now(),
        )
        self._cards[card_id] = updated
        return updated

    def add_human_comment(self, card_id: str, body: str) -> BoardCard:
        current = self.get(card_id)
        updated = replace(
            current,
            comments=(*current.comments, BoardComment(author="human", body=body)),
            updated_at=_now(),
        )
        self._cards[card_id] = updated
        return updated

    def resolve(self, card_id: str, *, resolution: str) -> BoardCard:
        current = self.get(card_id)
        updated = replace(
            current,
            status="resolved",
            resolution=resolution,
            updated_at=_now(),
        )
        self._cards[card_id] = updated
        return updated

    def _move(self, card_id: str, status: CardStatus) -> BoardCard:
        current = self.get(card_id)
        updated = replace(current, status=status, updated_at=_now())
        self._cards[card_id] = updated
        return updated
