import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data


def test_health_ready() -> None:
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert "checks" in body


def test_list_missions() -> None:
    r = client.get("/v1/tasks")
    assert r.status_code == 200
    missions = r.json()
    assert isinstance(missions, list)
    # Seed data from stores OR engine tasks — either way >= 1 item after engine startup,
    # or engine has no tasks yet → falls back to in-memory seed data which has >= 1.
    # If engine queue is empty we fall through to stores which has m-1, m-2.
    assert len(missions) >= 1
    assert missions[0]["id"]


def test_install_plan_parity() -> None:
    r = client.post(
        "/v1/install/plan",
        json={
            "schema_version": "1",
            "features": ["core_lib"],
            "stack_bringup": "none",
        },
    )
    if r.status_code == 503:
        pytest.skip("maistro-bootstrap not adjacent (non-monorepo layout)")
    assert r.status_code == 200
    body = r.json()
    assert body.get("kind") == "maistro_install_plan"
    assert "shell_commands" in body
    assert "compose_profile_hints" in body


def test_install_session_get_and_post() -> None:
    r = client.get("/v1/install/session")
    if r.status_code == 503:
        pytest.skip("maistro-bootstrap not adjacent (non-monorepo layout)")
    assert r.status_code == 200
    tmpl = r.json()
    assert tmpl.get("kind") == "maistro_install_session_template"
    assert "defaults" in tmpl

    r2 = client.post("/v1/install/session", json={"features": ["server"], "llm_gateway": "direct"})
    assert r2.status_code == 200
    sess = r2.json()
    assert sess.get("kind") == "maistro_install_session"
    assert sess["answers"]["llm_gateway"] == "direct"
    assert "server" in sess["answers"]["features"]


def test_chat_complete_stub() -> None:
    """When engine is not configured, stub response is returned."""
    r = client.post(
        "/v1/chat/complete",
        json={"messages": [{"role": "user", "content": "ping"}], "model": "gpt-4"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "choices" in body
    assert body["choices"][0]["message"]["role"] == "assistant"


def test_chat_complete_with_mock_engine() -> None:
    """When engine is configured, route() is called with the correct messages."""
    expected_messages = [{"role": "user", "content": "Hello from mock"}]
    mock_response = {
        "choices": [{"message": {"role": "assistant", "content": "mock response"}}]
    }

    mock_engine = MagicMock()
    mock_engine.is_configured = True
    mock_engine.route_request = AsyncMock(return_value=mock_response)

    with patch("services.engine._singleton", mock_engine):
        r = client.post(
            "/v1/chat/complete",
            json={"messages": expected_messages},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["choices"][0]["message"]["content"] == "mock response"
    mock_engine.route_request.assert_called_once_with(expected_messages)


def test_mission_create_dispatches_task() -> None:
    """POST /v1/tasks with engine queue available dispatches to submit_task()."""
    from datetime import UTC, datetime

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
    mock_engine._queue = MagicMock()  # queue exists → engine path taken
    mock_engine.submit_task = AsyncMock(return_value=fake_rec)

    with patch("services.engine._singleton", mock_engine):
        r = client.post(
            "/v1/tasks",
            json={"name": "Write hello world", "description": "Write hello world"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == task_id
    assert body["status"] == "pending"
    mock_engine.submit_task.assert_called_once_with("Write hello world", "Write hello world")


def test_mission_status_maps_correctly() -> None:
    """TaskStatus values map to correct Mission.status strings."""
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
    """WebSocket /v1/ws/tasks/{id} yields events until 'completed'."""
    from datetime import UTC, datetime

    async def _fake_iter(task_id: str):  # type: ignore[no-untyped-def]
        yield {"id": task_id, "status": "running", "progress": 0.5, "current_step": "planning"}
        yield {"id": task_id, "status": "completed", "progress": 1.0, "current_step": "done"}

    mock_engine = MagicMock()
    mock_engine.iter_task_events = _fake_iter

    with patch("services.engine._singleton", mock_engine):
        with client.websocket_connect("/v1/ws/tasks/test-task-1") as ws:
            msg1 = ws.receive_json()
            assert msg1["status"] == "running"
            msg2 = ws.receive_json()
            assert msg2["status"] == "completed"
