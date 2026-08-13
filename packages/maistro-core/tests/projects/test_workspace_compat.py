"""Canonical Workspace compatibility tests.

Workspace is deliberately introduced over the existing Project persistence
contract.  These tests prevent a migration from silently creating a second
ownership root, changing durable IDs, or widening Project membership rules.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from maistro.projects import (
    InMemoryProjectStore,
    InMemoryWorkspaceStore,
    Project,
    ProjectMemberRole,
    Workspace,
    WorkspaceMember,
    WorkspaceOwnershipError,
    WorkspaceRole,
    WorkspaceStore,
    resolve_workspace_id,
)


@dataclass(frozen=True)
class _CanonicalChild:
    workspace_id: str


@dataclass(frozen=True)
class _LegacyChild:
    project_id: str


@dataclass(frozen=True)
class _DualScopedChild:
    workspace_id: str
    project_id: str


def test_workspace_is_identity_preserving_project_compatibility_alias() -> None:
    assert Workspace is Project
    workspace = Workspace(id="ws-1", owner_user_id="alice", name="Alpha")
    assert isinstance(workspace, Project)
    assert workspace.id == "ws-1"
    # No new storage column is introduced merely by adopting canonical naming.
    assert "workspace_id" not in workspace.model_dump()


def test_workspace_store_is_existing_project_store_contract() -> None:
    assert InMemoryWorkspaceStore is InMemoryProjectStore
    # The Protocol alias also stays the exact same runtime contract.
    assert WorkspaceStore.__name__ == "ProjectStore"


async def test_workspace_store_preserves_durable_id_and_legacy_read_path() -> None:
    store = InMemoryWorkspaceStore()
    workspace = await store.create(owner_user_id="alice", name="Alpha")

    canonical_id = resolve_workspace_id(workspace)
    legacy_read = await store.get(canonical_id)

    assert legacy_read is not None
    assert canonical_id == workspace.id == legacy_read.id
    assert legacy_read.name == "Alpha"


def test_workspace_role_preserves_existing_permission_semantics() -> None:
    assert WorkspaceRole is ProjectMemberRole
    workspace = Workspace(id="ws-1", owner_user_id="alice", name="Alpha")
    workspace = workspace.model_copy(
        update={
            "members": [
                WorkspaceMember(user_id="bob", role=WorkspaceRole.VIEWER),
            ]
        }
    )

    assert workspace.role_of("alice") == WorkspaceRole.OWNER
    assert workspace.can_mutate("alice") is True
    assert workspace.role_of("bob") == WorkspaceRole.VIEWER
    assert workspace.can_mutate("bob") is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (_CanonicalChild(workspace_id="ws-1"), "ws-1"),
        (_LegacyChild(project_id="ws-2"), "ws-2"),
        (_DualScopedChild(workspace_id="ws-3", project_id="ws-3"), "ws-3"),
        ({"workspace_id": "ws-4"}, "ws-4"),
        ({"project_id": "ws-5"}, "ws-5"),
        ({"workspace_id": "ws-6", "project_id": "ws-6"}, "ws-6"),
    ],
)
def test_resolve_workspace_id_accepts_canonical_and_legacy_scopes(
    value: object, expected: str
) -> None:
    assert resolve_workspace_id(value) == expected


def test_resolve_workspace_id_rejects_conflicting_dual_scope() -> None:
    with pytest.raises(WorkspaceOwnershipError, match="different Workspaces"):
        resolve_workspace_id(_DualScopedChild(workspace_id="ws-a", project_id="ws-b"))


@pytest.mark.parametrize(
    "value",
    [
        object(),
        {"id": "looks-like-a-workspace-but-is-not-declared-as-one"},
        {"workspace_id": ""},
        {"project_id": 123},
    ],
)
def test_resolve_workspace_id_fails_closed_without_valid_ownership(value: object) -> None:
    with pytest.raises(WorkspaceOwnershipError):
        resolve_workspace_id(value)
