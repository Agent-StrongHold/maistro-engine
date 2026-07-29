"""Workspace tabs — Persona/Workspace system (replaces the hardcoded PM Fleet mode).

Phase A: manual create/list/get only. No interview, no checklist derivation,
no theme, no sticky tool bindings yet — those are later phases. A workspace
just records which persona it instantiates and who owns it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import stores
from fastapi import APIRouter, HTTPException, Request
from models.workspace import Workspace, WorkspaceMember
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["workspaces"])


def _now() -> datetime:
    return datetime.now(UTC)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    return str(user.get("id") or user.get("username") or "dev")


def _visible_to(user_id: str, workspace: Workspace) -> bool:
    return any(m.user_id == user_id for m in workspace.members)


@router.get("", response_model=list[Workspace])
def list_workspaces(request: Request) -> list[Workspace]:
    user_id = _user_id(request)
    return [w for w in stores.workspaces.values() if _visible_to(user_id, w)]


@router.get("/{workspace_id}", response_model=Workspace)
def get_workspace(workspace_id: str, request: Request) -> Workspace:
    workspace = stores.workspaces.get(workspace_id)
    if workspace is None or not _visible_to(_user_id(request), workspace):
        raise HTTPException(status_code=404, detail="workspace not found")
    return workspace


class CreateWorkspaceBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    persona_template_id: str
    name: str


@router.post("", response_model=Workspace, status_code=201)
def create_workspace(body: CreateWorkspaceBody, request: Request) -> Workspace:
    user_id = _user_id(request)
    workspace_id = str(uuid4())
    t = _now()
    workspace = Workspace(
        id=workspace_id,
        persona_template_id=body.persona_template_id,
        name=body.name,
        members=[WorkspaceMember(user_id=user_id, role="owner")],
        created_at=t,
        updated_at=t,
    )
    stores.workspaces[workspace_id] = workspace
    return workspace
