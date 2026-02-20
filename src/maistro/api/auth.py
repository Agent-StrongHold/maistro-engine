"""Bearer token authentication for API endpoints."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from maistro.config.settings import Settings, get_settings

security_scheme = HTTPBearer(auto_error=False)


def verify_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str | None:
    """Verify bearer token against configured API keys.

    If no API keys are configured, authentication is disabled (dev mode).
    Returns the validated token or None if auth is disabled.
    """
    if not settings.api_keys:
        # No keys configured — dev mode, allow all requests
        return None

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    for key in settings.api_keys:
        if hmac.compare_digest(token.encode(), key.encode()):
            return token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Dependency alias for route injection
RequireAuth = Annotated[str | None, Depends(verify_api_key)]
