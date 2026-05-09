"""Tests for webhook endpoints — signature verification and content wrapping."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from maistro.main import app

from maistro.config.settings import Settings, get_settings
from maistro.tasks.queue import get_task_queue


def _client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def app_with_webhook_secret():
    """Create app with webhook secrets configured."""
    secret = "test-webhook-secret-123"
    settings = Settings(
        require_auth=False,
        github_webhook_secret=secret,
        ci_webhook_secret="ci-token-abc",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield secret
    app.dependency_overrides.clear()


def _make_signature(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestGitHubWebhookSignature:
    """CRIT-03: Webhook signature must be verified when secret is configured."""

    def test_missing_signature_rejected(self, app_with_webhook_secret: str) -> None:
        client = _client()
        response = client.post(
            "/webhooks/github",
            json={"action": "opened"},
            headers={"X-GitHub-Event": "push"},
        )
        assert response.status_code == 401

    def test_invalid_signature_rejected(self, app_with_webhook_secret: str) -> None:
        client = _client()
        response = client.post(
            "/webhooks/github",
            json={"action": "opened"},
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
        assert response.status_code == 403

    def test_valid_signature_accepted(self, app_with_webhook_secret: str) -> None:
        client = _client()
        payload = json.dumps({"action": "opened"}).encode()
        sig = _make_signature(payload, app_with_webhook_secret)
        response = client.post(
            "/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
            },
        )
        assert response.status_code == 200


class TestCIWebhookAuth:
    """CRIT-03: CI webhook must require token when secret is configured."""

    def test_missing_token_rejected(self, app_with_webhook_secret: str) -> None:
        client = _client()
        response = client.post("/webhooks/ci", json={"status": "failure"})
        assert response.status_code == 401

    def test_wrong_token_rejected(self, app_with_webhook_secret: str) -> None:
        client = _client()
        response = client.post(
            "/webhooks/ci",
            json={"status": "failure"},
            headers={"X-CI-Token": "wrong-token"},
        )
        assert response.status_code == 401

    def test_valid_token_accepted(self, app_with_webhook_secret: str) -> None:
        client = _client()
        response = client.post(
            "/webhooks/ci",
            json={"status": "success"},
            headers={"X-CI-Token": "ci-token-abc"},
        )
        assert response.status_code == 200


class TestGitHubWebhookFunctionality:
    """Test webhook routing still works (no secrets = dev mode)."""

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


class TestCIWebhookFunctionality:
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
