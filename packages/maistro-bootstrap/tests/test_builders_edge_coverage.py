"""Edge coverage and assertion-strength tests for builder substrate."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from maistro_bootstrap.builders.actions import ActionRequest
from maistro_bootstrap.builders.models import load_litellm_models, role_mapping_from_models
from maistro_bootstrap.builders.quality import QualityGateReport
from maistro_bootstrap.builders.sandbox import LocalWorktreeSandbox, SandboxCommandResult
from maistro_bootstrap.builders.session import BuilderSession
from maistro_bootstrap.builders.spec_session import SpecSession


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


def test_action_request_rejects_malformed_json() -> None:
    with pytest.raises(ValueError, match="invalid builder action JSON"):
        ActionRequest.from_json("{")


def test_litellm_config_rejects_bad_yaml_shapes(tmp_path: Path) -> None:
    scalar = tmp_path / "scalar.yaml"
    scalar.write_text("[]", encoding="utf-8")
    bad_models = tmp_path / "bad-models.yaml"
    bad_models.write_text("model_list: nope", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML mapping"):
        load_litellm_models(scalar)
    with pytest.raises(ValueError, match="model_list must be a list"):
        load_litellm_models(bad_models)


def test_litellm_config_falls_back_when_model_entries_are_empty(tmp_path: Path) -> None:
    config = tmp_path / "empty.yaml"
    config.write_text("model_list:\n  - litellm_params: {model: ignored}\n", encoding="utf-8")

    models = load_litellm_models(config)
    roles = role_mapping_from_models([])

    assert models[0].alias == "maistro-tier-2"
    assert roles.fallback == "maistro-tier-2"


def test_quality_gate_reports_each_failure_reason() -> None:
    report = QualityGateReport(
        tests_passed=False,
        coverage_pct=0,
        mutation_score_pct=0,
        complexity_grade="C",
        dry_ok=False,
        code_smells_ok=False,
        bandit_ok=False,
        ruff_ok=False,
        mypy_ok=False,
    )

    assert report.failures() == [
        "tests pass",
        "coverage >= 90%",
        "mutation score >= 90%",
        "complexity grade >= B+",
        "DRY",
        "no code smells",
        "bandit",
        "ruff",
        "mypy",
    ]


def test_local_worktree_sandbox_blocks_path_escape_and_runs_commands(tmp_path: Path) -> None:
    sandbox = LocalWorktreeSandbox(tmp_path)

    sandbox.write_file("notes/todo.txt", "ship it")
    sandbox.write_file("nested/deep/todo.txt", "nested")
    result = sandbox.run_command([sys.executable, "-c", "print('ok')"], timeout=5)

    assert sandbox.read_file("notes/todo.txt") == "ship it"
    assert sandbox.read_file("nested/deep/todo.txt") == "nested"
    assert (tmp_path / "nested" / "deep").is_dir()
    assert sandbox.search("ship") == ["notes/todo.txt"]
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
    with pytest.raises(ValueError, match="escapes"):
        sandbox.read_file("../outside.txt")


def test_local_worktree_sandbox_diff_reports_git_errors_outside_repo(tmp_path: Path) -> None:
    diff = LocalWorktreeSandbox(tmp_path).diff()

    assert "git" in diff.lower()


def test_local_worktree_sandbox_rejects_empty_command(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires argv"):
        LocalWorktreeSandbox(tmp_path).run_command([], timeout=5)


def test_session_error_branches_and_approved_apply() -> None:
    session = BuilderSession(sandbox=FakeSandbox())
    session.approved_to_apply = True

    apply_result = session.apply_slash_command("/apply")
    bad_run = session.apply_action(ActionRequest(action="run_command", args={"argv": "pytest"}))
    quality = session.apply_slash_command("/quality")

    assert apply_result.status == "ok"
    assert bad_run.status == "error"
    assert quality.output == "No quality report recorded."
    with pytest.raises(ValueError, match="unsupported slash command"):
        session.apply_slash_command("/missing")


def test_spec_session_rejects_incomplete_or_missing_spec() -> None:
    spec = SpecSession()

    assert spec.to_todos(owner="frank") == []
    assert spec.render_review() == "No spec draft."
    with pytest.raises(ValueError, match="no spec draft"):
        spec.accept()
    with pytest.raises(ValueError, match="at least one"):
        spec.define_spec(title="x", summary="y", acceptance_criteria=[])


def test_spec_session_normalizes_spec_and_todo_context() -> None:
    spec = SpecSession()

    draft = spec.define_spec(
        title="  Builders TUI  ",
        summary="  Async comments  ",
        acceptance_criteria=["  create board  ", "", "review done cards"],
    )
    accepted = spec.accept()
    todos = spec.to_todos(owner="mason")

    assert draft.title == "Builders TUI"
    assert draft.summary == "Async comments"
    assert draft.acceptance_criteria == ("create board", "review done cards")
    assert accepted.status == "accepted"
    assert [todo.agent for todo in todos] == ["mason", "mason"]
    assert [todo.question for todo in todos] == ["create board", "review done cards"]
    assert [todo.context for todo in todos] == [
        {"spec": "Builders TUI"},
        {"spec": "Builders TUI"},
    ]
