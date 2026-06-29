"""Coverage for OAuth2Provider (in-memory demo OAuth2 implementation)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from maistro.security.oauth import OAuth2Provider, OAuthProvider, OAuthToken


@pytest.fixture
def provider() -> OAuth2Provider:
    return OAuth2Provider()


def test_register_provider_stores_provider_config(provider: OAuth2Provider) -> None:
    provider.register_provider(
        name="google",
        authorization_url="https://accounts.google.com/auth",
        token_url="https://oauth2.googleapis.com/token",
        client_id="client-123",
        scope="openid email",
    )
    stored = provider._providers["google"]
    assert stored == OAuthProvider(
        name="google",
        authorization_url="https://accounts.google.com/auth",
        token_url="https://oauth2.googleapis.com/token",
        client_id="client-123",
        scope="openid email",
    )


def test_exchange_code_for_token_raises_for_unknown_provider(provider: OAuth2Provider) -> None:
    with pytest.raises(ValueError, match="OAuth2 provider not found: ghost"):
        provider.exchange_code_for_token("ghost", code="abc", redirect_uri="https://x/cb")


def test_exchange_code_for_token_returns_token_and_caches_it(provider: OAuth2Provider) -> None:
    provider.register_provider(
        name="github",
        authorization_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        client_id="cid",
        scope="repo",
    )
    token = provider.exchange_code_for_token("github", code="abc", redirect_uri="https://x/cb")
    assert token.access_token == "access_token_github"
    assert token.refresh_token == "refresh_token_github"
    assert token.expires_in == 3600
    assert token.scope == "repo"
    assert token.user_id == "user_github"
    assert token.roles == ["user"]
    assert provider._tokens[token.access_token] is token


def test_refresh_token_raises_for_unknown_provider(provider: OAuth2Provider) -> None:
    with pytest.raises(ValueError, match="OAuth2 provider not found: ghost"):
        provider.refresh_token("ghost", refresh_token="rt")


def test_refresh_token_returns_new_token_and_caches_it(provider: OAuth2Provider) -> None:
    provider.register_provider(
        name="keycloak",
        authorization_url="https://kc/auth",
        token_url="https://kc/token",
        client_id="cid",
        scope="profile",
    )
    token = provider.refresh_token("keycloak", refresh_token="old-rt")
    assert token.access_token == "access_token_keycloak_refreshed"
    assert token.refresh_token == "refresh_token_keycloak_new"
    assert token.scope == "profile"
    assert provider._tokens[token.access_token] is token


def test_validate_token_returns_false_for_unknown_token(provider: OAuth2Provider) -> None:
    assert provider.validate_token("nope") is False


def test_validate_token_returns_true_for_fresh_token(provider: OAuth2Provider) -> None:
    provider.register_provider("google", "url", "url", "cid", "scope")
    token = provider.exchange_code_for_token("google", code="c", redirect_uri="r")
    assert provider.validate_token(token.access_token) is True


def test_validate_token_returns_false_for_expired_token(provider: OAuth2Provider) -> None:
    expired = OAuthToken(
        access_token="expired-token",
        refresh_token="rt",
        expires_in=1,
        scope="s",
        user_id="u",
        roles=["user"],
        created_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    provider._tokens[expired.access_token] = expired
    assert provider.validate_token("expired-token") is False


def test_get_user_info_raises_for_unknown_token(provider: OAuth2Provider) -> None:
    with pytest.raises(ValueError, match="Invalid access token"):
        provider.get_user_info("nope")


def test_get_user_info_returns_expected_fields(provider: OAuth2Provider) -> None:
    provider.register_provider("google", "url", "url", "cid", "openid")
    token = provider.exchange_code_for_token("google", code="c", redirect_uri="r")
    info = provider.get_user_info(token.access_token)
    assert info["user_id"] == "user_google"
    assert info["roles"] == ["user"]
    assert info["scope"] == "openid"
    assert isinstance(info["expires_at"], datetime)


def test_revoke_token_removes_known_token(provider: OAuth2Provider) -> None:
    provider.register_provider("google", "url", "url", "cid", "scope")
    token = provider.exchange_code_for_token("google", code="c", redirect_uri="r")
    provider.revoke_token(token.access_token)
    assert token.access_token not in provider._tokens


def test_revoke_token_is_a_noop_for_unknown_token(provider: OAuth2Provider) -> None:
    provider.revoke_token("nope")
    assert "nope" not in provider._tokens
