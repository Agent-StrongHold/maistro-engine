from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from maistro.workspaces.model import (
    Workspace,
    WorkspaceAccessDenied,
    WorkspaceMembership,
    WorkspaceNotFound,
    WorkspaceRole,
)


@runtime_checkable
class WorkspaceStore(Protocol):
    async def create(
        self,
        *,
        creator_user_id: str,
        name: str,
        description: str = "",
    ) -> Workspace: ...

    async def get(self, workspace_id: str) -> Workspace | None: ...

    async def update(self, workspace: Workspace) -> Workspace: ...

    async def delete(self, workspace_id: str) -> None: ...

    async def list_for_user(self, user_id: str) -> list[Workspace]: ...

    async def list_memberships(self, workspace_id: str) -> list[WorkspaceMembership]: ...

    async def get_membership(
        self,
        workspace_id: str,
        *,
        user_id: str,
    ) -> WorkspaceMembership | None: ...

    async def set_membership(
        self,
        workspace_id: str,
        *,
        user_id: str,
        role: WorkspaceRole,
    ) -> WorkspaceMembership: ...

    async def remove_membership(self, workspace_id: str, *, user_id: str) -> None: ...


class InMemoryWorkspaceStore:
    """Reference store with Workspace identity separated from membership."""

    def __init__(self) -> None:
        self._workspaces: dict[str, Workspace] = {}
        self._memberships: dict[tuple[str, str], WorkspaceMembership] = {}

    async def create(
        self,
        *,
        creator_user_id: str,
        name: str,
        description: str = "",
    ) -> Workspace:
        workspace = Workspace(name=name, description=description)
        self._workspaces[workspace.workspace_id] = workspace
        self._memberships[(workspace.workspace_id, creator_user_id)] = WorkspaceMembership(
            workspace_id=workspace.workspace_id,
            user_id=creator_user_id,
            role=WorkspaceRole.OWNER,
            added_at=workspace.created_at,
        )
        return workspace.model_copy(deep=True)

    async def get(self, workspace_id: str) -> Workspace | None:
        workspace = self._workspaces.get(workspace_id)
        return workspace.model_copy(deep=True) if workspace is not None else None

    async def update(self, workspace: Workspace) -> Workspace:
        if workspace.workspace_id not in self._workspaces:
            raise WorkspaceNotFound(workspace.workspace_id)
        updated = workspace.model_copy(update={"updated_at": datetime.now(UTC)})
        self._workspaces[workspace.workspace_id] = updated
        return updated.model_copy(deep=True)

    async def delete(self, workspace_id: str) -> None:
        if workspace_id not in self._workspaces:
            raise WorkspaceNotFound(workspace_id)
        del self._workspaces[workspace_id]
        for key in [key for key in self._memberships if key[0] == workspace_id]:
            del self._memberships[key]

    async def list_for_user(self, user_id: str) -> list[Workspace]:
        workspace_ids = {
            workspace_id
            for (workspace_id, member_user_id), membership in self._memberships.items()
            if member_user_id == user_id and membership.role in WorkspaceRole
        }
        workspaces = [
            self._workspaces[workspace_id].model_copy(deep=True)
            for workspace_id in workspace_ids
            if workspace_id in self._workspaces
        ]
        workspaces.sort(key=lambda item: item.created_at, reverse=True)
        return workspaces

    async def list_memberships(self, workspace_id: str) -> list[WorkspaceMembership]:
        self._require_workspace(workspace_id)
        memberships = [
            membership.model_copy(deep=True)
            for (member_workspace_id, _), membership in self._memberships.items()
            if member_workspace_id == workspace_id
        ]
        memberships.sort(key=lambda item: (item.added_at, item.user_id))
        return memberships

    async def get_membership(
        self,
        workspace_id: str,
        *,
        user_id: str,
    ) -> WorkspaceMembership | None:
        self._require_workspace(workspace_id)
        membership = self._memberships.get((workspace_id, user_id))
        return membership.model_copy(deep=True) if membership is not None else None

    async def set_membership(
        self,
        workspace_id: str,
        *,
        user_id: str,
        role: WorkspaceRole,
    ) -> WorkspaceMembership:
        self._require_workspace(workspace_id)
        existing = self._memberships.get((workspace_id, user_id))
        if existing is not None and existing.role is WorkspaceRole.OWNER and role is not WorkspaceRole.OWNER:
            self._ensure_another_owner(workspace_id, excluding_user_id=user_id)

        membership = WorkspaceMembership(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            added_at=existing.added_at if existing is not None else datetime.now(UTC),
        )
        self._memberships[(workspace_id, user_id)] = membership
        return membership.model_copy(deep=True)

    async def remove_membership(self, workspace_id: str, *, user_id: str) -> None:
        self._require_workspace(workspace_id)
        key = (workspace_id, user_id)
        existing = self._memberships.get(key)
        if existing is None:
            return
        if existing.role is WorkspaceRole.OWNER:
            self._ensure_another_owner(workspace_id, excluding_user_id=user_id)
        del self._memberships[key]

    def _require_workspace(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFound(workspace_id)
        return workspace

    def _ensure_another_owner(self, workspace_id: str, *, excluding_user_id: str) -> None:
        has_other_owner = any(
            member_workspace_id == workspace_id
            and member_user_id != excluding_user_id
            and membership.role is WorkspaceRole.OWNER
            for (member_workspace_id, member_user_id), membership in self._memberships.items()
        )
        if not has_other_owner:
            raise WorkspaceAccessDenied("a Workspace must retain at least one owner")


__all__ = ["InMemoryWorkspaceStore", "WorkspaceStore"]
