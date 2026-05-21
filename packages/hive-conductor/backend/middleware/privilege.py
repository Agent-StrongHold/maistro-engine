"""Privilege middleware — enforces admin/user access control on routes.

When privilege is available (Foundation.privilege_available), requests
are screened for admin-only operations. Otherwise, all access is allowed
(graceful degradation for dev mode).
"""

from __future__ import annotations

import fnmatch
import logging

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("hive.privilege_middleware")

_ADMIN_PATHS = frozenset({
    "/v1/settings",
})

_ADMIN_PREFIXES = (
    "/v1/install/",
    "/v1/admin/",
)


class PrivilegeMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not self._requires_admin(request):
            return await call_next(request)

        if not self._privilege_available():
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")

        token = auth_header[7:]
        if self._is_admin(token):
            return await call_next(request)

        if self._has_elevation(token, request.url.path):
            return await call_next(request)

        raise HTTPException(status_code=403, detail="Admin access required")

    def _requires_admin(self, request: Request) -> bool:
        path = request.url.path
        if path in _ADMIN_PATHS and request.method in ("PUT", "POST", "DELETE"):
            return True
        return any(path.startswith(p) for p in _ADMIN_PREFIXES)

    def _privilege_available(self) -> bool:
        try:
            from services.foundation import get_foundation

            return get_foundation().privilege_available
        except (RuntimeError, Exception):
            return False

    def _is_admin(self, token: str) -> bool:
        try:
            from services.foundation import get_foundation

            f = get_foundation()
            if not f.privilege_available or f.privilege is None:
                return True
            return f.privilege.is_admin(token)  # type: ignore[union-attr]
        except Exception:
            return True

    def _has_elevation(self, token: str, scope: str) -> bool:
        try:
            from services.foundation import get_foundation

            f = get_foundation()
            if not f.privilege_available or f.privilege is None:
                return False
            grants = f.privilege.active_grants(token)  # type: ignore[union-attr]
            return any(
                fnmatch.fnmatch(scope, g.scope)
                for g in grants
                if g.is_valid
            )
        except Exception:
            return False
