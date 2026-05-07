"""Composite authentication provider: tries multiple providers in order.

Used when multiple auth mechanisms coexist:
1. JWT (Keycloak/Entra ID) -- for SSO users
2. Static API key + OpenWebUI headers -- for service-to-service + dashboard
3. Webhook secret -- for n8n/external integrations

First provider to succeed wins. All fail -> ValueError.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maistro.security._types import AuthContext

logger = logging.getLogger("maistro.auth.composite")


class CompositeAuthProvider:
    """Tries multiple auth providers in order. First success wins."""

    def __init__(self, providers: list[Any]) -> None:
        self._providers = providers

    async def authenticate(
        self,
        authorization: str | None,
        headers: dict[str, str] | None = None,
    ) -> AuthContext:
        last_error: Exception | None = None

        for provider in self._providers:
            try:
                result: AuthContext = await provider.authenticate(authorization, headers=headers)
                return result
            except Exception as e:
                last_error = e
                continue

        if last_error:
            logger.debug("All auth providers failed. Last error: %s", last_error)
        raise ValueError("Authentication failed")
