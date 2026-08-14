from __future__ import annotations

import pytest

from maistro.auth.resources import (
    AuthorizationResolver,
    MembershipStatus,
    ProjectMembership,
    ResourceKind,
    ResourceScope,
    ResourceScopeKind,
    WorkspaceMembership,
)


@pytest.fixture
def resolver() -> AuthorizationResolver:
    return AuthorizationResolver()


@pytest.fixture
def workspace_member() -> WorkspaceMembership:
    return WorkspaceMembership(
        workspace_id="ws-1",
        principal_id="user-1",
        grants=frozenset({"run:read", "run:execute", "credential:use", "binding:use", "policy:read"}),
    )


def test_workspace_membership_is_required(resolver: AuthorizationResolver) -> None:
    decision = resolver.resolve(permission="run:read", workspace_membership=None)
    assert decision.allowed is False
    assert decision.reason == "active workspace membership required"


def test_suspended_workspace_membership_is_rejected(resolver: AuthorizationResolver) -> None:
    membership = WorkspaceMembership(
        workspace_id="ws-1",
        principal_id="user-1",
        grants=frozenset({"run:read"}),
        status=MembershipStatus.SUSPENDED,
    )
    decision = resolver.resolve(permission="run:read", workspace_membership=membership)
    assert decision.allowed is False
    assert decision.effective_permissions == frozenset()


