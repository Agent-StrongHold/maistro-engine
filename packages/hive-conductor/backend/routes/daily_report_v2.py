"""Daily report v2 — simple, uses same path as chat tools."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from typing import Any

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


@router.get("")
async def daily_report(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None) or {}
    user_id = str(user.get("id", ""))

    pat = _get_pat(user_id)
    jira: dict[str, Any] = {"status": "no_pat", "count": 0, "issues": []}

    if pat:
        jql = "project = JEDAI AND updated >= -7d ORDER BY updated DESC"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    "https://myjira.disney.com/rest/api/2/search",
                    params={"jql": jql, "maxResults": 15, "fields": "summary,status,assignee,issuetype,updated"},
                    headers={"Authorization": f"Bearer {pat}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
                issues = []
                for i in data.get("issues", []):
                    f = i.get("fields", {})
                    issues.append({
                        "key": i.get("key"),
                        "summary": f.get("summary"),
                        "status": (f.get("status") or {}).get("name"),
                        "assignee": ((f.get("assignee") or {}).get("displayName")),
                        "updated": f.get("updated"),
                    })
                jira = {"status": "ok", "count": data.get("total", 0), "issues": issues}
        except Exception as e:
            jira = {"status": "error", "detail": str(e), "count": 0, "issues": []}

    from datetime import datetime, UTC

    # Airtable
    airtable: dict[str, Any] = {"status": "not_configured", "count": 0, "issues": []}
    airtable_pat = None
    try:
        from services import user_credentials as cred_svc
        store = cred_svc.get_credential_store()
        if store:
            for pid in ("airtable", "airtable_pat"):
                try:
                    if store.has_secret(user_id, pid):
                        airtable_pat = store.use_secret(user_id, pid, lambda s: s)
                        break
                except Exception:
                    continue
            # If still not found, the PAT might be stored but under a different mechanism
            if not airtable_pat:
                try:
                    airtable_pat = store.use_secret(user_id, "airtable", lambda s: s)
                except Exception:
                    pass
    except Exception:
        pass

    if airtable_pat:
        base_id = "app0i9FWbZrctJuS6"  # JEDAI base
        try:
            # Get first table
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
                    headers={"Authorization": f"Bearer {airtable_pat}"},
                )
                table_id = ""
                if r.status_code == 200:
                    tables = r.json().get("tables", [])
                    if tables:
                        table_id = tables[0].get("id", "")

                if table_id:
                    r = await client.get(
                        f"https://api.airtable.com/v0/{base_id}/{table_id}",
                        params={"maxRecords": 10},
                        headers={"Authorization": f"Bearer {airtable_pat}"},
                    )
                    if r.status_code == 200:
                        records = r.json().get("records", [])
                        items = []
                        for rec in records[:10]:
                            fields = rec.get("fields", {})
                            name = fields.get("Name") or fields.get("Title") or fields.get("Use Case Name") or next(iter(fields.values()), "")
                            items.append({"id": rec.get("id"), "name": str(name)[:100]})
                        airtable = {"status": "ok", "count": len(records), "records": items}
                    else:
                        airtable = {"status": "error", "detail": f"Airtable {r.status_code}", "count": 0, "issues": []}
        except Exception as e:
            airtable = {"status": "error", "detail": str(e)[:100], "count": 0, "issues": []}

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "jira": jira,
        "airtable": airtable,
        "research": {"status": "not_configured", "count": 0},
        "suggested_actions": [
            {"title": "Ask in Chat", "reason": "Use chat to query Jira, blockers, or Confluence", "link_label": "Open Chat", "link_href": "/chat"},
        ],
    }
