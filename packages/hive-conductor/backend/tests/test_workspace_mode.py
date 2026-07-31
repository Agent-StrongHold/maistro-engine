"""services/workspace_mode.py -- Persona/Workspace system, Phase H. See the
module docstring for the bounded scope of the call-site migration (which
gates were safely, mechanically re-pointable vs. which weren't)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import stores
from models.workspace import Workspace, WorkspaceMember
from services.workspace_mode import is_pm_fleet_workspace, is_workspace_request_authorized


@pytest.fixture(autouse=True)
def _clear_workspaces():
    for key in list(stores.workspaces.keys()):
        stores.workspaces.pop(key, None)
    yield
    for key in list(stores.workspaces.keys()):
        stores.workspaces.pop(key, None)


def _workspace(persona_template_id: str) -> Workspace:
    t = datetime.now(UTC)
    return Workspace(
        id="ws-1",
        persona_template_id=persona_template_id,
        name="test",
        members=[WorkspaceMember(user_id="admin", role="owner")],
        created_at=t,
        updated_at=t,
    )


def test_pm_fleet_workspace_is_true_regardless_of_env_var(monkeypatch) -> None:
    stores.workspaces["ws-1"] = _workspace("pm_fleet")
    monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: False)
    assert is_pm_fleet_workspace("ws-1") is True


def test_non_pm_fleet_workspace_is_false_regardless_of_env_var(monkeypatch) -> None:
    stores.workspaces["ws-1"] = _workspace("content_creator")
    monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: True)
    assert is_pm_fleet_workspace("ws-1") is False


def test_no_workspace_id_falls_back_to_legacy_env_var_flag(monkeypatch) -> None:
    monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: True)
    assert is_pm_fleet_workspace(None) is True
    monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: False)
    assert is_pm_fleet_workspace(None) is False


def test_unknown_workspace_id_falls_back_to_legacy_env_var_flag(monkeypatch) -> None:
    monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: True)
    assert is_pm_fleet_workspace("does-not-exist") is True
    monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: False)
    assert is_pm_fleet_workspace("does-not-exist") is False


class TestIsWorkspaceRequestAuthorized:
    """Request-time gate: membership-checked, and — unlike
    is_pm_fleet_workspace — two different persona-matching semantics
    depending on whether the gated surface is PM-Fleet-specific
    (require_pm_fleet_persona=True, the default) or already generalized to
    any persona (False)."""

    def test_pm_fleet_persona_required_true_for_pm_fleet_member(self, monkeypatch) -> None:
        stores.workspaces["ws-1"] = _workspace("pm_fleet")
        monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: False)
        assert is_workspace_request_authorized("admin", "ws-1") is True

    def test_pm_fleet_persona_required_false_for_other_persona_member(self, monkeypatch) -> None:
        stores.workspaces["ws-1"] = _workspace("content_creator")
        monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: True)
        assert is_workspace_request_authorized("admin", "ws-1") is False

    def test_persona_not_required_true_for_any_persona_member(self, monkeypatch) -> None:
        stores.workspaces["ws-1"] = _workspace("content_creator")
        monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: False)
        assert (
            is_workspace_request_authorized("admin", "ws-1", require_pm_fleet_persona=False) is True
        )

    def test_non_member_falls_back_to_legacy_flag_even_when_persona_matches(
        self, monkeypatch
    ) -> None:
        stores.workspaces["ws-1"] = _workspace("pm_fleet")
        monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: False)
        assert is_workspace_request_authorized("someone-else", "ws-1") is False
        monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: True)
        assert is_workspace_request_authorized("someone-else", "ws-1") is True

    def test_no_workspace_id_falls_back_to_legacy_flag(self, monkeypatch) -> None:
        monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: True)
        assert is_workspace_request_authorized("admin", None) is True
        monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: False)
        assert is_workspace_request_authorized("admin", None) is False

    def test_unknown_workspace_id_falls_back_to_legacy_flag(self, monkeypatch) -> None:
        monkeypatch.setattr("services.workspace_mode.is_pm_poc_mode", lambda: True)
        assert is_workspace_request_authorized("admin", "does-not-exist") is True
