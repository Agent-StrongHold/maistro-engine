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
    "/v1/voice/",
    "/health",
)

# FastAPI's default docs/openapi paths don't end in "/" (the real route is
# /openapi.json), so they can't use the boundary-safe prefix check below —
# keep them on a plain startswith() match.
_PUBLIC_PREFIXES_LOOSE = (
    "/docs",
    "/openapi",
    "/redoc",
)

_PUBLIC_EXACT = frozenset(
    {
        "/",
        "/v1/setup/status",
        "/v1/setup/presets",
        "/v1/auth/login",
        "/v1/auth/register",
        "/v1/auth/whoami",
        "/favicon.ico",
    }
)

_ADMIN_CHAT_BLOCKED = ("/v1/chat/",)

_PROTECTED_OPS: dict[str, dict[str, str]] = {
    "DELETE": {
        "/v1/settings": "config.delete",
        "/v1/agents": "agents.delete",
        "/v1/skills": "skills.delete",
        "/v1/mcp": "mcp.delete",
        # Killing another principal's harness session is a denial of service on
        # in-flight work, so it needs the same scope that starting one does.
        "/v1/harness": "harness.execute",
        "/v1/containers": "containers.control",
        "/v1/credentials": "credentials.write",
        "/v1/dags": "dags.write",
        "/v1/schedules": "schedules.write",
    },
    "POST": {
        "/v1/settings": "config.write",
        # The whole /v1/mcp mutating surface, not just /servers: discover and
        # test connect to operator-supplied endpoints, which is the same
        # trust decision as registering one.
        "/v1/mcp": "mcp.write",
        "/v1/agents": "agents.write",
        "/v1/skills": "skills.write",
        # Talks to the Docker socket directly — host infrastructure control.
        "/v1/containers": "containers.control",
        # DAGs execute graphs whose nodes include harness/synth-DAG kinds:
        # creating or running one is agent execution, and an unscoped DAG run
        # would be a bypass of harness.execute via composition.
        "/v1/dags": "dags.write",
        # Accepting an optimizer proposal rewrites a DAG — same surface.
        "/v1/optimizer": "dags.write",
        # A schedule is recurring autonomous execution.
        "/v1/schedules": "schedules.write",
        # The evolution tournament is the self-improvement loop's other door.
        "/v1/evolution": "rsi.execute",
        # Executes GitHub/GitLab tools with stored credentials against real
        # external trackers.
        "/v1/pm-fleet/tools": "pm.execute",
        # Audit entries name an arbitrary `actor`: an unscoped writer is a
        # log-forgery primitive, and the app writes its own entries in-process,
        # not over HTTP — no product flow needs this route unelevated.
        "/v1/audit": "audit.write",
        # The inbound harness starts a coding agent against an operator-supplied
        # `workdir`: POST /v1/harness/sessions is code execution on this host,
        # and .../send steers it. Authentication alone was already required
        # (dispatch 401s any unauthenticated /v1/ path), but *every*
        # authenticated principal could reach it — including a role="user"
        # account with permissions=[]. Deliberately its own scope rather than
        # agents.write: being cleared to edit an agent's configuration is not
        # the same as being cleared to execute code as it.
        "/v1/harness": "harness.execute",
        # RSI runs are the self-modification loop — they push branches and can
        # open PRs. Separate scope again, because granting code execution on a
        # scratch workdir is a smaller decision than granting the loop that
        # rewrites this repository.
        "/v1/rsi": "rsi.execute",
        # Capability discovery + approval resolution (approving a destructive
        # infra action is high-stakes) — gate behind config.write.
        "/v1/capabilities": "config.write",
    },
    "PUT": {
        "/v1/settings": "config.write",
        "/v1/mcp/servers": "mcp.write",
        "/v1/agents": "agents.write",
        "/v1/skills": "skills.write",
        "/v1/credentials": "credentials.write",
        "/v1/dags": "dags.write",
        "/v1/schedules": "schedules.write",
    },
    "PATCH": {
        "/v1/settings": "config.write",
        "/v1/mcp/servers": "mcp.write",
        "/v1/capabilities": "config.write",
        # Toggling a skill changes what every future agent run may do.
        "/v1/skills": "skills.write",
    },
}


def _matches_public_prefix(path: str, prefix: str) -> bool:
    """True if path is exactly prefix, or prefix followed by '/'.

    Plain str.startswith() would also match unrelated sibling routes that
    merely share the prefix as a string (e.g. "/healthcheck-internal"
    starting with "/health"). Mirrors the boundary fix in
    tools/sandbox/workspace.py's path-prefix allowlist.
    """
    stripped = prefix.rstrip("/")
    return path == stripped or path.startswith(stripped + "/")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        if (
            path in _PUBLIC_EXACT
            or any(_matches_public_prefix(path, p) for p in _PUBLIC_PREFIXES)
            or any(path.startswith(p) for p in _PUBLIC_PREFIXES_LOOSE)
        ):
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
                    content={
                        "detail": "Admin account cannot use chat. Use your daily user account."
                    },
                )

            required_perm = self._required_permission(request)
            if required_perm and not self._check_permission(user, required_perm):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": f"Permission '{required_perm}' required. Elevate to proceed."
                    },
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
        # Agent invoke (POST /v1/agents/{id}/invoke) is autonomous read — don't
        # gate behind elevation. Match the trailing segment, not a bare
        # substring: "in path" would also exempt any future route that merely
        # contains "/invoke" elsewhere (e.g. "/v1/agents/invoke-history").
        if path.endswith("/invoke"):
            return None
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
