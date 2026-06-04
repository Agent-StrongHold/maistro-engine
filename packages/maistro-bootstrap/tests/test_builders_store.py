"""Durable state for async builder session monitoring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maistro_bootstrap.builders.actions import ActionRequest
from maistro_bootstrap.builders.message_board import BoardCard, BoardComment
from maistro_bootstrap.builders.quality import QualityGateReport
from maistro_bootstrap.builders.sandbox import LocalWorktreeSandbox
from maistro_bootstrap.builders.session import BuilderSession
from maistro_bootstrap.builders.store import (
    SessionNotFoundError,
    SessionStore,
    _card_from_payload,
    _ensure_dict,
    _list,
    _quality_from_payload,
)


def _session(tmp_path: Path) -> BuilderSession:
    return BuilderSession(sandbox=LocalWorktreeSandbox(tmp_path))


def test_session_store_round_trips_board_comments_spec_and_quality(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / ".maistro-builders")
    session = _session(tmp_path)
    question = session.message_board.post_question(
        agent="mason",
        question="Should I split the Ranger and Scout stages?",
        context={"stage": "plan"},
    )
    todo = session.message_board.add_todo(title="Implement durable board", owner="mason")
    session.message_board.start(todo.card_id)
    done = session.message_board.finish(todo.card_id, summary="JSON store implemented.")
    session.message_board.add_human_comment(done.card_id, "Add CLI comment coverage.")
    session.apply_action(
        ActionRequest(
            action="define_spec",
            args={
                "title": "Async builders TUI",
                "summary": "Let humans monitor and guide builder DAG work.",
                "acceptance_criteria": ["Comments survive reload"],
            },
        )
    )
    session.dagflow.record_quality(
        QualityGateReport(
            tests_passed=True,
            coverage_pct=91.0,
            mutation_score_pct=90.0,
            complexity_grade="B+",
            dry_ok=True,
            code_smells_ok=True,
            bandit_ok=True,
            ruff_ok=True,
            mypy_ok=True,
        )
    )

    saved = store.save("session-alpha", session)
    loaded = store.load("session-alpha", sandbox=LocalWorktreeSandbox(tmp_path))

    assert saved.session_id == "session-alpha"
    assert saved.quality_passed is True
    assert loaded.message_board.get(question.card_id).context == {"stage": "plan"}
    assert loaded.message_board.get(done.card_id).comments[-1].body == "Add CLI comment coverage."
    assert loaded.spec_session.draft is not None
    assert loaded.spec_session.draft.title == "Async builders TUI"
    assert loaded.dagflow.quality is not None
    assert loaded.dagflow.quality.mutation_score_pct == 90.0
    assert loaded.snapshot()["board_columns"] == {"todo": 0, "wip": 0, "done": 1}


def test_session_store_save_creates_nested_state_dir_and_pins_json_keys(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "nested" / "state")
    session = _session(tmp_path)
    session.approved_to_apply = True

    summary = store.save("approved", session)
    payload = json.loads((tmp_path / "nested" / "state" / "approved.json").read_text())
    loaded = store.load("approved", sandbox=LocalWorktreeSandbox(tmp_path))

    assert summary.session_id == "approved"
    assert sorted(payload) == [
        "approved_to_apply",
        "dagflow",
        "message_board",
        "session_id",
        "spec_session",
        "transcript",
        "updated_at",
    ]
    assert payload["approved_to_apply"] is True
    assert loaded.approved_to_apply is True


def test_session_store_lists_saved_sessions_in_update_order(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "state")
    first = _session(tmp_path)
    second = _session(tmp_path)
    store.save("older", first)
    store.save("newer", second)
    first.message_board.post_question(agent="tester", question="Recheck mutants?")
    store.save("older", first)

    sessions = store.list_sessions()

    assert [item.session_id for item in sessions] == ["older", "newer"]
    assert sessions[0].open_questions == 1


def test_session_store_rejects_missing_or_corrupted_sessions(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "state")

    with pytest.raises(SessionNotFoundError):
        store.load("missing", sandbox=LocalWorktreeSandbox(tmp_path))

    session_file = tmp_path / "state" / "broken.json"
    session_file.parent.mkdir()
    session_file.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid builder session JSON"):
        store.load("broken", sandbox=LocalWorktreeSandbox(tmp_path))


def test_session_store_rejects_path_separator_session_ids(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "state")
    session = _session(tmp_path)

    for session_id in ["", "nested/id", "nested\\id"]:
        with pytest.raises(ValueError, match="session_id"):
            store.save(session_id, session)


def test_store_deserializers_pin_exact_card_and_quality_fields() -> None:
    card = _card_from_payload(
        {
            "card_id": "card_123",
            "agent": "mason",
            "question": "Review done todo?",
            "card_type": "todo",
            "status": "done",
            "context": {"spec": "Builders"},
            "comments": [
                {
                    "author": "human",
                    "body": "Add mutant evidence.",
                    "created_at": "2026-06-03T00:00:00+00:00",
                }
            ],
            "resolution": "Reviewed.",
            "created_at": "2026-06-03T00:00:00+00:00",
            "updated_at": "2026-06-03T00:01:00+00:00",
        }
    )
    quality = _quality_from_payload(
        {
            "tests_passed": True,
            "coverage_pct": 90.5,
            "mutation_score_pct": 91.5,
            "complexity_grade": "B+",
            "dry_ok": True,
            "code_smells_ok": True,
            "bandit_ok": True,
            "ruff_ok": True,
            "mypy_ok": True,
        }
    )

    assert isinstance(card, BoardCard)
    assert isinstance(card.comments[0], BoardComment)
    assert card.card_id == "card_123"
    assert card.agent == "mason"
    assert card.question == "Review done todo?"
    assert card.card_type == "todo"
    assert card.status == "done"
    assert card.context == {"spec": "Builders"}
    assert card.comments[0].author == "human"
    assert card.comments[0].body == "Add mutant evidence."
    assert card.resolution == "Reviewed."
    assert quality is not None
    assert quality.tests_passed is True
    assert quality.coverage_pct == 90.5
    assert quality.mutation_score_pct == 91.5
    assert quality.complexity_grade == "B+"
    assert quality.passed is True


def test_store_validation_helpers_reject_wrong_shapes() -> None:
    with pytest.raises(ValueError, match="expected object"):
        _ensure_dict([])
    with pytest.raises(ValueError, match="cards must be list"):
        _list({"cards": "not-list"}, "cards")
