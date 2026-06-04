"""Tests for BuilderSession handlers and slash commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from maistro_bootstrap.builders.actions import ActionRequest
from maistro_bootstrap.builders.sandbox import LocalWorktreeSandbox, SandboxCommandResult
from maistro_bootstrap.builders.session import BuilderSession

# ---------------------------------------------------------------------------
# Minimal fake sandbox — no subprocess, no git
# ---------------------------------------------------------------------------


@dataclass
class FakeSandbox:
    files: dict[str, str] = field(default_factory=lambda: {"README.md": "hello"})
    _last_cmd: list[str] = field(default_factory=list)
    _cmd_returncode: int = 0
    _cmd_stdout: str = "ok"
    _cmd_stderr: str = ""

    def read_file(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def write_file(self, path: str, content: str) -> None:
        self.files[path] = content

    def search(self, query: str) -> list[str]:
        return [p for p, c in self.files.items() if query in c]

    def run_command(self, argv: list[str], *, timeout: float) -> SandboxCommandResult:
        self._last_cmd = argv
        return SandboxCommandResult(
            returncode=self._cmd_returncode,
            stdout=self._cmd_stdout,
            stderr=self._cmd_stderr,
            elapsed_seconds=0.001,
        )

    def diff(self) -> str:
        return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session(sandbox: FakeSandbox | None = None) -> BuilderSession:
    return BuilderSession(sandbox=sandbox or FakeSandbox())


def _req(action: str, **args: object) -> ActionRequest:
    return ActionRequest(action=action, args=dict(args))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


class TestSlashDiff:
    def test_diff_returns_ok_status(self) -> None:
        session = _session()
        result = session.apply_slash_command("/diff")

        assert result.status == "ok"

    def test_diff_delegates_to_show_diff_action(self) -> None:
        sandbox = FakeSandbox()
        session = _session(sandbox)
        # show_diff returns sandbox.diff() which is "" — that's fine
        result = session.apply_slash_command("/diff")

        assert result.status == "ok"
        assert len(session.transcript) == 1
        assert session.transcript[0]["action"] == "show_diff"


class TestSlashTest:
    def test_test_runs_pytest_via_run_command(self) -> None:
        sandbox = FakeSandbox()
        session = _session(sandbox)
        result = session.apply_slash_command("/test")

        assert result.status == "ok"
        assert sandbox._last_cmd == ["uv", "run", "pytest", "-q"]

    def test_test_propagates_non_zero_exit_as_error(self) -> None:
        sandbox = FakeSandbox(_cmd_returncode=1, _cmd_stderr="1 failed")
        session = _session(sandbox)
        result = session.apply_slash_command("/test")

        assert result.status == "error"


class TestSlashBoard:
    def test_board_reports_empty_columns(self) -> None:
        session = _session()
        result = session.apply_slash_command("/board")

        assert result.status == "ok"
        assert "todo=0" in result.output
        assert "wip=0" in result.output
        assert "done=0" in result.output

    def test_board_counts_todo_cards_from_spec(self) -> None:
        session = _session()
        # Define and accept a spec so to-dos land on the board
        session.apply_action(
            _req(
                "define_spec",
                title="Ship it",
                summary="Fast path",
                acceptance_criteria=["task A", "task B"],
            )
        )
        session.apply_action(_req("accept_spec", owner="frank"))
        result = session.apply_slash_command("/board")

        # Two todo cards were added for the two acceptance criteria
        assert "todo=2" in result.output

    def test_board_counts_open_question_cards(self) -> None:
        session = _session()
        session.apply_action(_req("post_question", agent="builder", question="Blockers?"))
        result = session.apply_slash_command("/board")

        assert "questions=1" in result.output


class TestSlashStatus:
    def test_status_returns_ok_with_summary(self) -> None:
        session = _session()
        result = session.apply_slash_command("/status")

        assert result.status == "ok"
        assert "Builder session" in result.output
        assert "last_status=none" in result.output

    def test_status_reflects_action_count_after_actions(self) -> None:
        session = _session()
        session.apply_slash_command("/diff")
        result = session.apply_slash_command("/status")

        assert "1 action(s)" in result.output


class TestSlashQuality:
    def test_quality_with_no_report_says_none_recorded(self) -> None:
        session = _session()
        result = session.apply_slash_command("/quality")

        assert result.status == "ok"
        assert "No quality report recorded." in result.output

    def test_quality_with_passing_report_says_passed(self) -> None:
        session = _session()
        session.apply_action(
            _req(
                "record_quality",
                tests_passed=True,
                coverage_pct=95.0,
                mutation_score_pct=91.0,
                complexity_grade="A",
                dry_ok=True,
                code_smells_ok=True,
                bandit_ok=True,
                ruff_ok=True,
                mypy_ok=True,
            )
        )
        result = session.apply_slash_command("/quality")

        assert result.status == "ok"
        assert "passed" in result.output.lower()

    def test_quality_with_failing_report_returns_error(self) -> None:
        session = _session()
        session.apply_action(
            _req(
                "record_quality",
                tests_passed=False,
                coverage_pct=50.0,
                mutation_score_pct=40.0,
                complexity_grade="C",
                dry_ok=False,
                code_smells_ok=False,
                bandit_ok=False,
                ruff_ok=False,
                mypy_ok=False,
            )
        )
        result = session.apply_slash_command("/quality")

        assert result.status == "error"
        assert "tests pass" in result.output


class TestSlashReject:
    def test_reject_clears_approved_flag(self) -> None:
        session = _session()
        session.approved_to_apply = True

        result = session.apply_slash_command("/reject")

        assert result.status == "ok"
        assert session.approved_to_apply is False

    def test_reject_message_is_informative(self) -> None:
        session = _session()
        result = session.apply_slash_command("/reject")

        assert "rejected" in result.output


# ---------------------------------------------------------------------------
# _handle_propose_patch
# ---------------------------------------------------------------------------


class TestHandleProposePatch:
    def test_writes_file_to_sandbox(self, tmp_path: Path) -> None:
        sandbox = LocalWorktreeSandbox(tmp_path)
        session = BuilderSession(sandbox=sandbox)

        result = session.apply_action(_req("propose_patch", path="src/app.py", content="# hello\n"))

        assert result.status == "ok"
        assert "src/app.py" in result.output
        assert (tmp_path / "src" / "app.py").read_text() == "# hello\n"

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        sandbox = LocalWorktreeSandbox(tmp_path)
        (tmp_path / "notes.txt").write_text("old", encoding="utf-8")
        session = BuilderSession(sandbox=sandbox)

        session.apply_action(_req("propose_patch", path="notes.txt", content="new"))

        assert (tmp_path / "notes.txt").read_text() == "new"

    def test_missing_path_raises_error_status(self) -> None:
        session = _session()
        result = session.apply_action(_req("propose_patch", content="x"))

        assert result.status == "error"
        assert "path" in result.output.lower()

    def test_missing_content_raises_error_status(self) -> None:
        session = _session()
        result = session.apply_action(_req("propose_patch", path="foo.py"))

        assert result.status == "error"
        assert "content" in result.output.lower()


# ---------------------------------------------------------------------------
# _handle_comment_card
# ---------------------------------------------------------------------------


class TestHandleCommentCard:
    def test_adds_comment_to_existing_question_card(self) -> None:
        session = _session()
        post_result = session.apply_action(
            _req("post_question", agent="builder", question="What is the deadline?")
        )
        card_id = post_result.metadata["card_id"]

        comment_result = session.apply_action(
            _req("comment_card", card_id=card_id, body="End of sprint.")
        )

        assert comment_result.status == "ok"
        assert card_id in comment_result.output
        assert comment_result.metadata["comments"] == 1

    def test_accumulates_multiple_comments(self) -> None:
        session = _session()
        post = session.apply_action(_req("post_question", agent="qa", question="Is auth done?"))
        cid = post.metadata["card_id"]

        session.apply_action(_req("comment_card", card_id=cid, body="First comment."))
        result = session.apply_action(_req("comment_card", card_id=cid, body="Second comment."))

        assert result.metadata["comments"] == 2

    def test_unknown_card_id_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(
            _req("comment_card", card_id="card_nonexistent", body="Hello")
        )

        assert result.status == "error"

    def test_missing_card_id_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("comment_card", body="Hello"))

        assert result.status == "error"

    def test_missing_body_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("comment_card", card_id="card_x"))

        assert result.status == "error"


# ---------------------------------------------------------------------------
# _handle_post_question
# ---------------------------------------------------------------------------


class TestHandlePostQuestion:
    def test_creates_a_new_question_card(self) -> None:
        session = _session()
        result = session.apply_action(
            _req("post_question", agent="planner", question="Which DB to use?")
        )

        assert result.status == "ok"
        assert "card_" in result.output
        assert "card_id" in result.metadata

    def test_question_appears_in_open_cards(self) -> None:
        session = _session()
        result = session.apply_action(
            _req("post_question", agent="planner", question="Which DB to use?")
        )
        cid = result.metadata["card_id"]

        open_ids = [c.card_id for c in session.message_board.open_cards()]
        assert cid in open_ids

    def test_missing_agent_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("post_question", question="Q?"))

        assert result.status == "error"

    def test_missing_question_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("post_question", agent="bob"))

        assert result.status == "error"


# ---------------------------------------------------------------------------
# _handle_define_spec
# ---------------------------------------------------------------------------


class TestHandleDefineSpec:
    def test_defines_a_spec_draft(self) -> None:
        session = _session()
        result = session.apply_action(
            _req(
                "define_spec",
                title="New Feature",
                summary="Adds X",
                acceptance_criteria=["criterion one", "criterion two"],
            )
        )

        assert result.status == "ok"
        assert result.metadata["criteria"] == 2
        assert result.metadata["status"] == "draft"

    def test_render_review_is_returned_in_output(self) -> None:
        session = _session()
        result = session.apply_action(
            _req(
                "define_spec",
                title="Login Flow",
                summary="OAuth2",
                acceptance_criteria=["redirect works"],
            )
        )

        assert "Login Flow" in result.output
        assert "redirect works" in result.output

    def test_missing_title_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("define_spec", summary="x", acceptance_criteria=["c"]))

        assert result.status == "error"

    def test_missing_summary_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("define_spec", title="T", acceptance_criteria=["c"]))

        assert result.status == "error"

    def test_empty_criteria_list_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(
            _req("define_spec", title="T", summary="S", acceptance_criteria=[])
        )

        assert result.status == "error"

    def test_criteria_not_a_list_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(
            _req("define_spec", title="T", summary="S", acceptance_criteria="not a list")
        )

        assert result.status == "error"


# ---------------------------------------------------------------------------
# _handle_accept_spec
# ---------------------------------------------------------------------------


class TestHandleAcceptSpec:
    def test_accepts_a_previously_defined_spec(self) -> None:
        session = _session()
        session.apply_action(
            _req(
                "define_spec",
                title="Checkout",
                summary="Shopping cart",
                acceptance_criteria=["add item", "remove item"],
            )
        )

        result = session.apply_action(_req("accept_spec", owner="frank"))

        assert result.status == "ok"
        assert "Checkout" in result.output
        assert result.metadata["todos"] == 2

    def test_accept_without_prior_define_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("accept_spec"))

        assert result.status == "error"

    def test_accept_uses_default_owner_frank_when_not_supplied(self) -> None:
        session = _session()
        session.apply_action(
            _req(
                "define_spec",
                title="T",
                summary="S",
                acceptance_criteria=["c1"],
            )
        )
        result = session.apply_action(_req("accept_spec"))

        # Should succeed — "frank" is the default owner
        assert result.status == "ok"

    def test_spec_status_is_accepted_after_accept(self) -> None:
        session = _session()
        session.apply_action(
            _req(
                "define_spec",
                title="Deploy",
                summary="CI/CD",
                acceptance_criteria=["pipeline green"],
            )
        )
        session.apply_action(_req("accept_spec"))

        assert session.spec_session.draft is not None
        assert session.spec_session.draft.status == "accepted"


# ---------------------------------------------------------------------------
# _handle_record_quality
# ---------------------------------------------------------------------------


class TestHandleRecordQuality:
    def _passing_args(self) -> dict[str, object]:
        return {
            "tests_passed": True,
            "coverage_pct": 92.0,
            "mutation_score_pct": 91.0,
            "complexity_grade": "A",
            "dry_ok": True,
            "code_smells_ok": True,
            "bandit_ok": True,
            "ruff_ok": True,
            "mypy_ok": True,
        }

    def test_passing_quality_report_returns_ok(self) -> None:
        session = _session()
        result = session.apply_action(_req("record_quality", **self._passing_args()))

        assert result.status == "ok"
        assert result.metadata["passed"] is True
        assert result.metadata["failures"] == []

    def test_failing_quality_report_returns_error(self) -> None:
        session = _session()
        args = self._passing_args()
        args["tests_passed"] = False
        args["coverage_pct"] = 10.0

        result = session.apply_action(_req("record_quality", **args))

        assert result.status == "error"
        assert result.metadata["passed"] is False
        assert "tests pass" in result.metadata["failures"]
        assert "coverage >= 90%" in result.metadata["failures"]

    def test_report_is_stored_on_dagflow(self) -> None:
        session = _session()
        session.apply_action(_req("record_quality", **self._passing_args()))

        assert session.dagflow.quality is not None
        assert session.dagflow.quality.passed is True

    def test_missing_bool_field_returns_error(self) -> None:
        session = _session()
        args = self._passing_args()
        del args["tests_passed"]  # type: ignore[misc]

        result = session.apply_action(_req("record_quality", **args))

        assert result.status == "error"

    def test_non_numeric_coverage_returns_error(self) -> None:
        session = _session()
        args = self._passing_args()
        args["coverage_pct"] = "ninety"

        result = session.apply_action(_req("record_quality", **args))

        assert result.status == "error"


# ---------------------------------------------------------------------------
# snapshot()
# ---------------------------------------------------------------------------


class TestSnapshot:
    _EXPECTED_KEYS: ClassVar[set[str]] = {
        "actions",
        "last_status",
        "approved_to_apply",
        "pending_diff",
        "open_questions",
        "board_columns",
        "spec_status",
        "dag",
        "transcript_tail",
    }

    def test_snapshot_contains_all_expected_keys(self) -> None:
        session = _session()
        snap = session.snapshot()

        assert set(snap.keys()) == self._EXPECTED_KEYS

    def test_snapshot_initial_state_defaults(self) -> None:
        session = _session()
        snap = session.snapshot()

        assert snap["actions"] == 0
        assert snap["last_status"] == "none"
        assert snap["approved_to_apply"] is False
        assert snap["open_questions"] == 0
        assert snap["spec_status"] == "none"
        assert snap["transcript_tail"] == []

    def test_snapshot_board_columns_is_dict_of_counts(self) -> None:
        session = _session()
        snap = session.snapshot()

        cols = snap["board_columns"]
        assert isinstance(cols, dict)
        assert set(cols.keys()) == {"todo", "wip", "done"}

    def test_snapshot_reflects_action_count(self) -> None:
        session = _session()
        session.apply_slash_command("/diff")
        session.apply_slash_command("/diff")
        snap = session.snapshot()

        assert snap["actions"] == 2
        assert snap["last_status"] == "ok"

    def test_snapshot_reflects_spec_status_after_define(self) -> None:
        session = _session()
        session.apply_action(
            _req(
                "define_spec",
                title="T",
                summary="S",
                acceptance_criteria=["c"],
            )
        )
        snap = session.snapshot()

        assert snap["spec_status"] == "draft"

    def test_snapshot_pending_diff_true_when_sandbox_has_diff(self) -> None:
        sandbox = FakeSandbox()
        sandbox.diff = lambda: "diff --git a/foo\n"  # type: ignore[method-assign]
        session = BuilderSession(sandbox=sandbox)
        snap = session.snapshot()

        assert snap["pending_diff"] is True

    def test_snapshot_transcript_tail_shows_up_to_five_entries(self) -> None:
        session = _session()
        for _ in range(7):
            session.apply_slash_command("/diff")
        snap = session.snapshot()

        assert len(snap["transcript_tail"]) == 5  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# apply_action() exception handling
# ---------------------------------------------------------------------------


class TestApplyActionExceptionHandling:
    def test_handler_exception_produces_error_result(self) -> None:
        session = _session()
        # propose_patch with missing path will raise ValueError inside handler
        result = session.apply_action(_req("propose_patch", content="x"))

        assert result.status == "error"
        assert "path" in result.output.lower()

    def test_exception_is_appended_to_transcript(self) -> None:
        session = _session()
        session.apply_action(_req("propose_patch", content="x"))

        assert len(session.transcript) == 1
        assert session.transcript[0]["status"] == "error"

    def test_session_continues_after_handler_error(self) -> None:
        session = _session()
        session.apply_action(_req("propose_patch", content="x"))  # will error
        result = session.apply_slash_command("/diff")

        assert result.status == "ok"
        assert len(session.transcript) == 2


# ---------------------------------------------------------------------------
# _handle_run_command() with malformed argv
# ---------------------------------------------------------------------------


class TestHandleRunCommandMalformedArgv:
    def test_non_list_argv_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("run_command", argv="pytest"))

        assert result.status == "error"
        assert "argv" in result.output.lower()

    def test_list_with_non_string_element_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("run_command", argv=["pytest", 42]))

        assert result.status == "error"

    def test_missing_argv_key_returns_error(self) -> None:
        session = _session()
        result = session.apply_action(_req("run_command", timeout=5.0))

        assert result.status == "error"

    def test_valid_list_argv_is_accepted(self) -> None:
        sandbox = FakeSandbox()
        session = _session(sandbox)
        result = session.apply_action(_req("run_command", argv=["echo", "hi"], timeout=5.0))

        assert result.status == "ok"
        assert sandbox._last_cmd == ["echo", "hi"]
