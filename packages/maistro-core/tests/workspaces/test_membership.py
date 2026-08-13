from __future__ import annotations

import pytest

from maistro.projects import Project, ProjectMember, ProjectMemberRole
from maistro.workspaces import Workspace, WorkspaceMembership, WorkspaceRole, memberships_for


def test_workspace_remains_project_compatibility_identity() -> None:
    assert Workspace is Project


@pytest.mark.parametrize(
    ("role", "can_use", "can_contribute", "can_administer"),
    [
        (WorkspaceRole.MEMBER, True, False, False),
        (WorkspaceRole.CONTRIBUTOR, True, True, False),
        (WorkspaceRole.OWNER, True, True, True),
    ],
)
def test_workspace_role_tiers(
    role: WorkspaceRole,
    can_use: bool,
    can_contribute: bool,
    can_administer: bool,
) -> None:
    membership = WorkspaceMembership(workspace_id="ws-1", user_id="alice", role=role)
    assert membership.can_use is can_use
    assert membership.can_contribute is can_contribute
    assert membership.can_administer is can_administer


def test_legacy_members_project_to_canonical_memberships() -> None:
    workspace = Workspace(
        id="ws-1",
        owner_user_id="alice",
        name="Alpha",
        members=[
            ProjectMember(user_id="bob", role=ProjectMemberRole.EDITOR),
            ProjectMember(user_id="cara", role=ProjectMemberRole.VIEWER),
        ],
    )

    projected = {item.user_id: item.role for item in memberships_for(workspace)}
    assert projected == {
        "alice": WorkspaceRole.OWNER,
        "bob": WorkspaceRole.CONTRIBUTOR,
        "cara": WorkspaceRole.MEMBER,
    }
