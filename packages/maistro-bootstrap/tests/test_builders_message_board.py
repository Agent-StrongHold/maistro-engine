"""Kanban-style message board for builder agent questions."""

from __future__ import annotations

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
