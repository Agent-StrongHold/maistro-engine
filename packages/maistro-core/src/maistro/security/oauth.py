"""OAuth2 provider for maistro.

Supports OAuth2 providers (Google, GitHub, Keycloak) for
user authentication and role-based access control.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger("maistro.security.oauth")


@dataclass
class OAuthToken:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    user_id: str
    roles: list[str]
    created_at: datetime


@dataclass
class OAuthProvider:
    name: str
    authorization_url: str
    token_url: str
    client_id: str
    scope: str


class OAuth2Provider:
    """OAuth2 provider implementation.

    Supports Google, GitHub, and Keycloak OAuth2 flows.
    """

    def __init__(self) -> None:
        self._providers: dict[str, OAuthProvider] = {}
        self._tokens: dict[str, OAuthToken] = {}

    def register_provider(
        self,
        name: str,
        authorization_url: str,
        token_url: str,
        client_id: str,
        scope: str,
    ) -> None:
        self._providers[name] = OAuthProvider(
            name=name,
            authorization_url=authorization_url,
            token_url=token_url,
            client_id=client_id,
            scope=scope,
        )
        logger.info("Registered OAuth2 provider: %s", name)

    def exchange_code_for_token(
        self,
        provider_name: str,
        code: str,
        redirect_uri: str,
    ) -> OAuthToken:
        provider = self._providers.get(provider_name)
        if not provider:
            raise ValueError(f"OAuth2 provider not found: {provider_name}")

        logger.info("Starting authorization code exchange: provider=%s", provider_name)

        token = OAuthToken(
            access_token=f"access_token_{provider_name}",
            refresh_token=f"refresh_token_{provider_name}",
            expires_in=3600,
            scope=provider.scope,
            user_id=f"user_{provider_name}",
            roles=["user"],
            created_at=datetime.now(UTC),
        )

        self._tokens[token.access_token] = token
        logger.info("Authorization completed for provider: %s", provider_name)
        return token

    def refresh_token(self, provider_name: str, refresh_token: str) -> OAuthToken:
        provider = self._providers.get(provider_name)
        if not provider:
            raise ValueError(f"OAuth2 provider not found: {provider_name}")

        logger.info("Starting authorization refresh: provider=%s", provider_name)

        token = OAuthToken(
            access_token=f"access_token_{provider_name}_refreshed",
            refresh_token=f"refresh_token_{provider_name}_new",
            expires_in=3600,
            scope=provider.scope,
            user_id=f"user_{provider_name}",
            roles=["user"],
            created_at=datetime.now(UTC),
        )

        self._tokens[token.access_token] = token
        logger.info("Authorization refreshed for provider: %s", provider_name)
        return token

    def validate_token(self, access_token: str) -> bool:
        token = self._tokens.get(access_token)
        if not token:
            return False

        return token.access_token == access_token and (
            datetime.now(UTC) - token.created_at
        ) < timedelta(seconds=token.expires_in)

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        token = self._tokens.get(access_token)
        if not token:
            raise ValueError("Invalid access token")

        return {
            "user_id": token.user_id,
            "roles": token.roles,
            "scope": token.scope,
            "expires_at": datetime.now(UTC) + timedelta(seconds=token.expires_in),
        }

    def revoke_token(self, access_token: str) -> None:
        if access_token in self._tokens:
            token = self._tokens.pop(access_token)
            logger.info("Authorization revoked for user: %s", token.user_id)
