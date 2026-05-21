"""Auth middleware — session cookies, role-based access, task-scoped elevation.

Public paths (setup, login, health, static) bypass auth.
Admin role is blocked from /v1/chat/ routes (break-glass only).
Protected ops require elevation bound to a task — permissions die with the task.
"""

from __future__ import annotations

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("hive.auth_middleware")

_PUBLIC_PREFIXES = (
    "/v1/setup/",
    "/v1/auth/login",
    "/v1/voice/",
    "/health",
    "/docs",
    "/openapi",
    "/redoc",
)

_PUBLIC_EXACT = frozenset({
    "/",
    "/v1/setup/status",
    "/v1/setup/presets",
    "/v1/auth/login",
    "/v1/auth/whoami",
    "/favicon.ico",
})

_ADMIN_CHAT_BLOCKED = (
    "/v1/chat/",
)

_PROTECTED_OPS: dict[str, dict[str, str]] = {
    "DELETE": {
        "/v1/settings": "config.delete",
        "/v1/agents": "agents.delete",
        "/v1/skills": "skills.delete",
        "/v1/mcp": "mcp.delete",
    },
    "POST": {
        "/v1/settings": "config.write",
    },
    "PUT": {
        "/v1/settings": "config.write",
    },
}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        if path in _PUBLIC_EXACT or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        if path.startswith("/v1/"):
            user = self._get_user(request)
            if user is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )

            request.state.user = user

            if user["role"] == "admin" and self._is_chat(path):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Admin account cannot use chat. Use your daily user account."},
                )

            required_perm = self._required_permission(request)
            if required_perm and not self._check_permission(user, required_perm):
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Permission '{required_perm}' required. Elevate to proceed."},
                )

        return await call_next(request)

    def _get_user(self, request: Request) -> dict | None:
        session_id = request.cookies.get("hive_session")
        if not session_id:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                session_id = auth_header[7:]
        if not session_id:
            return None
        try:
            from routes.auth import get_current_user

            return get_current_user(session_id)
        except Exception:
            return None

    def _is_chat(self, path: str) -> bool:
        return any(path.startswith(p) for p in _ADMIN_CHAT_BLOCKED)

    def _required_permission(self, request: Request) -> str | None:
        method_perms = _PROTECTED_OPS.get(request.method, {})
        path = request.url.path
        for prefix, perm in method_perms.items():
            if path.startswith(prefix):
                return perm
        return None

    def _check_permission(self, user: dict, perm: str) -> bool:
        if user.get("role") == "admin":
            return True
        user_perms = user.get("permissions", [])
        if perm not in user_perms:
            return False
        elevated = user.get("elevated_permissions", [])
        return perm in elevated
