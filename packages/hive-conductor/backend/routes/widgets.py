"""Deterministic widget data endpoints.

Widgets call these directly — no LLM in the loop at render time.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Query, Request

router = APIRouter(tags=["widgets"])
logger = logging.getLogger("hive.widgets")

_JIRA_BASE = os.environ.get("JIRA_BASE_URL", "https://jira.example.com")


def _jira_headers(pat: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {pat}", "Accept": "application/json"}


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    return str(user.get("id") or user.get("username") or "dev")


def _use_secret(store: Any, user_id: str, provider_id: str) -> str | None:
    """Single allowlisted callsite for use_secret — lambda is centralised here."""
    try:
        return store.use_secret(user_id, provider_id, lambda s: s)
    except Exception:
        return None


def _jira_pat(request: Request) -> str | None:
    uid = _user_id(request)
    try:
        from services import user_credentials as cred_svc

        store = cred_svc.get_credential_store()
        if store is None:
            return None
        for provider_id in ("atlassian_server_jira", "jira", "atlassian_rovo_mcp"):
            try:
                if store.has_secret(uid, provider_id):
                    return _use_secret(store, uid, provider_id)
            except Exception:
                continue
        return None
    except Exception:
        return None


def _airtable_token(request: Request) -> str | None:
    """The user's Airtable token — their own id first, then the shared 'user' id."""
    try:
        from services import user_credentials as cred_svc

        store = cred_svc.get_credential_store()
        if not store:
            return None
        for try_uid in (_user_id(request), "user"):
            try:
                if store.has_secret(try_uid, "airtable"):
                    return _use_secret(store, try_uid, "airtable")
            except Exception:
                continue
        return None
    except Exception:
        return None


def _airtable_base_id() -> str:
    """First configured Airtable base_id from the per-user provider config."""
    import stores

    for key in stores.user_provider_config:
        if key.endswith(":airtable"):
            val = stores.user_provider_config.get(key)
            if isinstance(val, dict) and val.get("base_id"):
                return str(val["base_id"]).split("/")[0]
    return ""


def _build_jql(
    project: str,
    status: str | None,
    assignee: str | None,
    days: int | None,
    jql_extra: str | None,
) -> str:
    """Assemble and sanitize the JQL (jql_extra may be LLM-built and sloppy)."""
    parts: list[str] = [f"project = {project}"]
    if status:
        parts.append(f'status = "{status}"')
    if assignee:
        parts.append(f"assignee = {assignee}")
    if days:
        parts.append(f"created >= -{days}d")
    if jql_extra:
        # Sanitize: strip leading AND/OR, fix double operators
        cleaned = jql_extra.strip()
        if cleaned.upper().startswith("AND "):
            cleaned = cleaned[4:]
        elif cleaned.upper().startswith("OR "):
            cleaned = cleaned[3:]
        parts.append(cleaned)
    jql = " AND ".join(parts)
    if "ORDER BY" not in jql.upper():
        jql += " ORDER BY updated DESC"
    return _sanitize_jql(jql)


def _sanitize_jql(jql: str) -> str:
    """Repair LLM-built JQL: doubled operators, stray AND/OR before ORDER BY."""
    while " AND AND " in jql or " OR OR " in jql or "  " in jql:
        jql = jql.replace(" AND AND ", " AND ").replace(" OR OR ", " OR ").replace("  ", " ")
    jql = jql.strip()
    if " ORDER BY" in jql:
        pre, order = jql.split(" ORDER BY", 1)
        pre = pre.rstrip()
        if pre.endswith(" AND"):
            pre = pre[:-4]
        if pre.endswith(" OR"):
            pre = pre[:-3]
        jql = pre + " ORDER BY" + order
    return jql


