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
