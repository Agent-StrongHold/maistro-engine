"""Encrypted per-user credential store."""

from __future__ import annotations

import pytest

from maistro.credentials.store import CredentialNotFound, UserCredentialStore


@pytest.fixture()
def store(tmp_path):
    return UserCredentialStore.open(tmp_path)


def test_set_and_use_secret(store: UserCredentialStore) -> None:
    store.set_secret("alice", "jira", "token-alice")
    seen: list[str] = []

    def _capture(value: str) -> str:
        seen.append(value)
        return "ok"

    assert store.use_secret("alice", "jira", _capture) == "ok"
    assert seen == ["token-alice"]


def test_users_isolated(store: UserCredentialStore) -> None:
    store.set_secret("alice", "jira", "alice-token")
    store.set_secret("bob", "jira", "bob-token")

    assert store.use_secret("alice", "jira", lambda v: v) == "alice-token"
    assert store.use_secret("bob", "jira", lambda v: v) == "bob-token"


def test_encrypted_file_not_plaintext(store: UserCredentialStore, tmp_path) -> None:
    store.set_secret("alice", "github", "ghp_supersecret")
    raw = (tmp_path / "user_credentials.enc").read_bytes()
    assert b"ghp_supersecret" not in raw


def test_missing_raises(store: UserCredentialStore) -> None:
    with pytest.raises(CredentialNotFound):
        store.use_secret("nobody", "jira", lambda v: v)
