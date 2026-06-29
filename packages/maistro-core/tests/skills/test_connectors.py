"""Coverage for skills/connectors.py."""

from __future__ import annotations

from typing import Any

import pytest

from maistro.skills import connectors
from maistro.skills.connectors import (
    _matches,
    _normalize,
    get_demo_agent_content,
    get_demo_skill_content,
    search_claude_plugins,
    search_clawhub,
    search_gitagent_repos,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeHttpClient:
    def __init__(
        self, response: _FakeResponse | None = None, error: Exception | None = None
    ) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get(
        self, url: str, params: dict[str, Any] | None = None, timeout: float = 5.0
    ) -> _FakeResponse:
        self.calls.append((url, params or {}))
        if self._error:
            raise self._error
        assert self._response is not None
        return self._response


@pytest.fixture(autouse=True)
def reset_claude_cache() -> None:
    connectors._claude_cache = []
    connectors._claude_cache_ts = 0.0


def test_normalize_lowercases_and_replaces_separators() -> None:
    assert _normalize("Web-Search_Tool") == "web search tool"


def test_matches_returns_true_for_empty_query() -> None:
    assert _matches("", "anything") is True


def test_matches_returns_true_when_all_terms_present() -> None:
    assert _matches("web search", "Web-Search", "desc") is True


def test_matches_returns_false_when_a_term_missing() -> None:
    assert _matches("web search", "Web-Search tool", "unrelated") is True
    assert _matches("github pr", "web search", "desc") is False


async def test_search_clawhub_returns_demo_data_when_no_client() -> None:
    results = await search_clawhub()
    assert len(results) == 8
    assert results[0].name == "web-search"


async def test_search_clawhub_filters_demo_data_by_query() -> None:
    results = await search_clawhub(query="github")
    assert len(results) == 1
    assert results[0].name == "github-manager"


async def test_search_clawhub_paginates_demo_data() -> None:
    page1 = await search_clawhub(page=1, per_page=2)
    page2 = await search_clawhub(page=2, per_page=2)
    assert [s.name for s in page1] == ["web-search", "github-manager"]
    assert [s.name for s in page2] == ["database-query", "slack-notifications"]


async def test_search_clawhub_uses_client_list_response() -> None:
    client = _FakeHttpClient(
        response=_FakeResponse(
            200,
            [
                {
                    "name": "x",
                    "description": "y",
                    "url": "u",
                    "author": "a",
                    "tags": ["t"],
                    "downloads": 5,
                }
            ],
        )
    )
    results = await search_clawhub(http_client=client)
    assert len(results) == 1
    assert results[0].name == "x"
    assert results[0].source_url == "u"
    assert results[0].download_count == 5
    assert len(client.calls) == 1


async def test_search_clawhub_uses_client_dict_items_response() -> None:
    client = _FakeHttpClient(
        response=_FakeResponse(200, {"items": [{"name": "z", "description": "d"}]})
    )
    results = await search_clawhub(http_client=client)
    assert len(results) == 1
    assert results[0].name == "z"


async def test_search_clawhub_falls_back_to_demo_when_results_empty() -> None:
    client = _FakeHttpClient(response=_FakeResponse(200, {"items": []}))
    results = await search_clawhub(http_client=client)
    assert len(results) == 8


async def test_search_clawhub_falls_back_to_demo_on_non_200() -> None:
    client = _FakeHttpClient(response=_FakeResponse(404, {}))
    results = await search_clawhub(http_client=client)
    assert len(results) == 8


async def test_search_clawhub_falls_back_to_demo_on_exception() -> None:
    client = _FakeHttpClient(error=RuntimeError("network down"))
    results = await search_clawhub(http_client=client)
    assert len(results) == 8


async def test_search_claude_plugins_returns_demo_when_no_client() -> None:
    results = await search_claude_plugins()
    assert len(results) == 5
    assert results[0].name == "mcp-filesystem"


async def test_search_claude_plugins_filters_demo_by_query_and_tags() -> None:
    results = await search_claude_plugins(query="github")
    assert len(results) == 1
    assert results[0].name == "mcp-github"


async def test_search_claude_plugins_builds_cache_from_client() -> None:
    client = _FakeHttpClient(
        response=_FakeResponse(
            200,
            {
                "plugins": [
                    {
                        "name": "p1",
                        "description": "d1",
                        "homepage": "h1",
                        "author": {"name": "auth1"},
                        "tags": ["a", "b"],
                    },
                    {
                        "name": "p2",
                        "description": "d2",
                        "author": "auth2",
                        "keywords": ["c"],
                    },
                ]
            },
        )
    )
    results = await search_claude_plugins(http_client=client)
    assert len(results) == 2
    assert results[0].author == "auth1"
    assert results[1].author == "auth2"
    assert results[1].tags == ("c",)
    assert connectors._claude_cache_ts != 0.0


async def test_search_claude_plugins_uses_cache_within_ttl() -> None:
    connectors._claude_cache = [connectors.SkillMetadata(name="cached", description="d")]
    connectors._claude_cache_ts = connectors.time.monotonic()
    client = _FakeHttpClient(error=AssertionError("should not be called"))
    results = await search_claude_plugins(http_client=client)
    assert len(results) == 1
    assert results[0].name == "cached"
    assert client.calls == []


async def test_search_claude_plugins_falls_back_to_demo_on_non_200() -> None:
    client = _FakeHttpClient(response=_FakeResponse(500, {}))
    results = await search_claude_plugins(http_client=client)
    assert len(results) == 5


async def test_search_claude_plugins_falls_back_to_demo_on_exception() -> None:
    client = _FakeHttpClient(error=RuntimeError("down"))
    results = await search_claude_plugins(http_client=client)
    assert len(results) == 5


async def test_search_gitagent_repos_returns_demo_when_no_client() -> None:
    results = await search_gitagent_repos()
    assert len(results) == 5
    assert results[0]["name"] == "code-reviewer"


async def test_search_gitagent_repos_returns_demo_when_no_query_even_with_client() -> None:
    client = _FakeHttpClient(error=AssertionError("should not be called"))
    results = await search_gitagent_repos(http_client=client)
    assert len(results) == 5
    assert client.calls == []


async def test_search_gitagent_repos_filters_demo_by_query() -> None:
    results = await search_gitagent_repos(query="devops")
    assert len(results) == 1
    assert results[0]["name"] == "devops-agent"


async def test_search_gitagent_repos_uses_client_response() -> None:
    client = _FakeHttpClient(
        response=_FakeResponse(
            200,
            {
                "items": [
                    {
                        "name": "repo1",
                        "description": "desc1",
                        "html_url": "url1",
                        "owner": {"login": "owner1"},
                        "stargazers_count": 10,
                    }
                ]
            },
        )
    )
    results = await search_gitagent_repos(query="repo1", http_client=client)
    assert len(results) == 1
    assert results[0]["name"] == "repo1"
    assert results[0]["author"] == "owner1"
    assert results[0]["stars"] == 10


async def test_search_gitagent_repos_falls_back_to_demo_when_no_items() -> None:
    client = _FakeHttpClient(response=_FakeResponse(200, {"items": []}))
    results = await search_gitagent_repos(query="anything", http_client=client)
    assert len(results) == 0


async def test_search_gitagent_repos_falls_back_to_demo_on_non_200() -> None:
    client = _FakeHttpClient(response=_FakeResponse(503, {}))
    results = await search_gitagent_repos(query="devops", http_client=client)
    assert len(results) == 1
    assert results[0]["name"] == "devops-agent"


async def test_search_gitagent_repos_falls_back_to_demo_on_exception() -> None:
    client = _FakeHttpClient(error=RuntimeError("down"))
    results = await search_gitagent_repos(query="devops", http_client=client)
    assert len(results) == 1
    assert results[0]["name"] == "devops-agent"


def test_get_demo_skill_content_returns_content_for_known_url() -> None:
    content = get_demo_skill_content("https://clawhub.ai/skills/community/web-search")
    assert content is not None
    assert "web_search" in content


def test_get_demo_skill_content_returns_none_for_unknown_url() -> None:
    assert get_demo_skill_content("https://unknown.example/x") is None


def test_get_demo_agent_content_returns_content_for_known_url() -> None:
    content = get_demo_agent_content("https://github.com/gitagent-community/devops-agent")
    assert content is not None
    assert "agent.yaml" in content
    assert "SOUL.md" in content


def test_get_demo_agent_content_returns_none_for_unknown_url() -> None:
    assert get_demo_agent_content("https://unknown.example/x") is None
