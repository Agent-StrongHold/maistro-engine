"""Daily report v2 — simple, uses same path as chat tools."""

from __future__ import annotations

import contextlib
from typing import Any

import httpx
from fastapi import APIRouter, Request

router = APIRouter(tags=["daily-report"])


def _get_pat(user_id: str) -> str | None:
    try:
        from services import user_credentials as cred_svc

        store = cred_svc.get_credential_store()
        if not store:
            return None
        for pid in ("atlassian_server_jira", "jira", "atlassian_rovo_mcp"):
            try:
                if store.has_secret(user_id, pid):
                    return store.use_secret(user_id, pid, lambda s: s)
            except Exception:
                continue
    except Exception:
        pass
    return None


async def _fetch_jira(user_id: str) -> dict[str, Any]:
    pat = _get_pat(user_id)
    if not pat:
        return {"status": "no_pat", "count": 0, "issues": []}

    jira_server_url = os.environ.get("JIRA_SERVER_URL", "")
    if not jira_server_url:
        return {
            "status": "no_config",
            "detail": "JIRA_SERVER_URL env var is not set",
            "count": 0,
            "issues": [],
        }

    jql = "project = MY_PROJECT AND updated >= -7d ORDER BY updated DESC"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{jira_server_url}/rest/api/2/search",
                params={
                    "jql": jql,
                    "maxResults": 15,
                    "fields": "summary,status,assignee,issuetype,updated",
                },
                headers={"Authorization": f"Bearer {pat}", "Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
            issues = []
            for i in data.get("issues", []):
                f = i.get("fields", {})
                issues.append(
                    {
                        "key": i.get("key"),
                        "summary": f.get("summary"),
                        "status": (f.get("status") or {}).get("name"),
                        "assignee": ((f.get("assignee") or {}).get("displayName")),
                        "updated": f.get("updated"),
                    }
                )
            return {"status": "ok", "count": data.get("total", 0), "issues": issues}
    except Exception as e:
        return {"status": "error", "detail": str(e), "count": 0, "issues": []}


def _get_airtable_pat(user_id: str) -> str | None:
    airtable_pat = None
    try:
        from services import user_credentials as cred_svc

        store = cred_svc.get_credential_store()
        if not store:
            return None
        for pid in ("airtable", "airtable_pat"):
            try:
                if store.has_secret(user_id, pid):
                    airtable_pat = store.use_secret(user_id, pid, lambda s: s)
                    break
            except Exception:
                continue
        # If still not found, the PAT might be stored but under a different mechanism
        if not airtable_pat:
            with contextlib.suppress(Exception):
                airtable_pat = store.use_secret(user_id, "airtable", lambda s: s)
    except Exception:
        return None
    return airtable_pat


def _airtable_records(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records", [])
    items = []
    for rec in records[:10]:
        fields = rec.get("fields", {})
        name = (
            fields.get("Name")
            or fields.get("Title")
            or fields.get("Use Case Name")
            or next(iter(fields.values()), "")
        )
        items.append({"id": rec.get("id"), "name": str(name)[:100]})
    return {"status": "ok", "count": len(records), "records": items}


async def _fetch_airtable(user_id: str) -> dict[str, Any]:
    airtable_pat = _get_airtable_pat(user_id)
    if not airtable_pat:
        return {"status": "not_configured", "count": 0, "issues": []}

    base_id = "appXXXXXXXXXXXXXX"  # MAISTRO base
    headers = {"Authorization": f"Bearer {airtable_pat}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
                headers=headers,
            )
            table_id = ""
            if r.status_code == 200:
                tables = r.json().get("tables", [])
                if tables:
                    table_id = tables[0].get("id", "")

            if not table_id:
                return {"status": "not_configured", "count": 0, "issues": []}

            r = await client.get(
                f"https://api.airtable.com/v0/{base_id}/{table_id}",
                params={"maxRecords": 10},
                headers=headers,
            )
            if r.status_code == 200:
                return _airtable_records(r.json())
            return {
                "status": "error",
                "detail": f"Airtable {r.status_code}",
                "count": 0,
                "issues": [],
            }
    except Exception as e:
        return {"status": "error", "detail": str(e)[:100], "count": 0, "issues": []}


@router.get("")
async def daily_report(request: Request) -> dict[str, Any]:
    from datetime import UTC, datetime

    user = getattr(request.state, "user", None) or {}
    user_id = str(user.get("id", ""))

    jira = await _fetch_jira(user_id)
    airtable = await _fetch_airtable(user_id)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "jira": jira,
        "airtable": airtable,
        "research": {"status": "not_configured", "count": 0},
        "suggested_actions": [
            {
                "title": "Ask in Chat",
                "reason": "Use chat to query Jira, blockers, or Confluence",
                "link_label": "Open Chat",
                "link_href": "/chat",
            },
        ],
    }
