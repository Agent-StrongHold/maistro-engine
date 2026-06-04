"""Chat-driven spec and acceptance-criteria session state."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal

from maistro_bootstrap.builders.message_board import BoardCard, MessageBoard

SpecStatus = Literal["draft", "accepted"]
ChatRole = Literal["human", "agent"]


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str
    created_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class SpecDraft:
    title: str
    summary: str
    acceptance_criteria: tuple[str, ...]
    status: SpecStatus = "draft"
    updated_at: datetime = field(default_factory=_now)


class SpecSession:
    """State for developing a spec and acceptance criteria in chat."""

    def __init__(self, *, board: MessageBoard | None = None) -> None:
        self._messages: list[ChatMessage] = []
        self._draft: SpecDraft | None = None
        self._board = board or MessageBoard()

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        return tuple(self._messages)

    @property
    def draft(self) -> SpecDraft | None:
        return self._draft

    @property
    def board(self) -> MessageBoard:
        return self._board

    def add_chat(self, role: ChatRole, content: str) -> ChatMessage:
        message = ChatMessage(role=role, content=content)
        self._messages.append(message)
        return message

    def restore(self, *, messages: list[ChatMessage], draft: SpecDraft | None) -> None:
        """Restore persisted spec-chat state."""
        self._messages = list(messages)
        self._draft = draft

    def define_spec(
        self,
        *,
        title: str,
        summary: str,
        acceptance_criteria: list[str],
    ) -> SpecDraft:
        criteria = tuple(item.strip() for item in acceptance_criteria if item.strip())
        if not title.strip():
            raise ValueError("spec title is required")
        if not summary.strip():
            raise ValueError("spec summary is required")
        if not criteria:
            raise ValueError("at least one acceptance criterion is required")
        self._draft = SpecDraft(
            title=title.strip(),
            summary=summary.strip(),
            acceptance_criteria=criteria,
        )
        return self._draft

    def accept(self) -> SpecDraft:
        if self._draft is None:
            raise ValueError("no spec draft to accept")
        self._draft = replace(self._draft, status="accepted", updated_at=_now())
        return self._draft

    def to_todos(self, *, owner: str) -> list[BoardCard]:
        if self._draft is None:
            return []
        return [
            self._board.add_todo(
                title=criterion,
                owner=owner,
                context={"spec": self._draft.title},
            )
            for criterion in self._draft.acceptance_criteria
        ]

    def render_review(self) -> str:
        if self._draft is None:
            return "No spec draft."
        criteria = "\n".join(f"- {item}" for item in self._draft.acceptance_criteria)
        return (
            f"# {self._draft.title}\n\n"
            f"Status: {self._draft.status}\n\n"
            f"{self._draft.summary}\n\n"
            f"Acceptance criteria:\n{criteria}"
        )
