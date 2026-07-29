"""Route-level coverage for routes/workspaces.py (Persona/Workspace system, Phase A).

Phase A is manual create/list/get only: no interview, no checklist, no theme,
no sticky tool bindings yet.
"""

from __future__ import annotations

import pytest
import stores


@pytest.fixture(autouse=True)
def _clear_workspaces():
    for key in list(stores.workspaces.keys()):
        stores.workspaces.pop(key, None)
    yield
    for key in list(stores.workspaces.keys()):
        stores.workspaces.pop(key, None)


def test_create_workspace_persists_and_returns_it(admin_client) -> None:
    r = admin_client.post(
        "/v1/workspaces", json={"persona_template_id": "pm_fleet", "name": "PM Fleet"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["persona_template_id"] == "pm_fleet"
    assert body["name"] == "PM Fleet"
    assert body["active"] is True
    assert body["checklist"] == []
    assert body["tool_bindings"] == []
    assert body["theme_id"] == "default"
    assert body["voice_tone_override"] is None
    assert len(stores.workspaces) == 1


def test_user_can_have_two_workspaces_from_the_same_persona(admin_client) -> None:
    r1 = admin_client.post(
        "/v1/workspaces", json={"persona_template_id": "content_creator", "name": "Garden Channel"}
    )
    r2 = admin_client.post(
        "/v1/workspaces", json={"persona_template_id": "content_creator", "name": "Cooking Channel"}
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]

    listed = admin_client.get("/v1/workspaces")
    assert listed.status_code == 200
    ids = {w["id"] for w in listed.json()}
    assert {r1.json()["id"], r2.json()["id"]} <= ids


def test_get_workspace_by_id(admin_client) -> None:
    created = admin_client.post(
        "/v1/workspaces", json={"persona_template_id": "pm_fleet", "name": "PM Fleet"}
    ).json()
    r = admin_client.get(f"/v1/workspaces/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_unknown_workspace_404s(admin_client) -> None:
    r = admin_client.get("/v1/workspaces/does-not-exist")
    assert r.status_code == 404


def test_zero_permission_user_cannot_create_workspace(authed_client) -> None:
    r = authed_client.post(
        "/v1/workspaces", json={"persona_template_id": "pm_fleet", "name": "PM Fleet"}
    )
    assert r.status_code == 403


def test_workspaces_are_not_visible_to_other_users(authed_client, admin_client) -> None:
    """A workspace only lists/gets for its members — not every authenticated user."""
    created = admin_client.post(
        "/v1/workspaces", json={"persona_template_id": "pm_fleet", "name": "PM Fleet"}
    ).json()

    r = authed_client.get(f"/v1/workspaces/{created['id']}")
    assert r.status_code == 404

    listed = authed_client.get("/v1/workspaces")
    assert listed.status_code == 200
    assert created["id"] not in {w["id"] for w in listed.json()}


def _fake_pm_fleet_template():
    from maistro.personas.schema import PersonaTemplate, SpawnSpec

    return PersonaTemplate(
        kind="workspace",
        id="pm_fleet",
        spawns=[SpawnSpec(agent="intake", tools=["create_epic"], skills=[])],
    )


class TestPersonaChecklist:
    """Phase C: the checklist is derived from the persona's own declared spawns."""

    def test_returns_declared_capabilities(self, admin_client, monkeypatch) -> None:
        import routes.workspaces as workspaces_routes

        monkeypatch.setattr(
            workspaces_routes, "load_templates", lambda: {"pm_fleet": _fake_pm_fleet_template()}
        )

        r = admin_client.get("/v1/workspaces/persona-templates/pm_fleet/checklist")
        assert r.status_code == 200
        body = r.json()
        assert body["persona_template_id"] == "pm_fleet"
        assert body["items"] == [
            {
                "id": "intake.tool.create_epic",
                "agent": "intake",
                "kind": "tool",
                "name": "create_epic",
                "label": "Create Epic",
            }
        ]
        assert body["default_accepted"] == ["intake.tool.create_epic"]

    def test_unknown_persona_404s(self, admin_client, monkeypatch) -> None:
        import routes.workspaces as workspaces_routes

        monkeypatch.setattr(workspaces_routes, "load_templates", lambda: {})
        r = admin_client.get("/v1/workspaces/persona-templates/nope/checklist")
        assert r.status_code == 404


class TestCreateWorkspaceChecklist:
    def test_explicit_checklist_is_honored(self, admin_client) -> None:
        r = admin_client.post(
            "/v1/workspaces",
            json={
                "persona_template_id": "pm_fleet",
                "name": "PM Fleet",
                "checklist": ["intake.tool.create_epic"],
            },
        )
        assert r.status_code == 201
        assert r.json()["checklist"] == ["intake.tool.create_epic"]

    def test_explicit_empty_checklist_is_honored_not_treated_as_missing(self, admin_client) -> None:
        r = admin_client.post(
            "/v1/workspaces",
            json={"persona_template_id": "pm_fleet", "name": "PM Fleet", "checklist": []},
        )
        assert r.status_code == 201
        assert r.json()["checklist"] == []

    def test_omitted_checklist_defaults_from_persona_when_resolvable(
        self, admin_client, monkeypatch
    ) -> None:
        import routes.workspaces as workspaces_routes

        monkeypatch.setattr(
            workspaces_routes, "load_templates", lambda: {"pm_fleet": _fake_pm_fleet_template()}
        )

        r = admin_client.post(
            "/v1/workspaces", json={"persona_template_id": "pm_fleet", "name": "PM Fleet"}
        )
        assert r.status_code == 201
        assert r.json()["checklist"] == ["intake.tool.create_epic"]


class TestWorkspaceTheme:
    """Phase D: theme catalog + per-workspace tone override."""

    def test_list_themes_returns_the_catalog(self, admin_client) -> None:
        r = admin_client.get("/v1/workspaces/themes")
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()}
        assert ids == {"default", "fantasia", "dark"}

    def test_create_workspace_honors_explicit_theme_id(self, admin_client) -> None:
        r = admin_client.post(
            "/v1/workspaces",
            json={"persona_template_id": "pm_fleet", "name": "PM Fleet", "theme_id": "fantasia"},
        )
        assert r.status_code == 201
        assert r.json()["theme_id"] == "fantasia"

    def test_create_workspace_rejects_unknown_theme_id(self, admin_client) -> None:
        r = admin_client.post(
            "/v1/workspaces",
            json={"persona_template_id": "pm_fleet", "name": "PM Fleet", "theme_id": "nope"},
        )
        assert r.status_code == 422

    def test_create_workspace_honors_voice_tone_override(self, admin_client) -> None:
        r = admin_client.post(
            "/v1/workspaces",
            json={
                "persona_template_id": "pm_fleet",
                "name": "PM Fleet",
                "voice_tone_override": "playful and terse",
            },
        )
        assert r.status_code == 201
        assert r.json()["voice_tone_override"] == "playful and terse"


def _set_members(workspace_id: str, roles: dict[str, str]) -> None:
    """Test-only helper: overwrite one workspace's membership list directly,
    so role-gating logic can be exercised for both owners and non-owners
    without needing a second real login per role."""
    from models.workspace import WorkspaceMember

    workspace = stores.workspaces[workspace_id]
    stores.workspaces[workspace_id] = workspace.model_copy(
        update={"members": [WorkspaceMember(user_id=uid, role=role) for uid, role in roles.items()]}
    )


class TestWorkspaceMembers:
    """Phase G: sharing via owner/editor/viewer membership."""

    def _create(self, admin_client) -> str:
        r = admin_client.post(
            "/v1/workspaces", json={"persona_template_id": "pm_fleet", "name": "PM Fleet"}
        )
        assert r.status_code == 201
        return r.json()["id"]

    def test_owner_can_add_member(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        r = admin_client.post(
            f"/v1/workspaces/{ws_id}/members", json={"user_id": "user", "role": "editor"}
        )
        assert r.status_code == 200
        roles = {m["user_id"]: m["role"] for m in r.json()["members"]}
        assert roles == {"admin": "owner", "user": "editor"}

    def test_re_adding_existing_member_updates_role_not_duplicates(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        admin_client.post(
            f"/v1/workspaces/{ws_id}/members", json={"user_id": "user", "role": "viewer"}
        )
        r = admin_client.post(
            f"/v1/workspaces/{ws_id}/members", json={"user_id": "user", "role": "editor"}
        )
        assert r.status_code == 200
        members = r.json()["members"]
        assert len(members) == 2
        assert {m["user_id"]: m["role"] for m in members}["user"] == "editor"

    def test_non_owner_cannot_add_member(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        _set_members(ws_id, {"admin": "editor"})
        r = admin_client.post(
            f"/v1/workspaces/{ws_id}/members", json={"user_id": "user", "role": "viewer"}
        )
        assert r.status_code == 403

    def test_add_member_requires_workspaces_write_scope(self, admin_client, authed_client) -> None:
        """The zero-permission daily account is refused at the middleware,
        before ever reaching the per-workspace owner check."""
        ws_id = self._create(admin_client)
        r = authed_client.post(
            f"/v1/workspaces/{ws_id}/members", json={"user_id": "someone", "role": "viewer"}
        )
        assert r.status_code == 403

    def test_owner_can_remove_other_member(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        _set_members(ws_id, {"admin": "owner", "user": "editor"})
        r = admin_client.delete(f"/v1/workspaces/{ws_id}/members/user")
        assert r.status_code == 200
        assert {m["user_id"] for m in r.json()["members"]} == {"admin"}

    def test_non_owner_cannot_remove_other_member(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        _set_members(ws_id, {"admin": "editor", "user": "viewer"})
        r = admin_client.delete(f"/v1/workspaces/{ws_id}/members/user")
        assert r.status_code == 403

    def test_member_can_remove_self_even_without_owner_role(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        # "user" holds the sole owner role here, so admin (an editor) removing
        # themself doesn't orphan the workspace and must be allowed.
        _set_members(ws_id, {"admin": "editor", "user": "owner"})
        r = admin_client.delete(f"/v1/workspaces/{ws_id}/members/admin")
        assert r.status_code == 200
        assert {m["user_id"] for m in r.json()["members"]} == {"user"}

    def test_last_owner_cannot_remove_self(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        r = admin_client.delete(f"/v1/workspaces/{ws_id}/members/admin")
        assert r.status_code == 400

    def test_removing_one_of_two_owners_is_allowed(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        _set_members(ws_id, {"admin": "owner", "user": "owner"})
        r = admin_client.delete(f"/v1/workspaces/{ws_id}/members/user")
        assert r.status_code == 200
        assert {m["user_id"] for m in r.json()["members"]} == {"admin"}

    def test_remove_unknown_member_404s(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        r = admin_client.delete(f"/v1/workspaces/{ws_id}/members/nobody")
        assert r.status_code == 404

    def test_add_member_to_unknown_workspace_404s(self, admin_client) -> None:
        r = admin_client.post(
            "/v1/workspaces/does-not-exist/members", json={"user_id": "user", "role": "viewer"}
        )
        assert r.status_code == 404
