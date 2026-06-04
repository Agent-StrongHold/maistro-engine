"""JSON-backed persistence for async builder sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from maistro_bootstrap.builders.dagflow import DagFlow, DagStage
from maistro_bootstrap.builders.message_board import BoardCard, BoardComment, MessageBoard
from maistro_bootstrap.builders.quality import QualityGateReport
from maistro_bootstrap.builders.sandbox import BuilderSandbox
from maistro_bootstrap.builders.session import BuilderSession
from maistro_bootstrap.builders.spec_session import ChatMessage, SpecDraft, SpecSession


class SessionNotFoundError(FileNotFoundError):
    """Raised when a requested builder session has not been persisted."""


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    updated_at: datetime
    open_questions: int
    todo: int
    wip: int
    done: int
    quality_passed: bool | None


class SessionStore:
    """Persist builder sessions as one JSON file per session id."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, session_id: str, session: BuilderSession) -> SessionSummary:
        path = self._session_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _session_to_payload(session_id, session)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return _summary_from_payload(payload)

    def load(self, session_id: str, *, sandbox: BuilderSandbox) -> BuilderSession:
        path = self._session_path(session_id)
        if not path.exists():
            raise SessionNotFoundError(session_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid builder session JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"invalid builder session JSON: {path}")
        return _session_from_payload(payload, sandbox=sandbox)

    def list_sessions(self) -> list[SessionSummary]:
        summaries: list[SessionSummary] = []
        if not self.root.exists():
            return summaries
        for path in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                summaries.append(_summary_from_payload(payload))
        return sorted(summaries, key=lambda item: item.updated_at, reverse=True)

    def _session_path(self, session_id: str) -> Path:
        if not session_id or "/" in session_id or "\\" in session_id:
            raise ValueError("session_id must be a non-empty file name")
        return self.root / f"{session_id}.json"


def _session_to_payload(session_id: str, session: BuilderSession) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "updated_at": datetime.now().astimezone().isoformat(),
        "approved_to_apply": session.approved_to_apply,
        "message_board": _board_to_payload(session.message_board),
        "spec_session": _spec_to_payload(session.spec_session),
        "dagflow": _dagflow_to_payload(session.dagflow),
        "transcript": session.transcript,
    }


def _session_from_payload(payload: dict[str, Any], *, sandbox: BuilderSandbox) -> BuilderSession:
    board = _board_from_payload(_dict(payload, "message_board"))
    session = BuilderSession(
        sandbox=sandbox,
        approved_to_apply=bool(payload.get("approved_to_apply", False)),
        message_board=board,
        dagflow=_dagflow_from_payload(_dict(payload, "dagflow")),
        transcript=_list(payload, "transcript"),
    )
    session.spec_session = _spec_from_payload(_dict(payload, "spec_session"), board=board)
    return session


def _summary_from_payload(payload: dict[str, Any]) -> SessionSummary:
    board = _board_from_payload(_dict(payload, "message_board"))
    columns = board.columns()
    quality = _quality_from_payload(_optional_dict(_dict(payload, "dagflow"), "quality"))
    return SessionSummary(
        session_id=str(payload["session_id"]),
        updated_at=_datetime(str(payload["updated_at"])),
        open_questions=len(board.open_cards()),
        todo=len(columns["todo"]),
        wip=len(columns["wip"]),
        done=len(columns["done"]),
        quality_passed=None if quality is None else quality.passed,
    )


def _board_to_payload(board: MessageBoard) -> dict[str, Any]:
    return {"cards": [_card_to_payload(card) for card in board.cards()]}


def _board_from_payload(payload: dict[str, Any]) -> MessageBoard:
    board = MessageBoard()
    board.replace_cards([_card_from_payload(item) for item in _list(payload, "cards")])
    return board


def _card_to_payload(card: BoardCard) -> dict[str, Any]:
    return {
        "card_id": card.card_id,
        "agent": card.agent,
        "question": card.question,
        "card_type": card.card_type,
        "status": card.status,
        "context": card.context,
        "comments": [_comment_to_payload(comment) for comment in card.comments],
        "resolution": card.resolution,
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
    }


def _card_from_payload(payload: Any) -> BoardCard:
    data = _ensure_dict(payload)
    return BoardCard(
        card_id=str(data["card_id"]),
        agent=str(data["agent"]),
        question=str(data["question"]),
        card_type=data["card_type"],
        status=data["status"],
        context={str(key): str(value) for key, value in _dict(data, "context").items()},
        comments=tuple(_comment_from_payload(item) for item in _list(data, "comments")),
        resolution=str(data["resolution"]),
        created_at=_datetime(str(data["created_at"])),
        updated_at=_datetime(str(data["updated_at"])),
    )