def _flatten_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Flatten Airtable field values for display (linked records, collaborators)."""
    flat: dict[str, Any] = {"id": rec["id"]}
    for k, v in rec.get("fields", {}).items():
        # Flatten single-element arrays (linked record lookups)
        if isinstance(v, list) and len(v) == 1:
            flat[k] = v[0]
        elif isinstance(v, list):
            flat[k] = ", ".join(str(x) for x in v[:3])
        elif isinstance(v, dict) and "name" in v:
            flat[k] = v["name"]
        elif isinstance(v, dict) and "email" in v:
            flat[k] = v.get("name", v["email"])
        else:
            flat[k] = v
    return flat


def _breakdown(records: list[dict[str, Any]], group_by: str) -> dict[str, int]:
    """Counts per group_by value across flattened records."""
    counts: dict[str, int] = {}
    for rec in records:
        val = rec.get(group_by, "(unset)")
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val) if val else "(unset)"
        elif not val:
            val = "(unset)"
        counts[str(val)] = counts.get(str(val), 0) + 1
    return counts


def _table_view(records: list[dict[str, Any]], table: str) -> dict[str, Any]:
    """Full records as rows + sorted columns (for table/pivot view)."""
    skip = {"id", "Auto_Id_DO_NOT_TOUCH", "Created"}
    table_records = []
    all_columns: set[str] = set()
    for rec in records:
        row = {}
        for k, v in rec.items():
            if k in skip:
                continue
            all_columns.add(k)
            row[k] = str(v) if v else ""
        table_records.append(row)
    return {
        "table_data": table_records,
        "columns": sorted(all_columns),
        "count": len(table_records),
        "table": table,
    }


@router.get("/jira")
async def widget_jira(
    request: Request,
    project: str = Query(...),
    status: str | None = None,
    assignee: str | None = None,
    days: int | None = None,
    jql_extra: str | None = None,
    max_results: int = 50,
) -> dict[str, Any]:
    """Execute JQL and return structured data for a Jira widget."""
    pat = _jira_pat(request)
    if not pat:
        return {"error": "No Jira credentials configured.", "total": 0, "issues": []}

    jql = _build_jql(project, status, assignee, days, jql_extra)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First page
            page_size = min(max_results, 100)
            r = await client.get(
                f"{_JIRA_BASE}/rest/api/2/search",
                params={
                    "jql": jql,
                    "maxResults": page_size,
                    "startAt": 0,
                    "fields": "summary,status,assignee,issuetype,priority,updated,created",
                },
                headers=_jira_headers(pat),
            )
            r.raise_for_status()
            data = r.json()
            total = data.get("total", 0)
            all_issues_raw = data.get("issues", [])

            # Paginate remaining for accurate aggregation (cap at 1000)
            while len(all_issues_raw) < min(total, 1000):
                r = await client.get(
                    f"{_JIRA_BASE}/rest/api/2/search",
                    params={
                        "jql": jql,
                        "maxResults": 100,
                        "startAt": len(all_issues_raw),
                        "fields": "status,priority",
                    },
                    headers=_jira_headers(pat),
                )
                if r.status_code != 200:
                    break
                page = r.json().get("issues", [])
                if not page:
                    break
                all_issues_raw.extend(page)

            # Build detailed list from first page only (for display)
            display_issues = [
                {
                    "key": i.get("key"),
                    "summary": (f := i.get("fields", {})).get("summary"),
                    "status": (f.get("status") or {}).get("name"),
                    "type": (f.get("issuetype") or {}).get("name"),
                    "priority": (f.get("priority") or {}).get("name"),
                    "assignee": (f.get("assignee") or {}).get("displayName"),
                    "updated": f.get("updated"),
                }
                for i in all_issues_raw[:page_size]
            ]
            # Compute status breakdown from ALL fetched issues
            status_counts: dict[str, int] = {}
            for i in all_issues_raw:
                s = ((i.get("fields") or {}).get("status") or {}).get("name") or "Unknown"
                status_counts[s] = status_counts.get(s, 0) + 1

            return {
                "total": total,
                "issues": display_issues,
                "statuses": status_counts,
                "shown": len(display_issues),
                "jql": jql,
            }
    except Exception as e:
        logger.warning("Jira widget query failed: %s", e)
        return {"error": str(e)[:200], "total": 0, "issues": [], "statuses": {}}


@router.get("/airtable")
async def widget_airtable(
    request: Request,
    table: str = Query(...),
    filter_formula: str | None = None,
    max_records: int = 20,
    group_by: str | None = None,
    display_field: str | None = None,
) -> dict[str, Any]:
    """Query Airtable deterministically. Use group_by for breakdowns, display_field for lists."""
    token = _airtable_token(request)
    if not token:
        return {"error": "Airtable not configured.", "records": []}
    base_id = _airtable_base_id()
    if not base_id:
        return {"error": "No base_id configured.", "records": []}

    params: dict[str, str] = {"maxRecords": str(min(max_records, 100))}
    if filter_formula:
        params["filterByFormula"] = filter_formula

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://api.airtable.com/v0/{base_id}/{table}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            r.raise_for_status()
            data = r.json()
            records = [_flatten_record(rec) for rec in data.get("records", [])]

            # group_by → breakdown (counts per value)
            if group_by:
                return {
                    "breakdown": _breakdown(records, group_by),
                    "total": len(records),
                    "field": group_by,
                    "table": table,
                }

            # display_field → simplified records
            if display_field:
                simple = [
                    {
                        "name": str(rec.get(display_field, rec.get("Name", rec.get("id", "")))),
                        "id": rec.get("id", ""),
                    }
                    for rec in records
                ]
                return {"records": simple, "count": len(simple), "table": table}

            # Table mode: all fields as columns for rich table display
            return _table_view(records, table)
    except Exception as e:
        return {"error": str(e)[:200], "records": []}


@router.get("/metrics")
async def widget_metrics(
    request: Request,
    metric: str = Query(..., description="latency|ttft|cost|tokens|invocations|errors"),
    period: str = "1h",
) -> dict[str, Any]:
    """Return a specific metric value."""
    from services.chat_completion import get_chat_metrics_summary

    summary = get_chat_metrics_summary()
    # Map metric names to values
    mapping: dict[str, Any] = {
        "latency": {"value": summary.get("avg_latency_ms", 0), "unit": "ms"},
        "ttft": {"value": summary.get("avg_ttft_ms", 0), "unit": "ms"},
        "cost": {"value": summary.get("total_cost", 0), "unit": "$"},
        "tokens": {"value": summary.get("total_tokens", 0), "unit": "tokens"},
        "invocations": {"value": summary.get("total_requests", 0), "unit": "requests"},
        "errors": {"value": summary.get("error_count", 0), "unit": "errors"},
    }
    result = mapping.get(metric, {"value": 0, "unit": "?"})
    result["metric"] = metric
    result["period"] = period
    return result


@router.get("/airtable/fields")
async def widget_airtable_fields(
    request: Request,
    table: str = Query(...),
) -> dict[str, Any]:
    """Return field names for a given Airtable table (by sampling records)."""
    token = _airtable_token(request)
    if not token:
        return {"fields": []}
    base_id = _airtable_base_id()
    if not base_id:
        return {"fields": []}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://api.airtable.com/v0/{base_id}/{table}",
                headers={"Authorization": f"Bearer {token}"},
                params={"maxRecords": "20"},
            )
            r.raise_for_status()
            data = r.json()
            # Collect all field names across sampled records
            field_set: set[str] = set()
            for rec in data.get("records", []):
                field_set.update(rec.get("fields", {}).keys())
            return {"fields": sorted(field_set), "table": table}
    except Exception:
        return {"fields": []}


@router.get("/airtable/bases")
async def widget_airtable_bases(request: Request) -> dict[str, Any]:
    """Return configured Airtable bases for the current user."""
    try:
        import stores

        # All airtable configs with base_ids
        bases = []
        for key in stores.user_provider_config:
            if "airtable" in key:
                val = stores.user_provider_config.get(key)
                if isinstance(val, dict) and val.get("base_id"):
                    bid = str(val["base_id"]).split("/")[0]
                    bases.append({"id": bid, "name": val.get("name", bid)})
        if not bases:
            # Fall back to the Airtable metadata API
            token = _airtable_token(request)
            if token:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        r = await client.get(
                            "https://api.airtable.com/v0/meta/bases",
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        if r.status_code == 200:
                            for b in r.json().get("bases", []):
                                bases.append({"id": b["id"], "name": b.get("name", b["id"])})
                except Exception:
                    pass
        return {"bases": bases}
    except Exception:
        return {"bases": []}


@router.get("/airtable/tables")
async def widget_airtable_tables(request: Request, base_id: str = Query(...)) -> dict[str, Any]:
    """Return tables for a specific Airtable base."""
    try:
        token = _airtable_token(request)
        if not token:
            return {"tables": []}

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 200:
                tables = [{"id": t["id"], "name": t["name"]} for t in r.json().get("tables", [])]
                return {"tables": tables, "base_id": base_id}
            # Fallback: try listing records from known tables
            return {"tables": [], "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"tables": [], "error": str(e)[:100]}


@router.post("/screenshot")
async def capture_screenshot(request: Request) -> dict[str, Any]:
    """Capture a screenshot of the current dashboard and return as base64."""
    import base64

    try:
        from playwright.async_api import async_playwright

        # Get user session to pass to the browser
        session_id = request.cookies.get("hive_session", "")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
            await ctx.add_cookies(
                [{"name": "hive_session", "value": session_id, "domain": "localhost", "path": "/"}]
            )
            page = await ctx.new_page()
            await page.goto(
                "http://localhost:5173/dashboard", wait_until="networkidle", timeout=15000
            )
            await page.wait_for_timeout(3000)
            # Dismiss onboarding if present
            skip = page.locator("button:has-text('Skip')")
            if await skip.is_visible(timeout=1000):
                await skip.click()
                await page.wait_for_timeout(500)
            screenshot = await page.screenshot(full_page=True)
            await browser.close()

        b64 = base64.b64encode(screenshot).decode("utf-8")
        return {"screenshot": b64, "width": 1440, "height": 900}
    except ImportError:
        return {"error": "playwright not installed on backend"}
    except Exception as e:
        return {"error": str(e)[:200]}
