from __future__ import annotations

import pytest

from maistro.projects import ProjectMemberRole
from maistro.workspaces import InMemoryWorkspaceStore, WorkspaceAccessDenied, WorkspaceRole


@pytest.mark.asyncio
async def test_workspace_store_maps_roles_to_legacy_storage() -> None:
    store = InMemoryWorkspaceStore()
    workspace = await store.create(owner_user_id="alice", name="Alpha")

    await store.set_membership(workspace.id, user_id="bob", role=WorkspaceRole.CONTRIBUTOR)
    await store.set_membership(workspace.id, user_id="cara", role=WorkspaceRole.MEMBER)

    legacy = await store.get(workspace.id)
    assert legacy is not None
    assert {item.user_id: item.role for item in legacy.members} == {
        "bob": ProjectMemberRole.EDITOR,
        "cara": ProjectMemberRole.VIEWER,
    }


@pytest.mark.asyncio
async def test_primary_owner_role_is_preserved_by_compatibility_store() -> None:
    store = InMemoryWorkspaceStore()
    workspace = await store.create(owner_user_id="alice", name="Alpha")

    with pytest.raises(WorkspaceAccessDenied):
        await store.set_membership(workspace.id, user_id="alice", role=WorkspaceRole.MEMBER)

    owner = await store.get_membership(workspace.id, user_id="alice")
    assert owner is not None
    assert owner.role is WorkspaceRole.OWNER