def _comment_to_payload(comment: BoardComment) -> dict[str, Any]:
    return {
        "author": comment.author,
        "body": comment.body,
        "created_at": comment.created_at.isoformat(),
    }


def _comment_from_payload(payload: Any) -> BoardComment:
    data = _ensure_dict(payload)
    return BoardComment(
        author=str(data["author"]),
        body=str(data["body"]),
        created_at=_datetime(str(data["created_at"])),
    )


def _spec_to_payload(spec: SpecSession) -> dict[str, Any]:
    draft = spec.draft
    return {
        "messages": [_message_to_payload(message) for message in spec.messages],
        "draft": None if draft is None else _draft_to_payload(draft),
    }


def _spec_from_payload(payload: dict[str, Any], *, board: MessageBoard) -> SpecSession:
    spec = SpecSession(board=board)
    spec.restore(
        messages=[_message_from_payload(item) for item in _list(payload, "messages")],
        draft=_draft_from_payload(payload["draft"]) if payload.get("draft") is not None else None,
    )
    return spec


def _message_to_payload(message: ChatMessage) -> dict[str, Any]:
    return {
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


def _message_from_payload(payload: Any) -> ChatMessage:
    data = _ensure_dict(payload)
    return ChatMessage(
        role=data["role"],
        content=str(data["content"]),
        created_at=_datetime(str(data["created_at"])),
    )


def _draft_to_payload(draft: SpecDraft) -> dict[str, Any]:
    return {
        "title": draft.title,
        "summary": draft.summary,
        "acceptance_criteria": list(draft.acceptance_criteria),
        "status": draft.status,
        "updated_at": draft.updated_at.isoformat(),
    }


def _draft_from_payload(payload: Any) -> SpecDraft:
    data = _ensure_dict(payload)
    return SpecDraft(
        title=str(data["title"]),
        summary=str(data["summary"]),
        acceptance_criteria=tuple(str(item) for item in _list(data, "acceptance_criteria")),
        status=data["status"],
        updated_at=_datetime(str(data["updated_at"])),
    )


def _dagflow_to_payload(dagflow: DagFlow) -> dict[str, Any]:
    return {
        "board": _board_to_payload(dagflow.board),
        "cards_by_stage": dagflow._cards_by_stage,
        "quality": None if dagflow.quality is None else _quality_to_payload(dagflow.quality),
    }


def _dagflow_from_payload(payload: dict[str, Any]) -> DagFlow:
    dagflow = DagFlow()
    dagflow.board = _board_from_payload(_dict(payload, "board"))
    dagflow._cards_by_stage = {
        cast(DagStage, key): str(value)
        for key, value in _dict(payload, "cards_by_stage").items()
    }
    dagflow.quality = _quality_from_payload(_optional_dict(payload, "quality"))
    return dagflow


def _quality_to_payload(quality: QualityGateReport) -> dict[str, Any]:
    return {
        "tests_passed": quality.tests_passed,
        "coverage_pct": quality.coverage_pct,
        "mutation_score_pct": quality.mutation_score_pct,
        "complexity_grade": quality.complexity_grade,
        "dry_ok": quality.dry_ok,
        "code_smells_ok": quality.code_smells_ok,
        "bandit_ok": quality.bandit_ok,
        "ruff_ok": quality.ruff_ok,
        "mypy_ok": quality.mypy_ok,
    }


def _quality_from_payload(payload: dict[str, Any] | None) -> QualityGateReport | None:
    if payload is None:
        return None
    return QualityGateReport(
        tests_passed=bool(payload["tests_passed"]),
        coverage_pct=float(payload["coverage_pct"]),
        mutation_score_pct=float(payload["mutation_score_pct"]),
        complexity_grade=str(payload["complexity_grade"]),
        dry_ok=bool(payload["dry_ok"]),
        code_smells_ok=bool(payload["code_smells_ok"]),
        bandit_ok=bool(payload["bandit_ok"]),
        ruff_ok=bool(payload["ruff_ok"]),
        mypy_ok=bool(payload["mypy_ok"]),
    )


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    return _ensure_dict(payload[key])


def _optional_dict(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = payload.get(key)
    if value is None:
        return None
    return _ensure_dict(value)


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be list")
    return value


def _ensure_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("expected object")
    return value


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
