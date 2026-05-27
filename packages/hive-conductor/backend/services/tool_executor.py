"""Tool-enabled DAG node executor.

Nodes can now declare tools they need. The executor provides:
  - web_search: real Playwright-driven Google/DuckDuckGo search
  - browse_url: fetch and summarize a real URL
  - clarify: multi-turn Q&A to gather requirements before generating

This replaces the naive "ask LLM to pretend it researched" pattern.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("hive.tool_executor")


async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Real web search via BrowserClient or fallback to Serper/Tavily."""
    # Try Serper first (fast, no browser needed)
    serper_key = os.environ.get("SERPER_API_KEY", "")
    if serper_key:
        return await _serper_search(query, max_results, serper_key)

    # Try Tavily
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    if tavily_key:
        return await _tavily_search(query, max_results, tavily_key)

    # Fallback: BrowserClient (Playwright + browser-use)
    try:
        from maistro.tools.browser import BrowserClient
        client = BrowserClient()
        result = await client.search_web(query, max_results=max_results)
        await client.aclose()
        return {
            "query": query,
            "summary": result.summary,
            "citations": [{"title": c.title, "url": c.url, "snippet": c.snippet} for c in result.citations],
            "source": result.source,
        }
    except Exception as e:
        logger.warning(f"All search methods failed for '{query}': {e}")
        return {"query": query, "summary": "", "citations": [], "source": "error", "error": str(e)}


async def browse_url(url: str, task: str = "Extract key facts and quotes") -> dict[str, Any]:
    """Fetch and summarize a real URL."""
    try:
        from maistro.tools.browser import BrowserClient
        client = BrowserClient()
        result = await client.browse(url, task)
        await client.aclose()
        return {"url": url, "title": result.title, "text": result.text, "duration_ms": result.duration_ms}
    except Exception as e:
        # Fallback: simple HTTP fetch
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.get(url, follow_redirects=True)
                text = r.text[:5000]
                return {"url": url, "title": url, "text": text, "duration_ms": 0}
        except Exception as e2:
            return {"url": url, "error": str(e2)}


async def clarify(questions: list[str], context: dict[str, Any]) -> dict[str, str]:
    """Multi-turn clarification — ask questions, get answers from context or LLM.
    
    In production, this would be interactive. For DAG execution, we use the
    input context to answer clarifying questions, or generate reasonable defaults.
    """
    base = os.environ.get("LITELLM_API_BASE", "").rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    key = os.environ.get("LITELLM_API_KEY", "")

    prompt = (
        "You are helping clarify requirements for a creative project.\n"
        f"Original request: {context.get('input', '')}\n\n"
        "Answer each question with specific, detailed answers. "
        "If the original request doesn't specify, make a creative choice "
        "that would result in high-quality output.\n\n"
        "Questions:\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions)) +
        "\n\nAnswer each question in detail (2-3 sentences each). "
        "Output JSON: {\"answers\": {\"1\": \"...\", \"2\": \"...\", ...}}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": os.environ.get("CHAT_DEFAULT_MODEL", "gemini-2.5-flash"),
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            return data.get("answers", data)
    except Exception as e:
        logger.error(f"Clarification failed: {e}")
        return {str(i+1): "Not specified" for i in range(len(questions))}


async def _serper_search(query: str, max_results: int, api_key: str) -> dict[str, Any]:
    """Google search via Serper.dev API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
        )
        r.raise_for_status()
        data = r.json()
        organic = data.get("organic", [])[:max_results]
        citations = [{"title": o.get("title", ""), "url": o.get("link", ""), "snippet": o.get("snippet", "")} for o in organic]
        # Build summary from snippets
        summary = " ".join(c["snippet"] for c in citations if c["snippet"])
        return {"query": query, "summary": summary, "citations": citations, "source": "serper"}


async def _tavily_search(query: str, max_results: int, api_key: str) -> dict[str, Any]:
    """Web search via Tavily API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": max_results, "include_answer": True},
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])[:max_results]
        citations = [{"title": o.get("title", ""), "url": o.get("url", ""), "snippet": o.get("content", "")[:200]} for o in results]
        return {"query": query, "summary": data.get("answer", ""), "citations": citations, "source": "tavily"}


# Tool registry — nodes declare which tools they need
TOOLS = {
    "web_search": web_search,
    "browse_url": browse_url,
    "clarify": clarify,
}
