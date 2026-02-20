"""Tests for webhook endpoints.

Evidence: GitHub and CI webhooks create tasks automatically.
The GitHub webhook had a structlog bug where event= conflicted
with structlog's reserved 'event' parameter — regression test included.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from maistro.main import app


def _client() -> TestClient:
    return TestClient(app)


class TestGitHubWebhook:
    def test_pr_opened_creates_task(self) -> None:
        """Evidence: PR opened events should auto-create a review task."""
        client = _client()
        response = client.post(
            "/webhooks/github",
            json={
                "action": "opened",
                "pull_request": {"title": "Add auth", "number": 42},
                "repository": {"full_name": "org/repo"},
            },
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "pr_review_queued"
        assert "task_id" in data

    def test_issue_opened_creates_task(self) -> None:
        client = _client()
        response = client.post(
            "/webhooks/github",
            json={
                "action": "opened",
                "issue": {"title": "Bug in login", "number": 7, "body": "Steps to reproduce..."},
                "repository": {"full_name": "org/repo"},
            },
            headers={"X-GitHub-Event": "issues"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "issue_task_queued"

    def test_ignored_event(self) -> None:
        client = _client()
        response = client.post(
            "/webhooks/github",
            json={"action": "closed"},
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


class TestCIWebhook:
    def test_failure_creates_fix_task(self) -> None:
        client = _client()
        response = client.post(
            "/webhooks/ci",
            json={
                "status": "failure",
                "repository": "org/repo",
                "branch": "main",
                "log_url": "https://ci.example.com/logs/123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "ci_fix_queued"
        assert "task_id" in data

    def test_success_ignored(self) -> None:
        client = _client()
        response = client.post(
            "/webhooks/ci",
            json={"status": "success", "repository": "org/repo"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
