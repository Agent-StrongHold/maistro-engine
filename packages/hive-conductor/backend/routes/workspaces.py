"""Workspace tabs — Persona/Workspace system (replaces the hardcoded PM Fleet mode).

Phase A: manual create/list/get. Phase C adds the persona-template checklist
endpoint (accept/modify tools/skills derived from the chosen persona's own
declared spawns). Phase D adds the theme catalog + per-workspace tone
override; the actual CSS/tab-bar wiring lands in Phase G. No interview
wiring, no sticky tool bindings yet — those are later phases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import stores
from fastapi import APIRouter, HTTPException, Request
from models.workspace import Workspace, WorkspaceMember
from pydantic import BaseModel, ConfigDict
from services.themes import THEME_CATALOG, ThemeOption, is_valid_theme_id

from maistro.personas.checklist import CapabilityItem, capability_checklist, default_checklist_ids
from maistro.personas.rubric import load_templates

router = APIRouter(tags=["workspaces"])


def _now() -> datetime:
    return datetime.now(UTC)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    return str(user.get("id") or user.get("username") or "dev")


def _visible_to(user_id: str, workspace: Workspace) -> bool:
    return any(m.user_id == user_id for m in workspace.members)


class PersonaChecklistResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    persona_template_id: str
    items: list[CapabilityItem]
    default_accepted: list[str]


@router.get("/persona-templates/{persona_id}/checklist", response_model=PersonaChecklistResponse)
def get_persona_checklist(persona_id: str) -> PersonaChecklistResponse:
    """The checklist a workspace-creation wizard shows: every tool/skill the
    chosen persona declares, derived from its own `spawns` -- not a separate
    hardcoded catalog. `default_accepted` pre-checks everything; the wizard
    lets the user uncheck what they don't want."""
    template = load_templates().get(persona_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"unknown persona template: {persona_id}")
    return PersonaChecklistResponse(
        persona_template_id=persona_id,
        items=capability_checklist(template),
        default_accepted=default_checklist_ids(template),
    )


@router.get("/themes", response_model=list[ThemeOption])
def list_themes() -> list[ThemeOption]:
    return THEME_CATALOG


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
    # Accept/modify result from GET .../checklist. Omitted or null means
    # "accept everything the persona declares" (if it resolves); an explicit
    # list -- including [] -- is honored exactly, so a user can deliberately
    # start a workspace with zero enabled capabilities.
    checklist: list[str] | None = None
    # Phase D: visual accent, one of GET /themes' ids. Invalid ids 422 rather
    # than silently falling back, so a wizard can't produce an unrenderable tab.
    theme_id: str = "default"
    voice_tone_override: str | None = None


@router.post("", response_model=Workspace, status_code=201)
def create_workspace(body: CreateWorkspaceBody, request: Request) -> Workspace:
    if not is_valid_theme_id(body.theme_id):
        raise HTTPException(status_code=422, detail=f"unknown theme_id: {body.theme_id}")
    user_id = _user_id(request)
    workspace_id = str(uuid4())
    t = _now()
    checklist = body.checklist
    if checklist is None:
        template = load_templates().get(body.persona_template_id)
        checklist = default_checklist_ids(template) if template is not None else []
    workspace = Workspace(
        id=workspace_id,
        persona_template_id=body.persona_template_id,
        name=body.name,
        members=[WorkspaceMember(user_id=user_id, role="owner")],
        checklist=checklist,
        theme_id=body.theme_id,
        voice_tone_override=body.voice_tone_override,
        created_at=t,
        updated_at=t,
    )
    stores.workspaces[workspace_id] = workspace
    return workspace
