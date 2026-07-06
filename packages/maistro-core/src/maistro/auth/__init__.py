"""maistro.auth — B2B service key authentication for the unified platform.

Long-lived service keys with scoped permissions for cross-service communication.
Supports category-level grants (e.g. "trading:*") and individual scope overrides.

Usage:
    from maistro.auth import ServiceKeyRegistry, ServiceKeyAuthProvider, Scope

    registry = ServiceKeyRegistry()
    registry.load_dict({"conductor-router": {"key": "sk-svc-xxx", "scopes": ["llm:*", "events:*"]}})
    provider = ServiceKeyAuthProvider(registry)
    identity = provider.authenticate({"x-service-key": "sk-svc-xxx"})
"""

from maistro.auth._types import (
    Scope,
    ScopeCategory,
    ServiceIdentity,
    expand_scopes,
)
from maistro.auth.checker import ServiceKeyChecker
from maistro.auth.client import ServiceKeyClient
from maistro.auth.provider import ServiceKeyAuthProvider
from maistro.auth.registry import ServiceKeyRegistry

_OAUTH_EXPORTS = (
    "IdentityLinkStore",
    "IdentityLinker",
    "IdTokenVerifier",
    "InMemoryIdentityLinkStore",
    "InMemoryStateStore",
    "JWKSIdTokenVerifier",
    "OAuth2Client",
    "OAuthError",
    "OAuthExchange",
    "OAuthExchangeError",
    "OAuthIdentity",
    "OAuthProviderConfig",
    "OAuthStateEntry",
    "OAuthStateError",
    "OAuthToken",
    "OAuthTokenValidationError",
    "StateStore",
    "UnverifiedJWTClaimsValidator",
    "default_id_token_verifier",
)


def __getattr__(name: str) -> object:
    if name in (
        "extract_service_identity",
        "require_any_scope",
        "require_scope",
        "setup_service_auth",
    ):
        from maistro.auth import middleware as _m

        return getattr(_m, name)
    if name in _OAUTH_EXPORTS:
        from maistro.auth import oauth as _o

        return getattr(_o, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "IdTokenVerifier",
    "IdentityLinkStore",
    "IdentityLinker",
    "InMemoryIdentityLinkStore",
    "InMemoryStateStore",
    "JWKSIdTokenVerifier",
    "OAuth2Client",
    "OAuthError",
    "OAuthExchange",
    "OAuthExchangeError",
    "OAuthIdentity",
    "OAuthProviderConfig",
    "OAuthStateEntry",
    "OAuthStateError",
    "OAuthToken",
    "OAuthTokenValidationError",
    "Scope",
    "ScopeCategory",
    "ServiceIdentity",
    "ServiceKeyAuthProvider",
    "ServiceKeyChecker",
    "ServiceKeyClient",
    "ServiceKeyRegistry",
    "StateStore",
    "UnverifiedJWTClaimsValidator",
    "default_id_token_verifier",
    "expand_scopes",
    "extract_service_identity",
    "require_any_scope",
    "require_scope",
    "setup_service_auth",
]
