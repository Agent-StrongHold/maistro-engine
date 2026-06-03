"""Tests for RepoContext and ConfirmationToken — SPEC-200."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from maistro.builders.errors import UnconfirmedRepoAction
from maistro.builders.repo_context import (
    _TOKEN_TTL,
    ConfirmationToken,
    RepoContext,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gh() -> MagicMock:
    gh = MagicMock()
    gh.list_prs.return_value = [{"number": 1}]
    gh.list_branches.return_value = [{"name": "feat/old"}]
    gh.list_issues.return_value = [{"number": 42}]
    return gh


def _ctx(tmp_path: Path, gh: MagicMock | None = None) -> RepoContext:
    return RepoContext(tmp_path, gh or _gh())


# ---------------------------------------------------------------------------
# ConfirmationToken
# ---------------------------------------------------------------------------


class TestConfirmationToken:
    def test_new_token_is_valid(self) -> None:
        t = ConfirmationToken("close_pr:1")
        assert t.is_valid is True

    def test_token_stores_action(self) -> None:
        t = ConfirmationToken("delete_branch:feat/old")
        assert t.action == "delete_branch:feat/old"

    def test_consume_marks_used(self) -> None:
        t = ConfirmationToken("close_pr:1")
        t.consume()
        assert t.is_valid is False

    def test_consume_twice_raises(self) -> None:
        t = ConfirmationToken("close_pr:1")
        t.consume()
        with pytest.raises(ValueError, match="already consumed"):
            t.consume()

    def test_expired_token_is_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        t = ConfirmationToken("close_pr:1")
        # Advance time past TTL
        monkeypatch.setattr(
            "maistro.builders.repo_context.time",
            _FakeTime(t._created_at + _TOKEN_TTL + 1),
        )
        assert t.is_valid is False

    def test_expired_token_consume_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        t = ConfirmationToken("close_pr:1")
        monkeypatch.setattr(
            "maistro.builders.repo_context.time",
            _FakeTime(t._created_at + _TOKEN_TTL + 1),
        )
        with pytest.raises(ValueError, match="expired"):
            t.consume()

    def test_each_token_has_unique_secret(self) -> None:
        a = ConfirmationToken("x")
        b = ConfirmationToken("x")
        assert a._secret != b._secret


class _FakeTime:
    """Monkeypatch target for maistro.builders.repo_context.time."""

    def __init__(self, mono_now: float) -> None:
        self._mono = mono_now

    def monotonic(self) -> float:
        return self._mono

    def time(self) -> float:
        return self._mono


# ---------------------------------------------------------------------------
# RepoContext — read operations (no token)
# ---------------------------------------------------------------------------


class TestRepoContextReads:
    def test_list_stale_prs_requires_no_token(self, tmp_path: Path) -> None:
        gh = _gh()
        ctx = _ctx(tmp_path, gh)
        result = ctx.list_stale_prs(older_than_days=30)
        assert result == [{"number": 1}]

    def test_list_branches_requires_no_token(self, tmp_path: Path) -> None:
        gh = _gh()
        ctx = _ctx(tmp_path, gh)
        result = ctx.list_branches()
        assert result == [{"name": "feat/old"}]

    def test_list_issues_requires_no_token(self, tmp_path: Path) -> None:
        gh = _gh()
        ctx = _ctx(tmp_path, gh)
        result = ctx.list_issues()
        assert result == [{"number": 42}]

    def test_reads_appended_to_audit_log(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        ctx.list_stale_prs()
        ctx.list_branches()
        assert len(ctx.audit_log) == 2

    def test_audit_log_returns_copy(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        ctx.list_stale_prs()
        log1 = ctx.audit_log
        log2 = ctx.audit_log
        assert log1 is not log2  # new list each time


# ---------------------------------------------------------------------------
# RepoContext — write operations (token required)
# ---------------------------------------------------------------------------


class TestRepoContextWrites:
    def test_close_pr_without_token_raises(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        expired = ConfirmationToken("close_pr:1")
        expired._used = True
        with pytest.raises(UnconfirmedRepoAction):
            ctx.close_pr(1, token=expired)

    def test_close_pr_with_valid_token_calls_gh(self, tmp_path: Path) -> None:
        gh = _gh()
        ctx = _ctx(tmp_path, gh)
        token = ConfirmationToken("close_pr:1")
        ctx.close_pr(1, token=token)
        gh.close_pr.assert_called_once_with(1)

    def test_close_pr_consumes_token(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        token = ConfirmationToken("close_pr:1")
        ctx.close_pr(1, token=token)
        assert token.is_valid is False

    def test_close_pr_token_not_reusable(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        token = ConfirmationToken("close_pr:1")
        ctx.close_pr(1, token=token)
        with pytest.raises(UnconfirmedRepoAction):
            ctx.close_pr(2, token=token)

    def test_delete_branch_with_valid_token(self, tmp_path: Path) -> None:
        gh = _gh()
        ctx = _ctx(tmp_path, gh)
        token = ConfirmationToken("delete_branch:feat/old")
        ctx.delete_branch("feat/old", token=token)
        gh.delete_branch.assert_called_once_with("feat/old")

    def test_close_issue_with_valid_token(self, tmp_path: Path) -> None:
        gh = _gh()
        ctx = _ctx(tmp_path, gh)
        token = ConfirmationToken("close_issue:42")
        ctx.close_issue(42, token=token)
        gh.close_issue.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# Audit log completeness
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_successful_write_logged_as_confirmed(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        token = ConfirmationToken("close_pr:7")
        ctx.close_pr(7, token=token)
        entry = ctx.audit_log[-1]
        assert entry.confirmed is True
        assert entry.action == "close_pr"
        assert entry.target == "7"

    def test_rejected_write_logged_as_unconfirmed(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        expired = ConfirmationToken("close_pr:99")
        expired._used = True
        with pytest.raises(UnconfirmedRepoAction):
            ctx.close_pr(99, token=expired)
        entry = ctx.audit_log[-1]
        assert entry.confirmed is False

    def test_every_action_has_timestamp(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        ctx.list_stale_prs()
        token = ConfirmationToken("close_pr:1")
        ctx.close_pr(1, token=token)
        for entry in ctx.audit_log:
            assert isinstance(entry.timestamp, float)
            assert entry.timestamp > 0

    def test_audit_log_order_matches_call_order(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        ctx.list_stale_prs()
        ctx.list_branches()
        ctx.list_issues()
        actions = [e.action for e in ctx.audit_log]
        assert actions == ["list_stale_prs", "list_branches", "list_issues"]
