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


@pytest.fixture(autouse=True)
def _clear_persona_feedback():
    for key in list(stores.persona_feedback.keys()):
        stores.persona_feedback.pop(key, None)
    yield
    for key in list(stores.persona_feedback.keys()):
        stores.persona_feedback.pop(key, None)


def test_create_workspace_persists_and_returns_it(admin_client) -> None:
    # A persona id with no real template on disk -- this test is about basic
    # create/persist behavior, deliberately independent of whether any
    # specific persona (e.g. the real pm_fleet.yaml, Phase H) happens to be
    # seeded, so the checklist-defaults-empty-when-unresolvable path stays
    # exercised regardless.
    r = admin_client.post(
        "/v1/workspaces", json={"persona_template_id": "no_such_persona", "name": "PM Fleet"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["persona_template_id"] == "no_such_persona"
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


class TestListPersonaTemplates:
    """Persona picker slice: GET /v1/workspaces/persona-templates."""

    def test_returns_one_option_per_loaded_template(self, admin_client, monkeypatch) -> None:
        import routes.workspaces as workspaces_routes

        from maistro.personas.schema import BrandSpec, PersonaTemplate

        monkeypatch.setattr(
            workspaces_routes,
            "load_templates",
            lambda: {
                "pm_fleet": PersonaTemplate(
                    kind="workspace",
                    id="pm_fleet",
                    brand=BrandSpec(display_name="PM Fleet", tagline="Ship the program"),
                ),
                "content_creator": PersonaTemplate(
                    kind="workspace",
                    id="content_creator",
                    brand=BrandSpec(display_name="Content Studio", tagline="Plan your posts"),
                ),
            },
        )
        r = admin_client.get("/v1/workspaces/persona-templates")
        assert r.status_code == 200
        body = r.json()
        assert {opt["id"] for opt in body} == {"pm_fleet", "content_creator"}
        pm_fleet = next(opt for opt in body if opt["id"] == "pm_fleet")
        assert pm_fleet["display_name"] == "PM Fleet"
        assert pm_fleet["tagline"] == "Ship the program"

    def test_falls_back_to_id_when_brand_display_name_is_empty(
        self, admin_client, monkeypatch
    ) -> None:
        import routes.workspaces as workspaces_routes

        from maistro.personas.schema import PersonaTemplate

        monkeypatch.setattr(
            workspaces_routes,
            "load_templates",
            lambda: {"nameless": PersonaTemplate(kind="workspace", id="nameless")},
        )
        r = admin_client.get("/v1/workspaces/persona-templates")
        assert r.status_code == 200
        assert r.json() == [{"id": "nameless", "display_name": "nameless", "tagline": ""}]

    def test_empty_when_no_templates_resolve(self, admin_client, monkeypatch) -> None:
        import routes.workspaces as workspaces_routes

        monkeypatch.setattr(workspaces_routes, "load_templates", lambda: {})
        r = admin_client.get("/v1/workspaces/persona-templates")
        assert r.status_code == 200
        assert r.json() == []


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


class TestRealPmFleetTemplate:
    """Phase H: the real personas/templates/pm_fleet.yaml, resolved end-to-end
    through the actual (unmocked) load_templates(), not the minimal fixture
    other tests in this file monkeypatch in."""

    def test_checklist_endpoint_no_longer_404s_for_pm_fleet(self, admin_client) -> None:
        r = admin_client.get("/v1/workspaces/persona-templates/pm_fleet/checklist")
        assert r.status_code == 200
        body = r.json()
        assert body["persona_template_id"] == "pm_fleet"
        assert len(body["items"]) > 0
        assert body["default_accepted"] == [i["id"] for i in body["items"]]

    def test_create_workspace_defaults_checklist_from_the_real_persona(self, admin_client) -> None:
        r = admin_client.post(
            "/v1/workspaces", json={"persona_template_id": "pm_fleet", "name": "PM Fleet"}
        )
        assert r.status_code == 201
        checklist = r.json()["checklist"]
        assert "intake.skill.create_initiative" in checklist
        assert "delivery.skill.poll_jira" in checklist

    def test_persona_template_list_includes_both_real_personas(self, admin_client) -> None:
        r = admin_client.get("/v1/workspaces/persona-templates")
        assert r.status_code == 200
        ids = {opt["id"] for opt in r.json()}
        assert {"pm_fleet", "content_creator"} <= ids


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


class TestPersonaFeedback:
    """Phase I: thumbs +/- + comment feedback, aggregated per-persona."""

    def _create(self, admin_client, persona_template_id: str = "pm_fleet") -> str:
        r = admin_client.post(
            "/v1/workspaces",
            json={"persona_template_id": persona_template_id, "name": "PM Fleet"},
        )
        assert r.status_code == 201
        return r.json()["id"]

    def test_submit_feedback_persists_against_the_workspaces_persona(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        r = admin_client.post(
            f"/v1/workspaces/{ws_id}/feedback",
            json={"thumb": "up", "comment": "Nailed the summary"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["persona_template_id"] == "pm_fleet"
        assert body["workspace_id"] == ws_id
        assert body["thumb"] == "up"
        assert body["comment"] == "Nailed the summary"
        assert body["user_id"] == "admin"

    def test_feedback_on_unknown_workspace_404s(self, admin_client) -> None:
        r = admin_client.post("/v1/workspaces/does-not-exist/feedback", json={"thumb": "down"})
        assert r.status_code == 404

    def test_feedback_requires_workspace_membership(self, admin_client, authed_client) -> None:
        ws_id = self._create(admin_client)
        r = authed_client.post(f"/v1/workspaces/{ws_id}/feedback", json={"thumb": "up"})
        assert r.status_code == 404

    def test_two_workspaces_of_the_same_persona_aggregate_into_one_summary(
        self, admin_client
    ) -> None:
        ws_a = self._create(admin_client)
        ws_b = self._create(admin_client)
        admin_client.post(f"/v1/workspaces/{ws_a}/feedback", json={"thumb": "up"})
        admin_client.post(f"/v1/workspaces/{ws_b}/feedback", json={"thumb": "up"})
        admin_client.post(f"/v1/workspaces/{ws_b}/feedback", json={"thumb": "down"})

        r = admin_client.get("/v1/workspaces/persona-templates/pm_fleet/feedback")
        assert r.status_code == 200
        body = r.json()
        assert body["persona_template_id"] == "pm_fleet"
        assert body["thumbs_up"] == 2
        assert body["thumbs_down"] == 1
        assert {row["workspace_id"] for row in body["recent"]} == {ws_a, ws_b}

    def test_feedback_for_a_persona_with_no_feedback_yet_is_zeroed(self, admin_client) -> None:
        r = admin_client.get("/v1/workspaces/persona-templates/never_used/feedback")
        assert r.status_code == 200
        body = r.json()
        assert body == {
            "persona_template_id": "never_used",
            "thumbs_up": 0,
            "thumbs_down": 0,
            "recent": [],
        }

    def test_invalid_thumb_value_422s(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        r = admin_client.post(f"/v1/workspaces/{ws_id}/feedback", json={"thumb": "sideways"})
        assert r.status_code == 422


class TestArchiveWorkspace:
    """Delete/archive slice: PATCH .../active toggles archive state."""

    def _create(self, admin_client) -> str:
        r = admin_client.post(
            "/v1/workspaces", json={"persona_template_id": "pm_fleet", "name": "PM Fleet"}
        )
        assert r.status_code == 201
        return r.json()["id"]

    def test_owner_can_archive_and_unarchive(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        r = admin_client.patch(f"/v1/workspaces/{ws_id}", json={"active": False})
        assert r.status_code == 200
        assert r.json()["active"] is False

        r = admin_client.patch(f"/v1/workspaces/{ws_id}", json={"active": True})
        assert r.status_code == 200
        assert r.json()["active"] is True

    def test_omitted_active_leaves_it_unchanged(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        r = admin_client.patch(f"/v1/workspaces/{ws_id}", json={})
        assert r.status_code == 200
        assert r.json()["active"] is True

    def test_non_owner_cannot_archive(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        _set_members(ws_id, {"admin": "editor"})
        r = admin_client.patch(f"/v1/workspaces/{ws_id}", json={"active": False})
        assert r.status_code == 403

    def test_archive_unknown_workspace_404s(self, admin_client) -> None:
        r = admin_client.patch("/v1/workspaces/does-not-exist", json={"active": False})
        assert r.status_code == 404

    def test_archive_requires_workspaces_write_scope(self, admin_client, authed_client) -> None:
        ws_id = self._create(admin_client)
        r = authed_client.patch(f"/v1/workspaces/{ws_id}", json={"active": False})
        assert r.status_code == 403


class TestDeleteWorkspace:
    """Delete/archive slice: DELETE permanently removes a workspace."""

    def _create(self, admin_client) -> str:
        r = admin_client.post(
            "/v1/workspaces", json={"persona_template_id": "pm_fleet", "name": "PM Fleet"}
        )
        assert r.status_code == 201
        return r.json()["id"]

    def test_owner_can_delete_workspace(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        r = admin_client.delete(f"/v1/workspaces/{ws_id}")
        assert r.status_code == 204
        assert admin_client.get(f"/v1/workspaces/{ws_id}").status_code == 404

    def test_non_owner_cannot_delete(self, admin_client) -> None:
        ws_id = self._create(admin_client)
        _set_members(ws_id, {"admin": "editor"})
        r = admin_client.delete(f"/v1/workspaces/{ws_id}")
        assert r.status_code == 403
        assert admin_client.get(f"/v1/workspaces/{ws_id}").status_code == 200

    def test_delete_unknown_workspace_404s(self, admin_client) -> None:
        r = admin_client.delete("/v1/workspaces/does-not-exist")
        assert r.status_code == 404

    def test_delete_requires_workspaces_write_scope(self, admin_client, authed_client) -> None:
        ws_id = self._create(admin_client)
        r = authed_client.delete(f"/v1/workspaces/{ws_id}")
        assert r.status_code == 403
        assert admin_client.get(f"/v1/workspaces/{ws_id}").status_code == 200
