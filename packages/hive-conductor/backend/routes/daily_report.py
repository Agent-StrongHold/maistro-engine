"""Daily status report — Jira 24h + Airtable 24h + research summary + suggested actions.

Each section returns a small, well-typed payload with a `source` field so the
UI can render either real data or a "needs setup" CTA. When a PAT is missing,
the section returns ``status='no_pat'`` and a deep link the user can click to
land on the right Credentials row.

The endpoint is intentionally tolerant — any one section failing should not
break the page. Errors are logged and surfaced as ``status='error'``.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from services import user_credentials as cred_svc

router = APIRouter(tags=["daily-report"])
logger = logging.getLogger(__name__)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    uid = user.get("id")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(uid)


def _has_credential(user_id: str, provider_id: str) -> bool:
    store = cred_svc.get_credential_store()
    if store is None:
        return False
    try:
        return store.has_secret(user_id, provider_id)
    except Exception:
        return False


def _use_secret(user_id: str, provider_id: str) -> str | None:
    store = cred_svc.get_credential_store()
    if store is None:
        return None
    try:
        if not store.has_secret(user_id, provider_id):
            return None
        return store.use_secret(user_id, provider_id, lambda s: s)
    except Exception:
        return None


async def _poll_jira(user_id: str) -> dict[str, Any]:
    """Poll on-prem Jira Server Jira (jira.example.com) for updates in the last 24h.

    Uses the per-user PAT from the credential store. Falls back to Cloud Jira
    if only the cloud token is set.
    """
    pat = _use_secret(user_id, "atlassian_server_jira")
    base_url = "https://jira.example.com"
    flavor = "server"
    if not pat:
        # Try Cloud token as fallback.
        pat = _use_secret(user_id, "jira") or _use_secret(user_id, "atlassian_rovo_mcp")
        cloud_site = os.getenv("ATLASSIAN_SITE_URL", "").strip().rstrip("/")
        if pat and cloud_site:
            base_url = cloud_site
            flavor = "cloud"
        else:
            return {
                "status": "no_pat",
                "detail": "Add your Jira PAT to see updates",
                "credential_id": "atlassian_server_jira",
                "help_url": (
                    "https://jira.example.com/secure/ViewProfile.jspa"
                    "?selectedTab=com.atlassian.pats.pats-plugin:jira-user-personal-access-tokens"
                ),
                "issues": [],
            }

    jql = 'updated >= -24h AND assignee = currentUser() ORDER BY updated DESC'
    api_path = "/rest/api/2/search" if flavor == "server" else "/rest/api/3/search"
    headers = {"Authorization": f"Bearer {pat}"} if flavor == "server" else {}
    auth = None
    if flavor == "cloud":
        email = os.getenv("ATLASSIAN_EMAIL", "").strip()
        auth = (email or pat, pat)

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{base_url}{api_path}",
                params={"jql": jql, "maxResults": 20, "fields": "summary,status,updated"},
                headers=headers,
                auth=auth,
            )
        if r.status_code == 401:
            return {
                "status": "auth_failed",
                "detail": "Jira returned 401 — your PAT may have expired (2FA?)",
                "credential_id": "atlassian_server_jira" if flavor == "server" else "jira",
                "help_url": (
                    "https://jira.example.com/secure/ViewProfile.jspa"
                    "?selectedTab=com.atlassian.pats.pats-plugin:jira-user-personal-access-tokens"
                ),
                "issues": [],
            }
        if r.status_code != 200:
            return {
                "status": "error",
                "detail": f"Jira returned HTTP {r.status_code}",
                "issues": [],
            }
        data = r.json()
        issues = []
        for it in data.get("issues", [])[:20]:
            fields = it.get("fields", {})
            issues.append(
                {
                    "key": it.get("key", ""),
                    "summary": fields.get("summary", "")[:160],
                    "status": (fields.get("status") or {}).get("name", ""),
                    "updated": fields.get("updated", ""),
                    "url": f"{base_url}/browse/{it.get('key', '')}",
                }
            )
        return {"status": "ok", "issues": issues, "source": f"jira_{flavor}", "count": len(issues)}
    except httpx.HTTPError as exc:
        logger.warning("daily_report jira fetch failed: %s", exc)
        return {"status": "error", "detail": "Jira unreachable", "issues": []}


async def _poll_airtable(user_id: str) -> dict[str, Any]:
    """Poll Airtable for record changes in the last 24h.

    Requires the user's PAT and a configured base id + table name (env or, later,
    a per-user setting). For v0, returns 'needs_config' if base id isn't set.
    """
    pat = _use_secret(user_id, "airtable")
    if not pat:
        return {
            "status": "no_pat",
            "detail": "Add your Airtable PAT to see updates",
            "credential_id": "airtable",
            "help_url": "https://airtable.com/create/tokens/new",
            "records": [],
        }

    base_id = os.getenv("AIRTABLE_BASE_ID", "").strip()
    table_name = os.getenv("AIRTABLE_TABLE", "").strip()
    if not base_id or not table_name:
        return {
            "status": "needs_config",
            "detail": "Set AIRTABLE_BASE_ID and AIRTABLE_TABLE to enable polling",
            "records": [],
        }

    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"https://api.airtable.com/v0/{base_id}/{table_name}",
                headers={"Authorization": f"Bearer {pat}"},
                params={
                    "pageSize": 20,
                    "filterByFormula": f"IS_AFTER(LAST_MODIFIED_TIME(), '{cutoff}')",
                    "sort[0][field]": "Last modified time",
                    "sort[0][direction]": "desc",
                },
            )
        if r.status_code == 401:
            return {
                "status": "auth_failed",
                "detail": "Airtable returned 401 — token may have expired",
                "credential_id": "airtable",
                "help_url": "https://airtable.com/create/tokens/new",
                "records": [],
            }
        if r.status_code != 200:
            return {
                "status": "error",
                "detail": f"Airtable returned HTTP {r.status_code}",
                "records": [],
            }
        data = r.json()
        records = [
            {"id": rec.get("id", ""), "fields": rec.get("fields", {})}
            for rec in data.get("records", [])[:20]
        ]
        return {"status": "ok", "records": records, "count": len(records)}
    except httpx.HTTPError as exc:
        logger.warning("daily_report airtable fetch failed: %s", exc)
        return {"status": "error", "detail": "Airtable unreachable", "records": []}


def _research_summary(user_id: str) -> dict[str, Any]:
    """Pull recent research outcomes from the maistro outcome store.

    For v0, the outcome store may be empty (no DAG runs yet). Return a
    structured 'no_data' response so the UI can show a CTA to run a pulse.
    """
    try:
        # The outcome store is wired in maistro container DI; for v0 we read
        # via the global container singleton if present.
        from maistro.container import get_container  # type: ignore

        container = get_container()
        outcome_store = getattr(container, "outcome_store", None)
        if outcome_store is None:
            return {"status": "no_data", "detail": "Run a fleet pulse to generate research", "items": []}
        # get_experience_context returns a string; for v0 we surface the raw
        # recent outcomes if the store exposes them.
        outcomes = getattr(outcome_store, "_outcomes", [])
        recent = []
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        for o in list(outcomes)[-20:]:
            ts = getattr(o, "recorded_at", None)
            if ts is None:
                continue
            try:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
            except Exception:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if ts < cutoff:
                continue
            recent.append(
                {
                    "task_type": getattr(o, "task_type", ""),
                    "tool_name": getattr(o, "tool_name", ""),
                    "success": bool(getattr(o, "success", False)),
                    "recorded_at": ts.isoformat(),
                    "summary": str(getattr(o, "summary", ""))[:240],
                }
            )
        if not recent:
            return {"status": "no_data", "detail": "No fleet activity in the last 24h", "items": []}
        return {"status": "ok", "items": recent, "count": len(recent)}
    except Exception as exc:
        logger.debug("research_summary lookup failed: %s", exc)
        return {"status": "no_data", "detail": "Research index unavailable", "items": []}


def _suggested_actions(
    user_id: str,
    jira: dict[str, Any],
    airtable: dict[str, Any],
    research: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if jira.get("status") == "no_pat":
        actions.append(
            {
                "title": "Connect Jira to see real updates",
                "reason": "Daily report can't poll Jira until you add your PAT.",
                "link_label": "Open Credentials",
                "link_href": "/pm/credentials",
            }
        )
    elif jira.get("status") == "auth_failed":
        actions.append(
            {
                "title": "Refresh your Jira PAT",
                "reason": "Jira returned 401 — token likely expired after 2FA.",
                "link_label": "Regenerate token",
                "link_href": jira.get("help_url", "/pm/credentials"),
            }
        )
    elif jira.get("status") == "ok" and jira.get("count", 0) == 0:
        actions.append(
            {
                "title": "No Jira updates in 24h",
                "reason": "Either your queue is quiet or the JQL needs tuning.",
                "link_label": "Open Credentials",
                "link_href": "/pm/credentials",
            }
        )

    if airtable.get("status") == "no_pat":
        actions.append(
            {
                "title": "Connect Airtable",
                "reason": "Add your Airtable PAT so the fleet can read base updates.",
                "link_label": "Generate token",
                "link_href": airtable.get("help_url", "https://airtable.com/create/tokens/new"),
            }
        )
    elif airtable.get("status") == "needs_config":
        actions.append(
            {
                "title": "Tell Airtable which base to poll",
                "reason": "Set AIRTABLE_BASE_ID + AIRTABLE_TABLE in the Hive env.",
                "link_label": "Open Settings",
                "link_href": "/pm/settings",
            }
        )

    if research.get("status") == "no_data":
        actions.append(
            {
                "title": "Run a fleet pulse",
                "reason": "No research outcomes recorded in the last 24h.",
                "link_label": "Trigger pulse",
                "link_href": "/pm/agents",
            }
        )

    # Surface a few real items as actionable if status is ok.
    for issue in jira.get("issues", [])[:3]:
        actions.append(
            {
                "title": f"Review {issue.get('key', '')}: {issue.get('summary', '')}",
                "reason": f"Updated in last 24h — current status {issue.get('status', '?')}",
                "link_label": "Open in Jira",
                "link_href": issue.get("url", "/pm/agents"),
            }
        )

    return actions


@router.get("")
async def get_daily_report(request: Request) -> dict[str, Any]:
    uid = _user_id(request)
    generated_at = datetime.now(UTC).isoformat()
    jira = await _poll_jira(uid)
    airtable = await _poll_airtable(uid)
    research = _research_summary(uid)
    actions = _suggested_actions(uid, jira, airtable, research)
    return {
        "generated_at": generated_at,
        "window_hours": 24,
        "jira": jira,
        "airtable": airtable,
        "research": research,
        "suggested_actions": actions,
    }
