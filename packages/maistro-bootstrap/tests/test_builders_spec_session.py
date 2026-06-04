"""Chat-to-spec workflow for builder sessions."""

from __future__ import annotations

import pytest

from maistro_bootstrap.builders.spec_session import ChatMessage, SpecSession


def test_chat_messages_are_retained_while_spec_is_developed() -> None:
    spec = SpecSession()

    spec.add_chat("human", "Build a CLI/TUI builder session.")
    spec.add_chat("agent", "What should count as done?")

    assert [msg.role for msg in spec.messages] == ["human", "agent"]
    assert spec.messages[0].content == "Build a CLI/TUI builder session."


def test_spec_and_acceptance_criteria_are_reviewable() -> None:
    spec = SpecSession()

    draft = spec.define_spec(
        title="Interactive builder session",
        summary="Developer can develop a spec in chat and monitor async progress.",
        acceptance_criteria=[
            "Human can leave async comments on done cards.",
            "Quality gates require 90% coverage and mutation evidence.",
        ],
    )

    assert draft.status == "draft"
    assert draft.title == "Interactive builder session"
    assert len(draft.acceptance_criteria) == 2
    assert "90% coverage" in spec.render_review()


def test_accepting_spec_creates_todos_for_acceptance_criteria() -> None:
    spec = SpecSession()
    spec.define_spec(
        title="Async builders",
        summary="Autonomous DAG flow with human board comments.",
        acceptance_criteria=["Spec approved", "Tests pass"],
    )

    accepted = spec.accept()
    todos = spec.to_todos(owner="frank")

    assert accepted.status == "accepted"
    assert [todo.question for todo in todos] == ["Spec approved", "Tests pass"]
    assert all(todo.status == "todo" for todo in todos)


def test_restore_replaces_message_list_and_preserves_draft() -> None:
    spec = SpecSession()
    spec.add_chat("human", "old message that should be replaced")
    draft = spec.define_spec(
        title="Durable spec",
        summary="Survives a reload.",
        acceptance_criteria=["State is preserved"],
    )

    restored_messages = [
        ChatMessage(role="human", content="first restored message"),
        ChatMessage(role="agent", content="second restored message"),
    ]
    spec.restore(messages=restored_messages, draft=draft)

    assert len(spec.messages) == 2
    assert spec.messages[0].content == "first restored message"
    assert spec.messages[1].role == "agent"
    assert spec.draft is not None
    assert spec.draft.title == "Durable spec"


def test_restore_with_no_draft_clears_existing_draft() -> None:
    spec = SpecSession()
    spec.define_spec(
        title="Will be cleared",
        summary="Temp spec.",
        acceptance_criteria=["criterion"],
    )

    spec.restore(messages=[], draft=None)

    assert spec.draft is None
    assert list(spec.messages) == []


def test_accept_on_session_with_no_draft_raises() -> None:
    spec = SpecSession()

    with pytest.raises(ValueError, match="no spec draft"):
        spec.accept()
