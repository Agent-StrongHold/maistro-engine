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
from maistro.auth.client import ServiceKeyClient
from maistro.auth.middleware import (
    extract_service_identity,
    require_any_scope,
    require_scope,
    setup_service_auth,
)
from maistro.auth.provider import ServiceKeyAuthProvider
from maistro.auth.registry import ServiceKeyRegistry

__all__ = [
    "Scope",
    "ScopeCategory",
    "ServiceIdentity",
    "ServiceKeyAuthProvider",
    "ServiceKeyClient",
    "ServiceKeyRegistry",
    "expand_scopes",
    "extract_service_identity",
    "require_any_scope",
    "require_scope",
    "setup_service_auth",
]
