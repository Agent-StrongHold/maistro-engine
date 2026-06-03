"""Builders safety layer — gated live-repo context for Janitor (SPEC-200).

RepoContext wraps destructive GitHub/repo operations behind single-use
ConfirmationTokens. Every action — confirmed or rejected — is written to
an immutable audit log. Read operations need no token.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from maistro.builders.errors import UnconfirmedRepoAction

# ---------------------------------------------------------------------------
# ConfirmationToken
# ---------------------------------------------------------------------------

_TOKEN_TTL: float = 60.0


class ConfirmationToken:
    """Single-use, time-limited token authorising one destructive repo action.

    Issued by a HITL gate (CLI prompt, web modal, etc.) and consumed by the
    first destructive call that accepts it. Expired or already-consumed tokens
    raise ValueError on consume().
    """

    def __init__(self, action: str) -> None:
        self._action = action
        self._secret = secrets.token_hex(16)
        self._created_at = time.monotonic()
        self._used = False

    @property
    def action(self) -> str:
        return self._action

    @property
    def is_valid(self) -> bool:
        return not self._used and (time.monotonic() - self._created_at) <= _TOKEN_TTL

    def consume(self) -> None:
        if self._used:
            raise ValueError("ConfirmationToken already consumed")
        if (time.monotonic() - self._created_at) > _TOKEN_TTL:
            raise ValueError("ConfirmationToken expired")
        self._used = True


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


@dataclass
class RepoAction:
    """One entry in the RepoContext audit log."""

    action: str
    target: str
    confirmed: bool
    timestamp: float = field(default_factory=time.time)
    detail: str = ""


# ---------------------------------------------------------------------------
# GitHubClientProtocol
# ---------------------------------------------------------------------------


@runtime_checkable
class GitHubClientProtocol(Protocol):
    """Minimal GitHub surface that RepoContext needs."""

    def close_pr(self, pr_number: int) -> None: ...
    def delete_branch(self, branch: str) -> None: ...
    def close_issue(self, issue_number: int) -> None: ...
    def list_prs(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def list_branches(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def list_issues(self, **kwargs: Any) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# RepoContext
# ---------------------------------------------------------------------------


class RepoContext:
    """Gated interface to the live repo and GitHub for Janitor.

    Read operations (list_*) never require a token.
    Write operations (close_pr, delete_branch, close_issue) each consume one
    ConfirmationToken — the token must be valid and unused.

    Every call (read or write, success or failure) is appended to audit_log.
    """

    def __init__(self, repo_path: Path, github_client: GitHubClientProtocol) -> None:
        self._repo = repo_path.resolve()
        self._gh = github_client
        self._log: list[RepoAction] = []

    @property
    def audit_log(self) -> list[RepoAction]:
        return list(self._log)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record(self, action: str, target: str, *, confirmed: bool, detail: str = "") -> None:
        self._log.append(
            RepoAction(action=action, target=target, confirmed=confirmed, detail=detail)
        )

    def _require_token(self, token: ConfirmationToken, action: str) -> None:
        if not token.is_valid:
            self._record(action, "", confirmed=False, detail="invalid or expired token")
            raise UnconfirmedRepoAction(action)
        token.consume()

    # ------------------------------------------------------------------
    # Read operations — no token required
    # ------------------------------------------------------------------

    def list_stale_prs(self, *, older_than_days: int = 30) -> list[dict[str, Any]]:
        result = self._gh.list_prs(older_than_days=older_than_days)
        self._record("list_stale_prs", "", confirmed=True)
        return result

    def list_branches(self, **kwargs: Any) -> list[dict[str, Any]]:
        result = self._gh.list_branches(**kwargs)
        self._record("list_branches", "", confirmed=True)
        return result

    def list_issues(self, **kwargs: Any) -> list[dict[str, Any]]:
        result = self._gh.list_issues(**kwargs)
        self._record("list_issues", "", confirmed=True)
        return result

    # ------------------------------------------------------------------
    # Write operations — each consumes one ConfirmationToken
    # ------------------------------------------------------------------

    def close_pr(self, pr_number: int, *, token: ConfirmationToken) -> None:
        self._require_token(token, f"close_pr:{pr_number}")
        self._gh.close_pr(pr_number)
        self._record("close_pr", str(pr_number), confirmed=True)

    def delete_branch(self, branch: str, *, token: ConfirmationToken) -> None:
        self._require_token(token, f"delete_branch:{branch}")
        self._gh.delete_branch(branch)
        self._record("delete_branch", branch, confirmed=True)

    def close_issue(self, issue_number: int, *, token: ConfirmationToken) -> None:
        self._require_token(token, f"close_issue:{issue_number}")
        self._gh.close_issue(issue_number)
        self._record("close_issue", str(issue_number), confirmed=True)
