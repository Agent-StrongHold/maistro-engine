"""Webhook receivers for GitHub and CI events."""

from __future__ import annotations

import hashlib
import hmac
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from maistro.config.settings import Settings, get_settings
from maistro.security.external_content import ContentSource, detect_injection, wrap_external_content
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
    settings: Annotated[Settings, Depends(get_settings)],
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
) -> dict[str, Any]:
    body = await request.body()

    # CRIT-03: Verify GitHub webhook signature
    if settings.github_webhook_secret:
        if not x_hub_signature_256:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Hub-Signature-256 header",
            )
        if not _verify_github_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook signature",
            )
    else:
        await logger.awarn(
            "github_webhook_no_secret",
            msg="GITHUB_WEBHOOK_SECRET not set — signature verification skipped",
        )

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

        # MAJ-09: Wrap external content and detect injection
        raw_description = f"Review PR #{number}: {title} in {repo}"
        wrapped = wrap_external_content(
            raw_description, ContentSource.WEBHOOK, sender=f"github/{repo}",
        )
        injections = detect_injection(title)
        if injections:
            await logger.awarn("injection_detected_in_pr", pr=number, patterns=injections)

        task = TaskCreate(
            description=wrapped,
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

        # MAJ-09: Wrap external content and detect injection
        raw_description = f"Investigate issue #{number}: {title}\n\n{body_text[:500]}"
        wrapped = wrap_external_content(
            raw_description, ContentSource.WEBHOOK, sender=f"github/{repo}",
        )
        injections = detect_injection(title) + detect_injection(body_text[:500])
        if injections:
            await logger.awarn("injection_detected_in_issue", issue=number, patterns=injections)

        task = TaskCreate(
            description=wrapped,
            workspace=f"/repos/{repo}",
        )
        result = await queue.submit(task)
        return {"task_id": result.task_id, "action": "issue_task_queued"}

    return {"status": "ignored", "event": event, "action": action}


@router.post("/ci")
async def ci_webhook(
    request: Request,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_ci_token: str | None = Header(None),
) -> dict[str, Any]:
    # CRIT-03: Require CI webhook authentication
    if settings.ci_webhook_secret:
        if not x_ci_token or not hmac.compare_digest(x_ci_token, settings.ci_webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing CI webhook token",
            )
    else:
        await logger.awarn(
            "ci_webhook_no_secret",
            msg="CI_WEBHOOK_SECRET not set — authentication skipped",
        )

    payload = await request.json()

    ci_status = payload.get("status", "")
    repo = payload.get("repository", "")
    branch = payload.get("branch", "main")
    log_url = payload.get("log_url", "")

    if ci_status == "failure":
        raw_description = f"Fix CI failure on {branch} in {repo}. Log: {log_url}"
        wrapped = wrap_external_content(raw_description, ContentSource.WEBHOOK, sender="ci")

        task = TaskCreate(
            description=wrapped,
            workspace=f"/repos/{repo}",
            branch=branch,
        )
        result = await queue.submit(task)
        return {"task_id": result.task_id, "action": "ci_fix_queued"}

    return {"status": "ignored", "ci_status": ci_status}
