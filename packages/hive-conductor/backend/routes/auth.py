"""Auth routes — login, logout, whoami, elevate (2FA stub).

Elevation is task-scoped: permissions are bound to a task_id and revoked
when the task completes, fails, or is cancelled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from routes.audit import log_audit

router = APIRouter(tags=["auth"])

_SESSION_COOKIE = "hive_session"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 7


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str
    password: str


class ElevateBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    password: str
    permissions: list[str] = Field(default_factory=list)
    task_id: str


def _resolve_session(session_id: str) -> dict[str, Any] | None:
    import stores

    if not session_id or session_id not in stores.sessions:
        return None
    sess = stores.sessions[session_id]
    if not isinstance(sess, dict):
        return None
    user_id = sess.get("user_id")
    if not user_id or user_id not in stores.users:
        return None
    return sess


def _active_grants(sess: dict[str, Any]) -> dict[str, list[str]]:
    grants = sess.get("elevated_grants", {})
    return {tid: perms for tid, perms in grants.items() if isinstance(perms, list)}


def get_current_user(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    sess = _resolve_session(session_id)
    if sess is None:
        return None
    import stores

    user = stores.users.get(sess["user_id"])
    if user is None or not user.is_active:
        return None
    grants = _active_grants(sess)
    all_elevated: list[str] = []
    for perms in grants.values():
        for p in perms:
            if p not in all_elevated:
                all_elevated.append(p)
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "permissions": user.permissions,
        "did": user.did,
        "elevated_permissions": all_elevated,
        "elevated_tasks": list(grants.keys()),
    }


def user_has_permission(session_id: str | None, perm: str) -> bool:
    if not session_id:
        return False
    sess = _resolve_session(session_id)
    if sess is None:
        return False
    import stores

    user = stores.users.get(sess["user_id"])
    if user is None:
        return False
    return user.has_permission(perm)


def revoke_task_elevation(session_id: str, task_id: str) -> None:
    import stores

    if session_id not in stores.sessions:
        return
    sess = stores.sessions[session_id]
    grants = sess.get("elevated_grants", {})
    if task_id in grants:
        del grants[task_id]
        stores.sessions[session_id] = {**sess, "elevated_grants": grants}


@router.post("/login")
def login(body: LoginBody, response: Response) -> dict[str, Any]:
    import stores

    for user in stores.users.values():
        if user.username == body.username and user.verify_password(body.password):
            if not user.is_active:
                raise HTTPException(status_code=403, detail="Account disabled")
            session_id = str(uuid4())
            stores.sessions[session_id] = {
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "permissions": user.permissions,
                "elevated_grants": {},
                "created_at": datetime.now(UTC).isoformat(),
            }
            response.set_cookie(
                key=_SESSION_COOKIE,
                value=session_id,
                max_age=_COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
            )
            log_audit("login", user.username)
            return {
                "ok": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role,
                    "permissions": user.permissions,
                    "did": user.did,
                },
            }
    log_audit("login_failed", body.username, severity="warning")
    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/logout")
def logout(response: Response, hive_session: str | None = Cookie(None)) -> dict[str, Any]:
    if hive_session:
        import stores

        user_info = _resolve_session(hive_session)
        actor = user_info.get("username", "unknown") if user_info else "unknown"
        stores.sessions.pop(hive_session, None)
        log_audit("logout", actor)
    response.delete_cookie(key=_SESSION_COOKIE)
    return {"ok": True}


@router.get("/whoami")
def whoami(hive_session: str | None = Cookie(None)) -> dict[str, Any]:
    user = get_current_user(hive_session)
    if user is None:
        return {"authenticated": False}
    return {"authenticated": True, "user": user}


@router.post("/elevate")
def elevate(body: ElevateBody, hive_session: str | None = Cookie(None)) -> dict[str, Any]:
    import stores

    if not hive_session or hive_session not in stores.sessions:
        raise HTTPException(status_code=401, detail="No session")
    sess = stores.sessions[hive_session]
    user = stores.users.get(sess["user_id"])
    if user is None or not user.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    requested = body.permissions if body.permissions else list(user.permissions)
    granted = [p for p in requested if user.has_permission(p)]
    if body.permissions and not granted:
        raise HTTPException(
            status_code=403,
            detail="None of the requested permissions are assigned to your account",
        )

    grants: dict[str, list[str]] = sess.get("elevated_grants", {})
    grants[body.task_id] = granted
    stores.sessions[hive_session] = {**sess, "elevated_grants": grants}
    log_audit("elevate", user.username, target=body.task_id, detail={"permissions": granted}, severity="warning")
    return {
        "ok": True,
        "task_id": body.task_id,
        "elevated_permissions": granted,
        "message": "Permissions elevated for this task. They will be revoked when the task completes.",
    }
