"""Credentials API — per-user encrypted storage."""

from __future__ import annotations

from fastapi.testclient import TestClient
from main import app


def _login(username: str = "testuser", password: str = "testpass") -> TestClient:
    c = TestClient(app)
    r = c.post("/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


def test_save_and_list_credentials() -> None:
    c = _login()
    save = c.put("/v1/credentials/jira", json={"secret": "atlassian-token-123"})
    assert save.status_code == 200, save.text

    listing = c.get("/v1/credentials")
    assert listing.status_code == 200
    rows = {row["id"]: row for row in listing.json()["credentials"]}
    assert rows["jira"]["configured"] is True
    assert "atlassian-token" not in str(listing.json())


def test_user_cannot_see_other_users_secrets() -> None:
    alice = TestClient(app)
    reg = alice.post(
        "/v1/auth/register",
        json={
            "username": "credalice",
            "password": "securepass1",
            "confirm_password": "securepass1",
        },
    )
    assert reg.status_code == 200, reg.text
    alice.put("/v1/credentials/jira", json={"secret": "alice-only-token"})

    bob = TestClient(app)
    bob.post(
        "/v1/auth/register",
        json={
            "username": "credbob",
            "password": "securepass1",
            "confirm_password": "securepass1",
        },
    )
    bob_list = bob.get("/v1/credentials")
    jira_row = next(r for r in bob_list.json()["credentials"] if r["id"] == "jira")
    assert jira_row["configured"] is False
