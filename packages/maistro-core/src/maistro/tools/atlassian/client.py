"""HTTP client for mcp-jedai-atlassian (the JEDAI on-prem Atlassian MCP).

Speaks streamable-HTTP MCP at `/mcp` (FastMCP convention). For v0 we
use a single-shot tools/call JSON-RPC POST — the streaming notification
channel isn't needed for synchronous tool invocations.

Per-request auth: PATs go in headers, never env. URLs come from env
(`ATLASSIAN_MCP_URL`, defaults to docker-compose service hostname).

Compatible with Cloud Rovo MCP post-migration: same headers, same JSON-RPC
shape; only the URL changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx


class AtlassianMCPError(RuntimeError):
    """Raised when mcp-jedai-atlassian returns an error or is unreachable."""


@dataclass(frozen=True)
class JiraIssue:
    key: str
    summary: str
    status: str = ""
    assignee: str | None = None
    issuetype: str = ""
    url: str | None = None
    description: str = ""
    labels: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class JiraSearchResult:
    issues: tuple[JiraIssue, ...]
    total: int
    jql: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "jql": self.jql,
            "total": self.total,
            "issues": [
                {
                    "key": i.key,
                    "summary": i.summary,
                    "status": i.status,
                    "assignee": i.assignee,
                    "issuetype": i.issuetype,
                    "url": i.url,
                    "labels": list(i.labels),
                }
                for i in self.issues
            ],
        }


def _resolve_mcp_url() -> str:
    return (
        os.environ.get("ATLASSIAN_MCP_URL")
        or os.environ.get("ATLASSIAN_SERVER_MCP_URL")
        or "http://atlassian-mcp:8000/mcp"
    )


class AtlassianMCPClient:
    """v0 client for the on-prem JEDAI Atlassian MCP.

    Methods take PATs as explicit arguments — callers fetch them from
    the per-user encrypted credential store (Hive Credentials nav). This
    keeps tokens off env/disk inside maistro-core itself.
    """

    def __init__(
        self,
        *,
        mcp_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.mcp_url = (mcp_url or _resolve_mcp_url()).rstrip("/")
        self.timeout = timeout
        # Health probe endpoint is at /healthz on the same host (not under /mcp).
        # Derive the base URL by stripping a trailing /mcp segment if present.
        base = self.mcp_url
        if base.endswith("/mcp"):
            base = base[: -len("/mcp")]
        self.health_url = f"{base}/healthz"

    def _headers(self, jira_pat: str | None, confluence_pat: str | None) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
        # Split-header mode — per mcp-jedai-atlassian's UserTokenMiddleware. Both
        # products can be authed simultaneously in a single request.
        if jira_pat:
            h["X-Atlassian-Jira-Personal-Token"] = jira_pat
        if confluence_pat:
            h["X-Atlassian-Confluence-Personal-Token"] = confluence_pat
        return h

    async def healthz(self) -> dict[str, Any]:
        """Probe the MCP container (no auth required for /healthz)."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(self.health_url)
            except httpx.HTTPError as exc:
                raise AtlassianMCPError(f"healthz unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise AtlassianMCPError(f"healthz returned {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except ValueError:
            return {"status": resp.text}

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        jira_pat: str | None = None,
        confluence_pat: str | None = None,
    ) -> dict[str, Any]:
        """Invoke an MCP tool by name. Returns the parsed JSON result.

        Raises AtlassianMCPError on transport failure, HTTP error, or
        MCP-level error response.
        """
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    self.mcp_url,
                    json=body,
                    headers=self._headers(jira_pat, confluence_pat),
                )
            except httpx.HTTPError as exc:
                raise AtlassianMCPError(
                    f"MCP transport error for tool '{tool_name}': {exc}"
                ) from exc
        if resp.status_code >= 400:
            raise AtlassianMCPError(
                f"MCP '{tool_name}' returned {resp.status_code}: {resp.text[:500]}"
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AtlassianMCPError(
                f"MCP '{tool_name}' returned non-JSON: {resp.text[:300]}"
            ) from exc
        if "error" in payload:
            err = payload["error"]
            raise AtlassianMCPError(
                f"MCP '{tool_name}' error: {err.get('message', err)} (code={err.get('code', '?')})"
            )
        result = payload.get("result", payload)
        return result if isinstance(result, dict) else {"raw": result}

    # ------------------------------------------------------------------
    # Convenience wrappers around the tools mcp-jedai-atlassian exposes.
    # Tool inputs/outputs match the JEDAI repo's tool definitions in
    # src/mcp_jedai_atlassian/tools/{jira,confluence,health}.py.
    # ------------------------------------------------------------------

    async def jira_search_issues(
        self, jql: str, *, max_results: int = 25, jira_pat: str
    ) -> JiraSearchResult:
        result = await self.call_tool(
            "jira_search_issues",
            {"jql": jql, "max_results": max_results},
            jira_pat=jira_pat,
        )
        return self._parse_jira_search(result, jql=jql)

    async def jira_search_by_text(
        self,
        text: str,
        *,
        project: str | None = None,
        max_results: int = 25,
        jira_pat: str,
    ) -> JiraSearchResult:
        args: dict[str, Any] = {"text": text, "max_results": max_results}
        if project:
            args["project"] = project
        result = await self.call_tool("jira_search_by_text", args, jira_pat=jira_pat)
        return self._parse_jira_search(result, jql=f'text ~ "{text}"')

    async def jira_get_my_issues(self, *, max_results: int = 25, jira_pat: str) -> JiraSearchResult:
        result = await self.call_tool(
            "jira_get_my_issues",
            {"max_results": max_results},
            jira_pat=jira_pat,
        )
        return self._parse_jira_search(
            result, jql="assignee = currentUser() OR reporter = currentUser()"
        )

    async def jira_get_issue(self, issue_key: str, *, jira_pat: str) -> JiraIssue:
        result = await self.call_tool("jira_get_issue", {"issue_key": issue_key}, jira_pat=jira_pat)
        # mcp-jedai-atlassian shape: result is either an issue dict or wraps one in "content"
        issue = result.get("issue") or result.get("content") or result
        if isinstance(issue, list) and issue:
            issue = issue[0]
        return self._parse_jira_issue(issue if isinstance(issue, dict) else {})

    async def confluence_search(
        self,
        query: str,
        *,
        max_results: int = 25,
        confluence_pat: str,
    ) -> dict[str, Any]:
        return await self.call_tool(
            "confluence_search",
            {"query": query, "max_results": max_results},
            confluence_pat=confluence_pat,
        )

    async def confluence_get_page(self, page_id: str, *, confluence_pat: str) -> dict[str, Any]:
        return await self.call_tool(
            "confluence_get_page",
            {"page_id": page_id},
            confluence_pat=confluence_pat,
        )

    @staticmethod
    def _parse_jira_search(result: dict[str, Any], *, jql: str) -> JiraSearchResult:
        # Tolerate a few shapes — Atlassian-Python-API + FastMCP can wrap
        # results in {content: [...]} or {issues: [...]} depending on version.
        raw_issues = (
            result.get("issues")
            or result.get("content")
            or result.get("data", {}).get("issues")
            or []
        )
        if not isinstance(raw_issues, list):
            raw_issues = []
        issues = tuple(
            AtlassianMCPClient._parse_jira_issue(i) for i in raw_issues if isinstance(i, dict)
        )
        total = int(result.get("total", len(issues)))
        return JiraSearchResult(issues=issues, total=total, jql=jql)

    @staticmethod
    def _parse_jira_issue(d: dict[str, Any]) -> JiraIssue:
        # Atlassian REST returns nested fields; FastMCP may flatten them. Try both.
        fields = d.get("fields") if isinstance(d.get("fields"), dict) else d
        assignee_obj = fields.get("assignee") if isinstance(fields, dict) else None
        assignee = (
            assignee_obj.get("displayName") if isinstance(assignee_obj, dict) else assignee_obj
        )
        status_obj = fields.get("status") if isinstance(fields, dict) else None
        status = status_obj.get("name") if isinstance(status_obj, dict) else (status_obj or "")
        issuetype_obj = fields.get("issuetype") if isinstance(fields, dict) else None
        issuetype = (
            issuetype_obj.get("name") if isinstance(issuetype_obj, dict) else (issuetype_obj or "")
        )
        labels = fields.get("labels", []) if isinstance(fields, dict) else []
        return JiraIssue(
            key=str(d.get("key", "")),
            summary=str(fields.get("summary", "") if isinstance(fields, dict) else ""),
            status=str(status or ""),
            assignee=str(assignee) if assignee else None,
            issuetype=str(issuetype or ""),
            url=str(d.get("self") or d.get("url") or "") or None,
            description=str(fields.get("description", "") if isinstance(fields, dict) else "")[
                :2000
            ],
            labels=tuple(str(l) for l in labels) if isinstance(labels, list) else (),
        )


__all__ = [
    "AtlassianMCPClient",
    "AtlassianMCPError",
    "JiraIssue",
    "JiraSearchResult",
]
