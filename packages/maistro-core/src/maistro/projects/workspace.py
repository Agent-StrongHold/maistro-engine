"""Canonical Workspace access model over legacy Project persistence.

Workspace is the product environment/ownership boundary. Project remains the
legacy durable representation during migration, so ``Workspace`` is an identity-
preserving alias of ``Project`` rather than a second root.

Access is modeled separately through ``WorkspaceMembership``. A user may belong
to many Workspaces and a Workspace may have many users. Canonical roles are
member, contributor, and owner.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .store import InMemoryProjectStore, ProjectStore
from .types import (
    Project,
    ProjectAccessDenied,
    ProjectMemberRole,
    ProjectNotFound,
    ProjectQuotaExceeded,
    ProjectSettings,
)

Workspace = Project
WorkspaceSettings = ProjectSettings
WorkspaceNotFound = ProjectNotFound
WorkspaceAccessDenied = ProjectAccessDenied
WorkspaceQuotaExceeded = ProjectQuotaExceeded


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    CONTRIBUTOR = "contributor"
    MEMBER = "member"


class WorkspaceMembership(BaseModel):
    """A user's access relationship to one Workspace."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    user_id: str
    role: WorkspaceRole = WorkspaceRole.MEMBER
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("workspace_id", "user_id")
    @classmethod
    def _require_non_blank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @property
    def can_use(self) -> bool:
        return True

    @property
    def can_contribute(self) -> bool:
        return self.role in (WorkspaceRole.OWNER, WorkspaceRole.CONTRIBUTOR)

    @property
    def can_administer(self) -> bool:
        return self.role is WorkspaceRole.OWNER


WorkspaceMember = WorkspaceMembership


def workspace_role_from_legacy(role: ProjectMemberRole) -> WorkspaceRole:
    if role is ProjectMemberRole.OWNER:
        return WorkspaceRole.OWNER
    if role is ProjectMemberRole.EDITOR:
        return WorkspaceRole.CONTRIBUTOR
    return WorkspaceRole.MEMBER


def legacy_project_role_for_workspace_role(role: WorkspaceRole) -> ProjectMemberRole:
    if role is WorkspaceRole.OWNER:
        return ProjectMemberRole.OWNER
    if role is WorkspaceRole.CONTRIBUTOR:
        return ProjectMemberRole.EDITOR
    return ProjectMemberRole.VIEWER


def memberships_for(workspace: Workspace) -> tuple[WorkspaceMembership, ...]:
    memberships: list[WorkspaceMembership] = [
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=workspace.owner_user_id,
            role=WorkspaceRole.OWNER,
            added_at=workspace.created_at,
        )
    ]
    seen = {workspace.owner_user_id}
    for member in workspace.members:
        if member.user_id in seen:
            continue
        memberships.append(
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=member.user_id,
                role=workspace_role_from_legacy(member.role),
                added_at=member.added_at,
            )
        )
        seen.add(member.user_id)
    return tuple(memberships)


def membership_for(workspace: Workspace, user_id: str) -> WorkspaceMembership | None:
    return next((m for m in memberships_for(workspace) if m.user_id == user_id), None)


class WorkspaceOwnershipError(ValueError):
    pass


def _scope_value(value: object, field: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _validated_scope(value: object | None, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceOwnershipError(f"{field} must be a non-empty string")
    return value


def resolve_workspace_id(value: object) -> str:
    if isinstance(value, Project):
        return value.id

    workspace_id = _validated_scope(_scope_value(value, "workspace_id"), "workspace_id")
    project_id = _validated_scope(_scope_value(value, "project_id"), "project_id")

    if workspace_id is not None and project_id is not None and workspace_id != project_id:
        raise WorkspaceOwnershipError(
            "workspace_id and project_id identify different Workspaces: "
            f"{workspace_id!r} != {project_id!r}"
        )

    resolved = workspace_id or project_id
    if resolved is None:
        raise WorkspaceOwnershipError(
            "durable object must declare workspace_id (or legacy project_id during migration)"
        )
    return resolved


@runtime_checkable
class WorkspaceStore(ProjectStore, Protocol):
    async def list_memberships(self, workspace_id: str) -> list[WorkspaceMembership]: ...

    async def get_membership(
        self, workspace_id: str, *, user_id: str
    ) -> WorkspaceMembership | None: ...

    async def set_membership(
        self, workspace_id: str, *, user_id: str, role: WorkspaceRole
    ) -> WorkspaceMembership: ...

    async def remove_membership(self, workspace_id: str, *, user_id: str) -> Workspace: ...


class InMemoryWorkspaceStore(InMemoryProjectStore):
    async def list_memberships(self, workspace_id: str) -> list[WorkspaceMembership]:
        workspace = await self.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFound(workspace_id)
        return list(memberships_for(workspace))

    async def get_membership(
        self, workspace_id: str, *, user_id: str
    ) -> WorkspaceMembership | None:
        workspace = await self.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFound(workspace_id)
        return membership_for(workspace, user_id)

    async def set_membership(
        self, workspace_id: str, *, user_id: str, role: WorkspaceRole
    ) -> WorkspaceMembership:
        workspace = await self.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFound(workspace_id)

        if workspace.owner_user_id == user_id:
            if role is not WorkspaceRole.OWNER:
                raise WorkspaceAccessDenied(
                    "the legacy primary owner cannot be downgraded through the compatibility adapter"
                )
            owner = membership_for(workspace, user_id)
            assert owner is not None
            return owner

        updated = await self.add_member(
            workspace_id,
            user_id=user_id,
            role=legacy_project_role_for_workspace_role(role),
        )
        projected = membership_for(updated, user_id)
        assert projected is not None
        return projected

    async def remove_membership(self, workspace_id: str, *, user_id: str) -> Workspace:
        return await self.remove_member(workspace_id, user_id=user_id)


__all__ = [
    "InMemoryWorkspaceStore",
    "Workspace",
    "WorkspaceAccessDenied",
    "WorkspaceMember",
    "WorkspaceMembership",
    "WorkspaceNotFound",
    "WorkspaceOwnershipError",
    "WorkspaceQuotaExceeded",
    "WorkspaceRole",
    "WorkspaceSettings",
    "WorkspaceStore",
    "legacy_project_role_for_workspace_role",
    "membership_for",
    "memberships_for",
    "resolve_workspace_id",
    "workspace_role_from_legacy",
]
