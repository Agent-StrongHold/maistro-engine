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
    r = client.post(
        "/v1/chat/complete",
        json={"messages": [{"role": "user", "content": "ping"}], "model": "gpt-4"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "choices" in body
    assert body["choices"][0]["message"]["role"] == "assistant"
