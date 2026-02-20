"""Webhook receivers for GitHub and CI events."""

from __future__ import annotations

import hashlib
import hmac
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, Request

from maistro.tasks.models import TaskCreate
from maistro.tasks.queue import TaskQueue, get_task_queue

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
) -> dict[str, Any]:
    payload = await request.json()

    event = x_github_event or "unknown"
    action = payload.get("action", "")

    await logger.ainfo("github_webhook", github_event=event, action=action)

    # Handle PR events
    if event == "pull_request" and action in ("opened", "synchronize"):
        pr = payload.get("pull_request", {})
        title = pr.get("title", "")
        number = pr.get("number", "")
        repo = payload.get("repository", {}).get("full_name", "")

        task = TaskCreate(
            description=f"Review PR #{number}: {title} in {repo}",
            workspace=f"/repos/{repo}",
        )
        result = await queue.submit(task)
        return {"task_id": result.task_id, "action": "pr_review_queued"}

    # Handle issue events
    if event == "issues" and action == "opened":
        issue = payload.get("issue", {})
        title = issue.get("title", "")
        number = issue.get("number", "")
        body_text = issue.get("body", "")
        repo = payload.get("repository", {}).get("full_name", "")

        task = TaskCreate(
            description=f"Investigate issue #{number}: {title}\n\n{body_text[:500]}",
            workspace=f"/repos/{repo}",
        )
        result = await queue.submit(task)
        return {"task_id": result.task_id, "action": "issue_task_queued"}

    return {"status": "ignored", "event": event, "action": action}


@router.post("/ci")
async def ci_webhook(
    request: Request,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
) -> dict[str, Any]:
    payload = await request.json()

    status = payload.get("status", "")
    repo = payload.get("repository", "")
    branch = payload.get("branch", "main")
    log_url = payload.get("log_url", "")

    if status == "failure":
        task = TaskCreate(
            description=f"Fix CI failure on {branch} in {repo}. Log: {log_url}",
            workspace=f"/repos/{repo}",
            branch=branch,
        )
        result = await queue.submit(task)
        return {"task_id": result.task_id, "action": "ci_fix_queued"}

    return {"status": "ignored", "ci_status": status}
