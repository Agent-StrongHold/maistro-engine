"""Chat-to-spec workflow for builder sessions."""

from __future__ import annotations

from maistro_bootstrap.builders.spec_session import SpecSession


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
