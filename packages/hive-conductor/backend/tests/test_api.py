from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def _login(username: str = "testuser", password: str = "testpass") -> TestClient:
    c = TestClient(app)
    r = c.post("/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    return c


@pytest.mark.ac("SPEC-176/AC-1")
def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data


@pytest.mark.ac("SPEC-176/AC-1")
def test_health_ready() -> None:
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert "checks" in body


def test_unauthenticated_api_returns_401() -> None:
    r = client.get("/v1/tasks")
    assert r.status_code == 401


def test_login_success() -> None:
    c = _login()
    r = c.get("/v1/tasks")
    assert r.status_code == 200


def test_login_failure() -> None:
    c = TestClient(app)
    r = c.post("/v1/auth/login", json={"username": "testuser", "password": "wrong"})
    assert r.status_code == 401


def test_register_success() -> None:
    c = TestClient(app)
    r = c.post(
        "/v1/auth/register",
        json={
            "username": "newpmuser",
            "password": "securepass1",
            "confirm_password": "securepass1",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["user"]["username"] == "newpmuser"
    assert data["user"]["role"] == "user"
    who = c.get("/v1/auth/whoami")
    assert who.json()["authenticated"] is True


def test_register_duplicate_username() -> None:
    c = TestClient(app)
    r = c.post(
        "/v1/auth/register",
        json={
            "username": "testuser",
            "password": "otherpass1",
            "confirm_password": "otherpass1",
        },
    )
    assert r.status_code == 409


def test_register_password_mismatch() -> None:
    c = TestClient(app)
    r = c.post(
        "/v1/auth/register",
        json={
            "username": "mismatchuser",
            "password": "securepass1",
            "confirm_password": "different1",
        },
    )
    assert r.status_code == 422


def test_whoami_authenticated() -> None:
    c = _login()
    r = c.get("/v1/auth/whoami")
    assert r.status_code == 200
    data = r.json()
    assert data["authenticated"] is True
    assert data["user"]["username"] == "testuser"
    assert data["user"]["role"] == "user"


def test_whoami_unauthenticated() -> None:
    r = client.get("/v1/auth/whoami")
    assert r.status_code == 200
    assert r.json()["authenticated"] is False


def test_admin_blocked_from_chat() -> None:
    c = _login("testadmin", "adminpass")
    r = c.post(
        "/v1/chat/complete",
        json={"messages": [{"role": "user", "content": "ping"}]},
    )
    assert r.status_code == 403
    assert "daily user" in r.json()["detail"].lower() or "admin" in r.json()["detail"].lower()


def test_user_can_chat() -> None:
    c = _login()
    r = c.post(
        "/v1/chat/complete",
        json={"messages": [{"role": "user", "content": "ping"}]},
    )
    assert r.status_code == 200


def test_list_missions() -> None:
    c = _login()
    r = c.get("/v1/tasks")
    assert r.status_code == 200
    missions = r.json()
    assert isinstance(missions, list)
    assert len(missions) >= 1
    assert missions[0]["id"]


def test_install_plan_endpoint_retired_returns_405() -> None:
    """POST /v1/install/plan was retired in favor of POST /v1/install/session
    (the canonical 'kind=maistro_install_session' shape). Regression-pin
    so nothing reintroduces it without an explicit decision."""
    c = _login()
    r = c.post(
        "/v1/install/plan",
        json={"schema_version": "1", "features": ["core_lib"]},
    )
    assert r.status_code == 405


def test_install_session_get_and_post() -> None:
    c = _login()
    r = c.get("/v1/install/session")
    if r.status_code == 503:
        pytest.skip("maistro-bootstrap not adjacent (non-monorepo layout)")
    assert r.status_code == 200
    tmpl = r.json()
    assert tmpl.get("kind") == "maistro_install_session_template"
    assert "defaults" in tmpl

    r2 = c.post("/v1/install/session", json={"features": ["server"], "llm_gateway": "direct"})
    assert r2.status_code == 200
    sess = r2.json()
    assert sess.get("kind") == "maistro_install_session"
    assert sess["answers"]["llm_gateway"] == "direct"
    assert "server" in sess["answers"]["features"]


def test_chat_complete_stub() -> None:
    c = _login()
    r = c.post(
        "/v1/chat/complete",
        json={"messages": [{"role": "user", "content": "ping"}], "model": "gpt-4"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "choices" in body
    assert body["choices"][0]["message"]["role"] == "assistant"


def test_chat_complete_with_mock_engine() -> None:
    c = _login()
    expected_messages = [{"role": "user", "content": "Hello from mock"}]
    mock_response = {"choices": [{"message": {"role": "assistant", "content": "mock response"}}]}

    mock_engine = MagicMock()
    mock_engine.is_configured = True
    mock_engine.route_request = AsyncMock(return_value=mock_response)

    with patch("services.engine._singleton", mock_engine):
        r = c.post(
            "/v1/chat/complete",
            json={"messages": expected_messages},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["choices"][0]["message"]["content"] == "mock response"
    mock_engine.route_request.assert_called_once_with(expected_messages)


def test_mission_create_dispatches_task() -> None:
    from datetime import UTC, datetime

    c = _login()
    task_id = "abc123def456"
    fake_rec = MagicMock()
    fake_rec.id = task_id
    fake_rec.name = "Write hello world"
    fake_rec.description = "Write hello world"
    fake_rec.mission_status = "pending"
    fake_rec.progress = 0.0
    fake_rec.current_step = ""
    fake_rec.created_at = datetime.now(UTC)
    fake_rec.started_at = None
    fake_rec.completed_at = None

    mock_engine = MagicMock()
    mock_engine.is_configured = False
    mock_engine._queue = MagicMock()
    mock_engine.submit_task = AsyncMock(return_value=fake_rec)

    with patch("services.engine._singleton", mock_engine):
        r = c.post(
            "/v1/tasks",
            json={"name": "Write hello world", "description": "Write hello world"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == task_id
    assert body["status"] == "pending"
    mock_engine.submit_task.assert_called_once_with("Write hello world", "Write hello world")


def test_mission_status_maps_correctly() -> None:
    from services.engine import _STATUS_MAP

    assert _STATUS_MAP["queued"] == "pending"
    assert _STATUS_MAP["planning"] == "running"
    assert _STATUS_MAP["coding"] == "running"
    assert _STATUS_MAP["reviewing"] == "running"
    assert _STATUS_MAP["testing"] == "running"
    assert _STATUS_MAP["completed"] == "completed"
    assert _STATUS_MAP["failed"] == "failed"
    assert _STATUS_MAP["cancelled"] == "failed"


def test_websocket_streams_task_events() -> None:

    c = _login()

    async def _fake_iter(task_id: str):
        yield {"id": task_id, "status": "running", "progress": 0.5, "current_step": "planning"}
        yield {"id": task_id, "status": "completed", "progress": 1.0, "current_step": "done"}

    mock_engine = MagicMock()
    mock_engine.iter_task_events = _fake_iter

    with (
        patch("services.engine._singleton", mock_engine),
        c.websocket_connect("/v1/ws/tasks/test-task-1") as ws,
    ):
        msg1 = ws.receive_json()
        assert msg1["status"] == "running"
        msg2 = ws.receive_json()
        assert msg2["status"] == "completed"


def test_elevate_flow() -> None:
    c = _login()
    r = c.post(
        "/v1/auth/elevate", json={"password": "testpass", "permissions": [], "task_id": "t-1"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["task_id"] == "t-1"
    assert "elevated_permissions" in data


def test_elevate_wrong_password() -> None:
    c = _login()
    r = c.post("/v1/auth/elevate", json={"password": "wrong", "permissions": [], "task_id": "t-1"})
    assert r.status_code == 401


def test_logout() -> None:
    c = _login()
    r = c.post("/v1/auth/logout")
    assert r.status_code == 200
    r2 = c.get("/v1/tasks")
    assert r2.status_code == 401


def test_elevation_only_activates_granted_permissions() -> None:
    from datetime import UTC, datetime

    import stores

    from maistro.security.passwords import hash_password

    now_ts = datetime.now(UTC)
    pw = hash_password("frankpass")
    stores.users["frank"] = stores.users._model_class(
        id="frank",
        username="frank",
        password_hash=pw,
        role="user",
        is_active=True,
        permissions=["config.write"],
        created_at=now_ts,
    )
    try:
        c = _login("frank", "frankpass")

        r = c.put("/v1/settings", json={"temperature": 0.5})
        assert r.status_code == 403, "should be blocked without elevation"

        c.post(
            "/v1/auth/elevate",
            json={
                "password": "frankpass",
                "permissions": ["config.write"],
                "task_id": "frank-task-1",
            },
        )
        r2 = c.put("/v1/settings", json={"temperature": 0.5})
        assert r2.status_code == 200, "should work after elevation for granted perm"

        r3 = c.delete("/v1/settings")
        assert r3.status_code == 403, (
            "should still be blocked for ungranted perm even with elevation"
        )
    finally:
        stores.users.pop("frank", None)


def test_elevate_rejects_unassigned_permissions() -> None:
    from datetime import UTC, datetime

    import stores

    from maistro.security.passwords import hash_password

    now_ts = datetime.now(UTC)
    pw = hash_password("frankpass")
    stores.users["frank"] = stores.users._model_class(
        id="frank",
        username="frank",
        password_hash=pw,
        role="user",
        is_active=True,
        permissions=["config.write"],
        created_at=now_ts,
    )
    try:
        c = _login("frank", "frankpass")
        r = c.post(
            "/v1/auth/elevate",
            json={
                "password": "frankpass",
                "permissions": ["config.delete", "agents.delete"],
                "task_id": "t-bad",
            },
        )
        assert r.status_code == 403, "should reject when none of the requested perms are assigned"
    finally:
        stores.users.pop("frank", None)


def test_elevation_revoked_on_task_completion() -> None:
    from datetime import UTC, datetime

    import stores

    from maistro.security.passwords import hash_password

    now_ts = datetime.now(UTC)
    pw = hash_password("frankpass")
    stores.users["frank"] = stores.users._model_class(
        id="frank",
        username="frank",
        password_hash=pw,
        role="user",
        is_active=True,
        permissions=["config.write"],
        created_at=now_ts,
    )
    try:
        c = _login("frank", "frankpass")

        c.post(
            "/v1/auth/elevate",
            json={"password": "frankpass", "permissions": ["config.write"], "task_id": "m-1"},
        )
        r = c.put("/v1/settings", json={"temperature": 0.5})
        assert r.status_code == 200, "should work with elevated perm"

        c.patch("/v1/tasks/m-1/status", json={"status": "completed"})
        r2 = c.put("/v1/settings", json={"temperature": 0.5})
        assert r2.status_code == 403, "perm should die with the task"
    finally:
        stores.users.pop("frank", None)
