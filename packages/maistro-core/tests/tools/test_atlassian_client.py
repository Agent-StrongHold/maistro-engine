"""Tests for AtlassianMCPClient's response-shaping and error-code logic.

Covers both Jira parsing (previously untested — pm_runner tests monkeypatch
past it) and the new Confluence parsing + cause-specific AtlassianMCPError
fields.
"""

from __future__ import annotations

from typing import Any

import pytest

from maistro.tools.atlassian.client import AtlassianMCPClient, AtlassianMCPError


class _FakeResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self) -> Any:
        if self._json_data is None:
            raise ValueError("no json body")
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, *args: object, **kwargs: object) -> _FakeResponse:
        return self._response

    async def get(self, *args: object, **kwargs: object) -> _FakeResponse:
        return self._response


def _patch_http(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> None:
    monkeypatch.setattr(
        "maistro.tools.atlassian.client.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(response),
    )


# ---------------------------------------------------------------------------
# Jira parsing
# ---------------------------------------------------------------------------


def test_parse_jira_issue_flattens_nested_fields() -> None:
    raw = {
        "key": "ENG-101",
        "self": "https://jira.example.com/rest/api/2/issue/101",
        "fields": {
            "summary": "Fix the thing",
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Jane Doe"},
            "issuetype": {"name": "Bug"},
            "labels": ["urgent", "backend"],
            "description": "x" * 5000,
        },
    }
    issue = AtlassianMCPClient._parse_jira_issue(raw)
    assert issue.key == "ENG-101"
    assert issue.summary == "Fix the thing"
    assert issue.status == "In Progress"
    assert issue.assignee == "Jane Doe"
    assert issue.issuetype == "Bug"
    assert issue.labels == ("urgent", "backend")
    assert len(issue.description) == 2000  # truncated, not dumped raw


def test_parse_jira_search_tolerates_issues_key() -> None:
    raw = {"issues": [{"key": "A-1", "fields": {"summary": "one"}}], "total": 1}
    result = AtlassianMCPClient._parse_jira_search(raw, jql="project = A")
    assert result.total == 1
    assert result.issues[0].key == "A-1"


# ---------------------------------------------------------------------------
# Confluence parsing
# ---------------------------------------------------------------------------


def test_parse_confluence_page_flattens_nested_body() -> None:
    raw = {
        "id": "123",
        "title": "Runbook",
        "space": {"key": "ENG"},
        "_links": {"webui": "/spaces/ENG/pages/123"},
        "body": {"storage": {"value": "<p>Steps...</p>"}},
    }
    page = AtlassianMCPClient._parse_confluence_page(raw)
    assert page.id == "123"
    assert page.title == "Runbook"
    assert page.space == "ENG"
    assert page.content == "<p>Steps...</p>"
    assert page.url == "/spaces/ENG/pages/123"


def test_parse_confluence_page_truncates_long_content() -> None:
    raw = {"id": "1", "title": "T", "body": "x" * 10_000}
    page = AtlassianMCPClient._parse_confluence_page(raw)
    assert len(page.content) == 4000


def test_parse_confluence_search_tolerates_results_key() -> None:
    raw = {
        "results": [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}],
        "total": 2,
    }
    result = AtlassianMCPClient._parse_confluence_search(raw, query="foo")
    assert result.total == 2
    assert [p.title for p in result.pages] == ["A", "B"]


@pytest.mark.asyncio
async def test_confluence_get_page_returns_flattened_page(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"id": "55", "title": "Onboarding", "body": "Welcome."},
    }
    _patch_http(monkeypatch, _FakeResponse(200, json_data=payload))
    client = AtlassianMCPClient()
    page = await client.confluence_get_page("55", confluence_pat="pat")
    assert page.id == "55"
    assert page.title == "Onboarding"
    assert page.content == "Welcome."


# ---------------------------------------------------------------------------
# Cause-specific error fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_tool_401_is_not_recoverable_and_suggests_pat_regen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_http(monkeypatch, _FakeResponse(401, text="Unauthorized"))
    client = AtlassianMCPClient()
    with pytest.raises(AtlassianMCPError) as exc_info:
        await client.call_tool("jira_get_issue", {"issue_key": "X-1"}, jira_pat="pat")
    err = exc_info.value
    assert err.error_code == "atlassian_http_error"
    assert err.recoverable is False
    assert "regenerate" in err.suggested_action.lower()


@pytest.mark.asyncio
async def test_call_tool_500_is_recoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_http(monkeypatch, _FakeResponse(500, text="boom"))
    client = AtlassianMCPClient()
    with pytest.raises(AtlassianMCPError) as exc_info:
        await client.call_tool("jira_get_issue", {"issue_key": "X-1"}, jira_pat="pat")
    err = exc_info.value
    assert err.error_code == "atlassian_http_error"
    assert err.recoverable is True


@pytest.mark.asyncio
async def test_call_tool_non_json_response_raises_invalid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_http(monkeypatch, _FakeResponse(200, json_data=None, text="<html>not json</html>"))
    client = AtlassianMCPClient()
    with pytest.raises(AtlassianMCPError) as exc_info:
        await client.call_tool("jira_get_issue", {"issue_key": "X-1"}, jira_pat="pat")
    assert exc_info.value.error_code == "atlassian_invalid_response"