def test_workspace_grant_is_effective_without_project_narrowing(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    decision = resolver.resolve(
        permission="run:execute",
        workspace_membership=workspace_member,
        project_path=("root", "child"),
    )
    assert decision.allowed is True


def test_workspace_deny_cannot_be_regranted_by_project(resolver: AuthorizationResolver) -> None:
    membership = WorkspaceMembership(
        workspace_id="ws-1",
        principal_id="user-1",
        grants=frozenset({"run:read", "run:execute"}),
        denies=frozenset({"run:execute"}),
    )
    decision = resolver.resolve(
        permission="run:execute",
        workspace_membership=membership,
        project_path=("root",),
        project_memberships=(
            ProjectMembership(
                workspace_id="ws-1",
                project_id="root",
                principal_id="user-1",
                grants=frozenset({"run:execute"}),
            ),
        ),
    )
    assert decision.allowed is False
    assert "run:execute" in decision.denied_permissions
    assert "run:execute" not in decision.effective_permissions


def test_project_grants_can_narrow_but_never_widen(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    memberships = (
        ProjectMembership(
            workspace_id="ws-1",
            project_id="root",
            principal_id="user-1",
            grants=frozenset({"run:read", "credential:use"}),
        ),
        ProjectMembership(
            workspace_id="ws-1",
            project_id="child",
            principal_id="user-1",
            grants=frozenset({"run:read", "run:execute"}),
        ),
    )

    read = resolver.resolve(
        permission="run:read",
        workspace_membership=workspace_member,
        project_path=("root", "child"),
        project_memberships=memberships,
    )
    execute = resolver.resolve(
        permission="run:execute",
        workspace_membership=workspace_member,
        project_path=("root", "child"),
        project_memberships=memberships,
    )

    assert read.allowed is True
    assert execute.allowed is False
    assert "run:execute" not in execute.effective_permissions


def test_deny_is_sticky_and_wins_over_descendant_grant(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    memberships = (
        ProjectMembership(
            workspace_id="ws-1",
            project_id="root",
            principal_id="user-1",
            denies=frozenset({"credential:use"}),
        ),
        ProjectMembership(
            workspace_id="ws-1",
            project_id="child",
            principal_id="user-1",
            grants=frozenset({"credential:use"}),
        ),
    )
    decision = resolver.resolve(
        permission="credential:use",
        workspace_membership=workspace_member,
        project_path=("root", "child"),
        project_memberships=memberships,
    )
    assert decision.allowed is False
    assert "credential:use" in decision.denied_permissions


def test_sibling_membership_does_not_affect_target_path(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    decision = resolver.resolve(
        permission="run:execute",
        workspace_membership=workspace_member,
        project_path=("root", "child-a"),
        project_memberships=(
            ProjectMembership(
                workspace_id="ws-1",
                project_id="child-b",
                principal_id="user-1",
                denies=frozenset({"run:execute"}),
            ),
        ),
    )
    assert decision.allowed is True


def test_other_principal_membership_does_not_affect_resolution(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    decision = resolver.resolve(
        permission="run:execute",
        workspace_membership=workspace_member,
        project_path=("root",),
        project_memberships=(
            ProjectMembership(
                workspace_id="ws-1",
                project_id="root",
                principal_id="user-2",
                denies=frozenset({"run:execute"}),
            ),
        ),
    )
    assert decision.allowed is True


def test_other_workspace_membership_does_not_affect_resolution(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    decision = resolver.resolve(
        permission="run:execute",
        workspace_membership=workspace_member,
        project_path=("root",),
        project_memberships=(
            ProjectMembership(
                workspace_id="ws-2",
                project_id="root",
                principal_id="user-1",
                denies=frozenset({"run:execute"}),
            ),
        ),
    )
    assert decision.allowed is True


def test_suspended_project_membership_denies_path(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    decision = resolver.resolve(
        permission="run:read",
        workspace_membership=workspace_member,
        project_path=("root",),
        project_memberships=(
            ProjectMembership(
                workspace_id="ws-1",
                project_id="root",
                principal_id="user-1",
                status=MembershipStatus.SUSPENDED,
            ),
        ),
    )
    assert decision.allowed is False


def test_workspace_resource_visible_anywhere_in_same_workspace(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    scope = ResourceScope(
        workspace_id="ws-1",
        kind=ResourceScopeKind.WORKSPACE,
        resource_kind=ResourceKind.CREDENTIAL,
    )
    assert resolver.can_view_resource(
        scope=scope,
        workspace_membership=workspace_member,
        project_path=("root", "child"),
    )


def test_project_resource_visible_to_its_descendants_not_siblings(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    scope = ResourceScope(
        workspace_id="ws-1",
        kind=ResourceScopeKind.PROJECT,
        project_id="project-a",
        resource_kind=ResourceKind.BINDING,
    )
    assert resolver.can_view_resource(
        scope=scope,
        workspace_membership=workspace_member,
        project_path=("root", "project-a", "project-a-child"),
    )
    assert not resolver.can_view_resource(
        scope=scope,
        workspace_membership=workspace_member,
        project_path=("root", "project-b"),
    )


def test_suspended_workspace_member_cannot_view_resource(resolver: AuthorizationResolver) -> None:
    membership = WorkspaceMembership(
        workspace_id="ws-1",
        principal_id="user-1",
        status=MembershipStatus.SUSPENDED,
    )
    scope = ResourceScope(workspace_id="ws-1", kind=ResourceScopeKind.WORKSPACE)
    assert not resolver.can_view_resource(scope=scope, workspace_membership=membership)


def test_policy_scope_is_workspace_isolated(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    scope = ResourceScope(
        workspace_id="ws-2",
        kind=ResourceScopeKind.WORKSPACE,
        resource_kind=ResourceKind.POLICY,
    )
    assert not resolver.can_view_resource(
        scope=scope,
        workspace_membership=workspace_member,
        project_path=("root",),
    )


def test_project_scope_requires_project_id() -> None:
    with pytest.raises(ValueError, match="project_id"):
        ResourceScope(workspace_id="ws-1", kind=ResourceScopeKind.PROJECT)


def test_workspace_scope_rejects_project_id() -> None:
    with pytest.raises(ValueError, match="cannot carry project_id"):
        ResourceScope(
            workspace_id="ws-1",
            kind=ResourceScopeKind.WORKSPACE,
            project_id="root",
        )


def test_duplicate_membership_for_same_project_is_rejected(
    resolver: AuthorizationResolver,
    workspace_member: WorkspaceMembership,
) -> None:
    memberships = (
        ProjectMembership(workspace_id="ws-1", project_id="root", principal_id="user-1"),
        ProjectMembership(workspace_id="ws-1", project_id="root", principal_id="user-1"),
    )
    with pytest.raises(ValueError, match="duplicate project membership"):
        resolver.resolve(
            permission="run:read",
            workspace_membership=workspace_member,
            project_path=("root",),
            project_memberships=memberships,
        )
