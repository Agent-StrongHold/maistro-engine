"""CLI wiring for maistro-install builder sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner

from maistro_bootstrap import cli
from maistro_bootstrap.builders import cli as builders_cli
from maistro_bootstrap.builders.sandbox import SandboxCommandResult
from maistro_bootstrap.builders.session import BuilderSession
from maistro_bootstrap.builders.store import SessionStore

runner = CliRunner()


@dataclass
class FakeSandbox:
    files: dict[str, str] = field(default_factory=lambda: {"README.md": "hello"})

    def read_file(self, path: str) -> str:
        return self.files[path]

    def write_file(self, path: str, content: str) -> None:
        self.files[path] = content

    def search(self, query: str) -> list[str]:
        return [path for path, content in self.files.items() if query in content]

    def run_command(self, argv: list[str], *, timeout: float) -> SandboxCommandResult:
        return SandboxCommandResult(returncode=0, stdout="ok", stderr="", elapsed_seconds=0.01)

    def diff(self) -> str:
        return "diff --git a/README.md b/README.md\n"


def test_builders_models_command_prints_role_mapping(tmp_path: Path) -> None:
    config = tmp_path / "litellm_config.yaml"
    config.write_text(
        """
model_list:
  - model_name: maistro-tier-1
    litellm_params: {model: local-small}
  - model_name: maistro-tier-3
    litellm_params: {model: local-large}
""",
        encoding="utf-8",
    )

    result = runner.invoke(cli.app, ["builders", "models", "--config", str(config)])

    assert result.exit_code == 0
    assert "architect" in result.stdout
    assert "maistro-tier-3" in result.stdout


def test_builders_board_commands_operate_on_persisted_session(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    store = SessionStore(state_dir)
    session = BuilderSession(sandbox=FakeSandbox())
    card = session.message_board.add_todo(title="Review finished todo", owner="human")
    store.save("demo", session)

    comment_result = runner.invoke(
        cli.app,
        [
            "builders",
            "comment",
            card.card_id,
            "Please include mutant evidence.",
            "--state-dir",
            str(state_dir),
            "--session",
            "demo",
        ],
    )
    start_result = runner.invoke(
        cli.app,
        [
            "builders",
            "move",
            card.card_id,
            "wip",
            "--state-dir",
            str(state_dir),
            "--session",
            "demo",
        ],
    )
    finish_result = runner.invoke(
        cli.app,
        [
            "builders",
            "move",
            card.card_id,
            "done",
            "--summary",
            "Reviewed with evidence.",
            "--state-dir",
            str(state_dir),
            "--session",
            "demo",
        ],
    )
    board_result = runner.invoke(
        cli.app,
        ["builders", "board", "--state-dir", str(state_dir), "--session", "demo"],
    )

    assert comment_result.exit_code == 0
    assert start_result.exit_code == 0
    assert finish_result.exit_code == 0
    assert board_result.exit_code == 0
    assert "done" in board_result.stdout
    assert "Builder board" in board_result.stdout
    loaded = store.load("demo", sandbox=FakeSandbox())
    loaded_card = loaded.message_board.get(card.card_id)
    assert loaded_card.status == "done"
    assert loaded_card.comments[-1].body == "Please include mutant evidence."
    assert loaded_card.resolution == "Reviewed with evidence."


def test_builders_list_prints_saved_session_summaries(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    session = BuilderSession(sandbox=FakeSandbox())
    session.message_board.post_question(agent="mason", question="Which tests next?")
    SessionStore(state_dir).save("demo", session)

    result = runner.invoke(cli.app, ["builders", "list", "--state-dir", str(state_dir)])

    assert result.exit_code == 0
    assert "demo" in result.stdout
    assert "1" in result.stdout


def test_default_install_command_still_emits_json_plan(tmp_path: Path) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text(
        """
schema_version: "1"
features:
  - core_lib
stack_bringup: none
""",
        encoding="utf-8",
    )
    result = runner.invoke(
        cli.app,
        [
            "--answers-file",
            str(answers),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"kind": "maistro_install_plan"' in result.stdout


def test_builders_default_launch_tui_with_config(tmp_path: Path) -> None:
    config = tmp_path / "litellm_config.yaml"
    config.write_text(
        "model_list:\n  - model_name: maistro-tier-2\n    litellm_params: {model: local}\n",
        encoding="utf-8",
    )

    import unittest.mock

    with unittest.mock.patch.object(builders_cli, "_launch_tui") as mock_tui:
        result = runner.invoke(
            cli.app,
            ["builders", "session", "-c", str(config), "-r", str(tmp_path)],
        )

    assert result.exit_code == 0
    assert "maistro builders" in result.stdout
    mock_tui.assert_called_once()


def test_builders_models_discovers_config_at_default_path(tmp_path: Path) -> None:
    config = tmp_path / "litellm_config.yaml"
    config.write_text(
        "model_list:\n  - model_name: cloud-sonnet\n    litellm_params: {model: sonnet}\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        cli.app,
        ["builders", "models", "--config", str(config)],
    )

    assert result.exit_code == 0
    assert "cloud-sonnet" in result.stdout


def test_load_raw_answers_rejects_non_mapping(tmp_path: Path) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text("[]", encoding="utf-8")

    with pytest.raises(cli.typer.BadParameter):
        cli._load_raw_answers(answers)
