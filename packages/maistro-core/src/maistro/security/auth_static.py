"""Static API key authentication provider.

Also extracts OpenWebUI user context from X-OpenWebUI-User-* headers
when present, building a richer AuthContext than the default SYSTEM_AUTH.
"""

from __future__ import annotations

import hmac

from maistro.security._types import SYSTEM_AUTH, AuthContext, IdentityKind


class StaticKeyAuthProvider:
    """Authenticates via static API key. Extracts OpenWebUI user headers."""

    def __init__(self, api_key: str, read_only: bool = False) -> None:
        self._api_key = api_key
        self._read_only = read_only

    async def authenticate(
        self,
        authorization: str | None,
        headers: dict[str, str] | None = None,
    ) -> AuthContext:
        if not authorization:
            msg = "Missing Authorization header"
            raise ValueError(msg)

        if not authorization.startswith("Bearer "):
            msg = "Invalid authorization format"
            raise ValueError(msg)

        token = authorization.removeprefix("Bearer ").strip()
        if not hmac.compare_digest(token, self._api_key):
            msg = "Invalid API key"
            raise ValueError(msg)

        if headers:
            owui_ctx = _extract_openwebui_context(headers)
            if owui_ctx:
                return owui_ctx

        if self._read_only:
            return AuthContext(
                user_id="system",
                username="system",
                roles=frozenset({"user"}),
                kind=IdentityKind.SYSTEM,
                auth_method="api_key",
            )

        return SYSTEM_AUTH


def _extract_openwebui_context(headers: dict[str, str]) -> AuthContext | None:
    email = headers.get("x-openwebui-user-email", "")
    name = headers.get("x-openwebui-user-name", "")
    user_id = headers.get("x-openwebui-user-id", "")

    if not (email or user_id):
        return None

    roles = frozenset({"user"})

    return AuthContext(
        user_id=user_id or email,
        username=name or email,
        roles=roles,
        kind=IdentityKind.USER,
        auth_method="openwebui_header",
    )
