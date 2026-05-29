"""I15: Auth Registry — Service Key Registration — Hypothesis property-based tests."""

from __future__ import annotations

import hashlib

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant

from maistro.auth._types import Scope
from maistro.auth.registry import ServiceKeyRegistry


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class RegistryMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.registry = ServiceKeyRegistry()
        self.registered_names: set[str] = set()

    @rule(
        name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
        key=st.text(min_size=8, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
    )
    def register_service(self, name, key):
        self.registry.load_dict(
            {
                name: {"key": key, "scopes": ["llm:*"]},
            }
        )
        self.registered_names.add(name)

    @invariant()
    def registered_services_retrievable(self):
        for name in self.registered_names:
            assert name in self.registry.services

    @invariant()
    def key_hashes_are_16_chars(self):
        for identity in self.registry.services.values():
            if identity.key_hash:
                assert len(identity.key_hash) == 16


TestRegistryMachine = RegistryMachine.TestCase


def test_load_dict_retrievable():
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc-a": {"key": "key-123", "scopes": ["llm:*"]}})
    services = reg.services
    assert "svc-a" in services
    assert services["svc-a"].name == "svc-a"


def test_no_scopes_validate_reports():
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc-b": {"key": "key-456", "scopes": []}})
    issues = reg.validate()
    assert any("no scopes" in i for i in issues)


def test_duplicate_keys_validate_reports():
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc-c": {"key": "same-key", "scopes": ["llm:*"]}})
    reg.load_dict({"svc-d": {"key": "same-key", "scopes": ["llm:*"]}})
    issues = reg.validate()
    assert any("Duplicate" in i or "duplicate" in i for i in issues)


def test_scope_expansion():
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc-e": {"key": "key-789", "scopes": ["llm:*"]}})
    identity = reg.services["svc-e"]
    assert len(identity.scopes) > 0
    assert any(isinstance(s, Scope) for s in identity.scopes)


@given(
    name_a=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L",))),
    name_b=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L",))),
)
@settings(max_examples=30)
def test_multiple_services_independent(name_a, name_b):
    assume(name_a != name_b)
    reg = ServiceKeyRegistry()
    reg.load_dict(
        {
            name_a: {"key": "key-alpha", "scopes": ["llm:*"]},
            name_b: {"key": "key-beta", "scopes": ["memory:*"]},
        }
    )
    assert name_a in reg.services
    assert name_b in reg.services
    assert reg.services[name_a] != reg.services[name_b]


def test_key_hash_is_sha256_truncated():
    key = "test-key-value"
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc": {"key": key, "scopes": ["llm:*"]}})
    identity = reg.services["svc"]
    expected_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
    assert identity.key_hash == expected_hash


@given(
    key=st.text(min_size=8, max_size=40, alphabet=st.characters(whitelist_categories=("L", "N"))),
)
@settings(max_examples=30)
def test_key_hash_length(key):
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc": {"key": key, "scopes": ["llm:*"]}})
    identity = reg.services["svc"]
    assert len(identity.key_hash) == 16


def test_empty_key_skipped():
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc-empty": {"key": "", "scopes": ["llm:*"]}})
    assert "svc-empty" not in reg.services


def test_authenticate_by_key():
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc-auth": {"key": "my-key-abc", "scopes": ["llm:*"]}})
    identity = reg.authenticate("my-key-abc")
    assert identity is not None
    assert identity.name == "svc-auth"


def test_authenticate_unknown_key():
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc-auth2": {"key": "known-key", "scopes": ["llm:*"]}})
    identity = reg.authenticate("unknown-key")
    assert identity is None


@given(
    scopes=st.sets(st.sampled_from(["llm:*", "memory:*", "tasks:*"]), min_size=1, max_size=3),
)
@settings(max_examples=30)
def test_scope_expansion_during_load(scopes):
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc-sc": {"key": "key-sc", "scopes": list(scopes)}})
    identity = reg.services["svc-sc"]
    assert len(identity.scopes) >= 1


@given(
    key=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
)
@settings(max_examples=30)
def test_services_property_returns_copy(key):
    reg = ServiceKeyRegistry()
    reg.load_dict({"svc-cp": {"key": key, "scopes": ["llm:*"]}})
    svc = reg.services
    svc["extra"] = None
    assert "extra" not in reg.services
