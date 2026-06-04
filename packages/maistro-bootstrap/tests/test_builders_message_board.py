"""Kanban-style message board for builder agent questions."""

from __future__ import annotations

import pytest

from maistro_bootstrap.builders.message_board import MessageBoard


def test_agent_question_appears_on_open_board() -> None:
    board = MessageBoard()

    card = board.post_question(
        agent="mason",
        question="Which test command should I use?",
        context={"stage": "tests_written"},
    )

    open_cards = board.open_cards()
    assert open_cards == [card]
    assert card.card_id.startswith("card_")
    assert card.card_type == "question"
    assert card.agent == "mason"
    assert card.question == "Which test command should I use?"
    assert card.status == "open"
    assert card.context == {"stage": "tests_written"}


def test_human_can_comment_on_selected_card() -> None:
    board = MessageBoard()
    card = board.post_question(agent="auditor", question="Approve this diff?")

    updated = board.add_human_comment(card.card_id, "Run bootstrap tests first.")

    assert updated.comments[-1].author == "human"
    assert updated.comments[-1].body == "Run bootstrap tests first."


def test_resolved_card_leaves_open_board_but_remains_findable() -> None:
    board = MessageBoard()
    card = board.post_question(agent="frank", question="Clarify acceptance criteria?")

    resolved = board.resolve(card.card_id, resolution="User clarified scope.")

    assert resolved.status == "resolved"
    assert board.open_cards() == []
    assert board.get(card.card_id).resolution == "User clarified scope."


def test_todos_move_through_kanban_columns_and_done_cards_are_reviewable() -> None:
    board = MessageBoard()
    todo = board.add_todo(
        title="Wire LiteLLM roles",
        owner="frank",
        context={"spec": "Builder CLI"},
    )

    wip = board.start(todo.card_id)
    done = board.finish(wip.card_id, summary="Role mapping implemented.")
    reviewed = board.add_human_comment(done.card_id, "Looks good; add CLI smoke coverage.")

    assert todo.card_id.startswith("card_")
    assert todo.agent == "frank"
    assert todo.question == "Wire LiteLLM roles"
    assert todo.card_type == "todo"
    assert todo.context == {"spec": "Builder CLI"}
    assert wip.status == "wip"
    assert done.status == "done"
    assert done.resolution == "Role mapping implemented."
    columns = board.columns()
    assert columns["todo"] == []
    assert columns["wip"] == []
    assert columns["done"] == [reviewed]
    assert reviewed.comments[-1].body == "Looks good; add CLI smoke coverage."


# ---------------------------------------------------------------------------
# replace_cards
# ---------------------------------------------------------------------------


def test_replace_cards_replaces_all_existing_cards() -> None:
    board = MessageBoard()
    board.post_question(agent="mason", question="First question?")
    board.post_question(agent="mason", question="Second question?")
    assert len(board.cards()) == 2

    new_card = board.add_todo(title="Replacement task", owner="frank")
    # Snapshot the card then rebuild the board from just that card.
    replacement_cards = [new_card]
    board.replace_cards(replacement_cards)

    assert len(board.cards()) == 1
    assert board.cards()[0].question == "Replacement task"


def test_replace_cards_with_empty_list_clears_the_board() -> None:
    board = MessageBoard()
    board.post_question(agent="agent", question="Any question?")

    board.replace_cards([])

    assert board.cards() == ()
    assert board.open_cards() == []


def test_replace_cards_allows_round_trip_persistence() -> None:
    board = MessageBoard()
    c1 = board.add_todo(title="Task A", owner="alice")
    c2 = board.add_todo(title="Task B", owner="bob")
    snapshot = list(board.cards())

    fresh_board = MessageBoard()
    fresh_board.replace_cards(snapshot)

    assert [c.card_id for c in fresh_board.cards()] == [c1.card_id, c2.card_id]


# ---------------------------------------------------------------------------
# get() with unknown card_id
# ---------------------------------------------------------------------------


def test_get_raises_key_error_for_unknown_card_id() -> None:
    board = MessageBoard()

    with pytest.raises(KeyError):
        board.get("nonexistent_card_id")


def test_get_returns_card_after_it_is_added() -> None:
    board = MessageBoard()
    card = board.post_question(agent="agent", question="Findable?")

    found = board.get(card.card_id)

    assert found.card_id == card.card_id
    assert found.question == "Findable?"


# ---------------------------------------------------------------------------
# finish() on a card that was never started (never moved to wip)
# ---------------------------------------------------------------------------


def test_finish_without_start_moves_card_directly_to_done() -> None:
    board = MessageBoard()
    todo = board.add_todo(title="Skip-wip task", owner="agent")

    # finish() without calling start() first — should still succeed.
    done = board.finish(todo.card_id, summary="Completed directly.")

    assert done.status == "done"
    assert done.resolution == "Completed directly."
    # Card must appear in the done column, not todo or wip.
    columns = board.columns()
    assert columns["done"] == [done]
    assert columns["todo"] == []
    assert columns["wip"] == []


def test_finish_on_question_card_marks_it_done() -> None:
    board = MessageBoard()
    card = board.post_question(agent="agent", question="Is this done?")

    done = board.finish(card.card_id, summary="Yes.")

    assert done.status == "done"
    assert done.resolution == "Yes."
