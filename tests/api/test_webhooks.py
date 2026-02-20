"""Tests for webhook endpoints.

Evidence: GitHub and CI webhooks create tasks automatically.
The GitHub webhook had a structlog bug where event= conflicted
with structlog's reserved 'event' parameter — regression test included.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from maistro.main import app
from maistro.tasks.queue import get_task_queue


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

        # Verify the task was actually created in the queue with correct content
        queue = get_task_queue()
        task = queue.get(data["task_id"])
        assert task is not None, "Task must actually exist in the queue"
        assert "Add auth" in task.description
        assert "#42" in task.description
        assert task.workspace == "/repos/org/repo"

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

        # Verify task content
        queue = get_task_queue()
        task = queue.get(data["task_id"])
        assert task is not None
        assert "Bug in login" in task.description
        assert "#7" in task.description
        assert "Steps to reproduce" in task.description

    def test_ignored_event(self) -> None:
        client = _client()
        response = client.post(
            "/webhooks/github",
            json={"action": "closed"},
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


class TestGitHubWebhookSignature:
    """Evidence: Webhook signature verification must be enforced when secret is set."""

    def test_rejects_missing_signature_when_secret_configured(self, monkeypatch: object) -> None:
        import os

        old = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
        os.environ["GITHUB_WEBHOOK_SECRET"] = "test-secret"
        try:
            client = _client()
            response = client.post(
                "/webhooks/github",
                json={"action": "opened"},
                headers={"X-GitHub-Event": "push"},
            )
            assert response.status_code == 401
        finally:
            if old:
                os.environ["GITHUB_WEBHOOK_SECRET"] = old
            else:
                os.environ.pop("GITHUB_WEBHOOK_SECRET", None)

    def test_rejects_invalid_signature_when_secret_configured(self) -> None:
        import os

        old = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
        os.environ["GITHUB_WEBHOOK_SECRET"] = "test-secret"
        try:
            client = _client()
            response = client.post(
                "/webhooks/github",
                json={"action": "opened"},
                headers={
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": "sha256=invalid",
                },
            )
            assert response.status_code == 401
        finally:
            if old:
                os.environ["GITHUB_WEBHOOK_SECRET"] = old
            else:
                os.environ.pop("GITHUB_WEBHOOK_SECRET", None)


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

        # Verify task content
        queue = get_task_queue()
        task = queue.get(data["task_id"])
        assert task is not None
        assert "org/repo" in task.description
        assert "main" in task.description

    def test_success_ignored(self) -> None:
        client = _client()
        response = client.post(
            "/webhooks/ci",
            json={"status": "success", "repository": "org/repo"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
