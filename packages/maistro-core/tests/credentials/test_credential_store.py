"""Encrypted per-user credential store."""

from __future__ import annotations

import contextlib
import json

import pytest
from cryptography.fernet import Fernet
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from maistro.credentials.store import (
    CredentialNotFound,
    CredentialStoreUnavailable,
    UserCredentialStore,
)


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


def _master_key(tmp_path) -> bytes:
    return (tmp_path / "credential_master.key").read_bytes()


def _write_forged_store(tmp_path, ciphertext: bytes) -> None:
    (tmp_path / "user_credentials.enc").write_bytes(ciphertext)


class TestCorruptedStoreFile:
    """Adversarial payloads written directly to the .enc file — must degrade to
    CredentialStoreUnavailable, never an uncaught exception (binascii.Error,
    TypeError, AttributeError, etc.)."""

    def test_corrupted_base64_raises_unavailable(
        self, store: UserCredentialStore, tmp_path
    ) -> None:
        store.set_secret("alice", "jira", "seed")  # forces store creation
        _write_forged_store(tmp_path, b"!!! not valid fernet/base64 !!!")
        fresh = UserCredentialStore.open(tmp_path)
        with pytest.raises(CredentialStoreUnavailable):
            fresh.has_secret("alice", "jira")

    def test_empty_file_raises_unavailable(self, store: UserCredentialStore, tmp_path) -> None:
        store.set_secret("alice", "jira", "seed")
        _write_forged_store(tmp_path, b"")
        fresh = UserCredentialStore.open(tmp_path)
        with pytest.raises(CredentialStoreUnavailable):
            fresh.has_secret("alice", "jira")

    def test_valid_fernet_but_json_array_raises_unavailable(
        self, store: UserCredentialStore, tmp_path
    ) -> None:
        store.set_secret("alice", "jira", "seed")
        fernet = Fernet(_master_key(tmp_path))
        _write_forged_store(tmp_path, fernet.encrypt(json.dumps([1, 2, 3]).encode()))
        fresh = UserCredentialStore.open(tmp_path)
        with pytest.raises(CredentialStoreUnavailable):
            fresh.has_secret("alice", "jira")

    def test_valid_fernet_but_json_scalar_raises_unavailable(
        self, store: UserCredentialStore, tmp_path
    ) -> None:
        store.set_secret("alice", "jira", "seed")
        fernet = Fernet(_master_key(tmp_path))
        _write_forged_store(tmp_path, fernet.encrypt(json.dumps(42).encode()))
        fresh = UserCredentialStore.open(tmp_path)
        with pytest.raises(CredentialStoreUnavailable):
            fresh.has_secret("alice", "jira")

    def test_valid_fernet_but_non_json_payload_raises_unavailable(
        self, store: UserCredentialStore, tmp_path
    ) -> None:
        store.set_secret("alice", "jira", "seed")
        fernet = Fernet(_master_key(tmp_path))
        _write_forged_store(tmp_path, fernet.encrypt(b"not json at all {{{"))
        fresh = UserCredentialStore.open(tmp_path)
        with pytest.raises(CredentialStoreUnavailable):
            fresh.has_secret("alice", "jira")

    def test_wrong_key_decrypt_raises_unavailable(
        self, store: UserCredentialStore, tmp_path
    ) -> None:
        store.set_secret("alice", "jira", "seed")
        wrong_key_fernet = Fernet(Fernet.generate_key())
        payload = json.dumps({"alice": {"jira": "token"}}).encode()
        _write_forged_store(tmp_path, wrong_key_fernet.encrypt(payload))
        fresh = UserCredentialStore.open(tmp_path)
        with pytest.raises(CredentialStoreUnavailable):
            fresh.has_secret("alice", "jira")

    def test_non_dict_user_values_are_filtered_not_crashed(
        self, store: UserCredentialStore, tmp_path
    ) -> None:
        store.set_secret("alice", "jira", "seed")
        fernet = Fernet(_master_key(tmp_path))
        payload = json.dumps(
            {
                "alice": {"jira": "alice-token"},
                "bob": "not-a-dict",
                "carol": ["also", "not", "a", "dict"],
                "dave": None,
            }
        ).encode()
        _write_forged_store(tmp_path, fernet.encrypt(payload))
        fresh = UserCredentialStore.open(tmp_path)
        assert fresh.has_secret("alice", "jira") is True
        assert fresh.has_secret("bob", "jira") is False
        assert fresh.has_secret("carol", "jira") is False
        assert fresh.has_secret("dave", "jira") is False

    @pytest.mark.contract("behavioral")
    @pytest.mark.scope("property")
    @given(garbage=st.binary(max_size=500))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_arbitrary_bytes_never_raise_unexpected_type(
        self, garbage: bytes, store: UserCredentialStore, tmp_path
    ) -> None:
        store.set_secret("alice", "jira", "seed")
        _write_forged_store(tmp_path, garbage)
        fresh = UserCredentialStore.open(tmp_path)

        with contextlib.suppress(CredentialStoreUnavailable):
            fresh.has_secret("alice", "jira")  # the only acceptable failure mode
