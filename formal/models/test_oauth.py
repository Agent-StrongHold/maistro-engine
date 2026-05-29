"""I23: OAuth2 Token Lifecycle — Hypothesis property-based tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from maistro.security.oauth import OAuth2Provider


class OAuth2TokenMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.provider = OAuth2Provider()
        self.provider.register_provider("google", "https://auth", "https://token", "client123", "openid")
        self.provider.register_provider("github", "https://auth", "https://token", "client456", "repo")
        self.known_tokens = set()
        self.revoked = set()

    @rule(
        provider_name=st.sampled_from(["google", "github", "unknown_provider"]),
        code=st.text(min_size=1, max_size=20),
    )
    def exchange_code(self, provider_name, code):
        if provider_name == "unknown_provider":
            try:
                self.provider.exchange_code_for_token(provider_name, code, "https://cb")
            except ValueError:
                pass
            return
        token = self.provider.exchange_code_for_token(provider_name, code, "https://cb")
        assert token.access_token
        assert token.user_id
        assert token.roles is not None
        self.known_tokens.add(token.access_token)
        self.revoked.discard(token.access_token)

    @rule(stub=st.none())
    def refresh_existing(self, stub):
        token = self.provider.refresh_token("google", "refresh_token_google")
        assert token.access_token
        self.known_tokens.add(token.access_token)
        self.revoked.discard(token.access_token)

    @rule(stub=st.none())
    def revoke_existing(self, stub):
        if not self.known_tokens:
            return
        to_revoke = next(iter(self.known_tokens))
        self.provider.revoke_token(to_revoke)
        self.known_tokens.discard(to_revoke)
        self.revoked.add(to_revoke)

    @invariant()
    def known_tokens_are_valid(self):
        for t in self.known_tokens:
            assert self.provider.validate_token(t)

    @invariant()
    def revoked_tokens_are_invalid(self):
        for t in self.revoked:
            assert not self.provider.validate_token(t)

    @invariant()
    def unknown_tokens_invalid(self):
        assert not self.provider.validate_token("nonexistent_token_xyz")


TestOAuth2TokenMachine = OAuth2TokenMachine.TestCase


@given(provider_name=st.text(min_size=1, max_size=20))
@settings(max_examples=30)
def test_unregistered_provider_raises(provider_name):
    p = OAuth2Provider()
    try:
        p.exchange_code_for_token(provider_name, "code", "https://cb")
        raise AssertionError("Expected ValueError")
    except ValueError:
        pass


def test_exchange_then_validate():
    p = OAuth2Provider()
    p.register_provider("gh", "https://auth", "https://token", "cid", "repo")
    token = p.exchange_code_for_token("gh", "abc123", "https://cb")
    assert p.validate_token(token.access_token)
    info = p.get_user_info(token.access_token)
    assert info["user_id"] == token.user_id
    assert info["roles"] == token.roles


def test_revoke_then_validate_false():
    p = OAuth2Provider()
    p.register_provider("gh", "https://auth", "https://token", "cid", "repo")
    token = p.exchange_code_for_token("gh", "abc123", "https://cb")
    p.revoke_token(token.access_token)
    assert not p.validate_token(token.access_token)


def test_refreshed_token_is_new():
    p = OAuth2Provider()
    p.register_provider("gh", "https://auth", "https://token", "cid", "repo")
    token = p.exchange_code_for_token("gh", "abc123", "https://cb")
    refreshed = p.refresh_token("gh", token.refresh_token)
    assert refreshed.access_token != token.access_token
    assert p.validate_token(refreshed.access_token)


def test_token_not_in_store_is_invalid():
    p = OAuth2Provider()
    assert not p.validate_token("no_such_token")


def test_token_expiry_check():
    p = OAuth2Provider()
    p.register_provider("gh", "https://auth", "https://token", "cid", "repo")
    token = p.exchange_code_for_token("gh", "abc123", "https://cb")
    expired_token = token.access_token
    p._tokens[expired_token].created_at = datetime.now(UTC) - timedelta(seconds=7200)
    assert not p.validate_token(expired_token)


@given(scope=st.text(min_size=1, max_size=30))
@settings(max_examples=20)
def test_user_info_scope_matches(scope):
    p = OAuth2Provider()
    p.register_provider("test", "https://a", "https://t", "cid", scope)
    token = p.exchange_code_for_token("test", "code", "https://cb")
    info = p.get_user_info(token.access_token)
    assert info["scope"] == scope
