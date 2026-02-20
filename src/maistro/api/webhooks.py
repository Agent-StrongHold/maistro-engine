"""Webhook receivers for GitHub and CI events."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from maistro.api.schemas import CIWebhookIgnored, WebhookAccepted, WebhookIgnored
from maistro.config.settings import Settings, get_settings
from maistro.constants import WEBHOOK_BODY_PREVIEW_LEN
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


def _sanitize(text: str) -> str:
    """Detect injection and wrap external content for safe LLM consumption."""
    violations = detect_injection(text)
    if violations:
        logger.warning("injection_detected_in_webhook", violations=violations)
    return wrap_external_content(text, ContentSource.WEBHOOK)


def _check_body_size(request: Request, settings: Settings) -> None:
    """Raise 413 if Content-Length exceeds the configured limit."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_webhook_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Request body too large (max {settings.max_webhook_body_bytes} bytes)",
        )


@router.post("/github")
async def github_webhook(
    request: Request,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
) -> WebhookAccepted | WebhookIgnored:
    _check_body_size(request, settings)
    body = await request.body()

    # Verify GitHub signature when secret is configured
    if settings.github_webhook_secret:
        sig = x_hub_signature_256 or ""
        if not _verify_github_signature(body, sig, settings.github_webhook_secret):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
    else:
        logger.warning("github_webhook_secret_not_configured")

    payload = json.loads(body)

    event = x_github_event or "unknown"
    action = payload.get("action", "")

    await logger.ainfo("github_webhook", github_event=event, action=action)

    # Handle PR events
    if event == "pull_request" and action in ("opened", "synchronize"):
        pr = payload.get("pull_request", {})
        title = _sanitize(pr.get("title", ""))
        number = pr.get("number", "")
        repo = payload.get("repository", {}).get("full_name", "")

        task = TaskCreate(
            description=f"Review PR #{number}: {title} in {repo}",
            workspace=f"/repos/{repo}",
        )
        result = await queue.submit(task)
        return WebhookAccepted(task_id=result.task_id, action="pr_review_queued")

    # Handle issue events
    if event == "issues" and action == "opened":
        issue = payload.get("issue", {})
        title = _sanitize(issue.get("title", ""))
        number = issue.get("number", "")
        body_text = _sanitize(issue.get("body", "")[:WEBHOOK_BODY_PREVIEW_LEN])
        repo = payload.get("repository", {}).get("full_name", "")

        task = TaskCreate(
            description=f"Investigate issue #{number}: {title}\n\n{body_text}",
            workspace=f"/repos/{repo}",
        )
        result = await queue.submit(task)
        return WebhookAccepted(task_id=result.task_id, action="issue_task_queued")

    return WebhookIgnored(status="ignored", event=event, action=action)


class CIWebhookPayload(BaseModel):
    """Typed request body for CI webhook."""

    status: str
    repository: str = ""
    branch: str = "main"
    log_url: str = ""
    commit_sha: str = ""


@router.post("/ci")
async def ci_webhook(
    request: Request,
    payload: CIWebhookPayload,
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_webhook_secret: str | None = Header(None),
) -> WebhookAccepted | CIWebhookIgnored:
    _check_body_size(request, settings)

    # Verify CI webhook shared secret when configured
    if settings.ci_webhook_secret:
        if not x_webhook_secret or x_webhook_secret != settings.ci_webhook_secret:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")
    else:
        logger.warning("ci_webhook_secret_not_configured")

    if payload.status == "failure":
        log_ref = _sanitize(payload.log_url) if payload.log_url else "no log"
        task = TaskCreate(
            description=f"Fix CI failure on {payload.branch} in {payload.repository}. Log: {log_ref}",
            workspace=f"/repos/{payload.repository}",
            branch=payload.branch,
        )
        result = await queue.submit(task)
        return WebhookAccepted(task_id=result.task_id, action="ci_fix_queued")

    return CIWebhookIgnored(status="ignored", ci_status=payload.status)
