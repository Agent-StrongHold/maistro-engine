"""PM Fleet chat completion — real PM agent with real tools.

This is not a generic chatbot. It knows your program, has access to your
Jira/Confluence via stored credentials, and can take real actions.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from adapters.llm_http import HttpOpenAIProtocolLLM, StubLLMPort
from config import get_settings
from models.schemas import ChatCompletionRequest
from protocols.llm import LLMPort

logger = logging.getLogger("hive.chat")


def _use_secret(store: object, user_id: str, provider_id: str) -> str | None:
    """Single allowlisted callsite for use_secret — lambda is centralised here."""
    try:
        return store.use_secret(user_id, provider_id, lambda s: s)  # type: ignore[union-attr]
    except Exception:
        return None


def build_llm_port() -> LLMPort:
    s = get_settings()
    base = os.environ.get("LITELLM_API_BASE") or (s.litellm_api_base or "").strip()
    key = None
    if s.litellm_api_key:
        key = s.litellm_api_key.get_secret_value()
    if not key:
        key = os.environ.get("LITELLM_API_KEY") or os.environ.get("LITELLM_PROXY_KEY")
    if not base:
        base = os.environ.get("LITELLM_PROXY_URL")
    if not base or not key:
        return StubLLMPort()
    return HttpOpenAIProtocolLLM(base_url=base, api_key=key, variant=s.llm_http_variant)


def _get_program_context(user_id: str) -> dict[str, Any]:
    """Load the user's program context for system prompt injection."""
    try:
        from services import program_store as prog

        ctx = prog.get_context(user_id)
        return {
            "program_name": ctx.program_name,
            "goals": ctx.goals,
            "tools": ctx.tools,
            "constraints": ctx.constraints,
            "stakeholders": ctx.stakeholders,
            "summary": ctx.summary,
            "recent_guidance": ctx.guidance_log[-3:],
        }
    except Exception:
        return {}


def _get_jira_pat(user_id: str) -> str | None:
    """Pull Jira PAT from encrypted credential store."""
    try:
        from services import user_credentials as cred_svc

        store = cred_svc.get_credential_store()
        if store is None:
            return None
        # Try provider IDs in order — server (on-prem), then cloud, then generic
        for provider_id in ("atlassian_server_jira", "jira", "atlassian_rovo_mcp"):
            try:
                if store.has_secret(user_id, provider_id):
                    return _use_secret(store, user_id, provider_id)
            except Exception:
                continue
        return None
    except Exception:
        return None


def _format_profile(profile: dict[str, Any] | None) -> str:
    """Render the cached user profile as a system-prompt section."""
    if not profile:
        return ""
    filled = {
        k: v
        for k, v in profile.items()
        if v and k not in ("favorite_models", "hidden_models", "task_models", "prompts")
    }
    if not filled:
        return ""
    out = "\n\nUser profile:"
    for k, v in filled.items():
        out += f"\n- {k}: {v}"
    return out


def _build_system_prompt(user_id: str) -> str:
    """Build system prompt with program context and user profile."""
    ctx = _get_program_context(user_id)
    base = (
        "You are a PM Fleet agent — an AI project manager assistant. "
        "You help manage software programs by interacting with real tools (Jira, Confluence, Airtable). "
        "You also have profile tools (profile_get/set/delete) and memory tools (memory_add/search/delete/edit). "
        "When the user asks about their work, use the available tools to get real data. "
        "When they share info about themselves — use profile_set for structured facts, memory_add for freeform. "
        "When you need context — use profile_get first. When they correct you — infer and update the profile. "
        "Be concise and actionable. Never say you can't do something if you have a tool for it."
    )
    base += _format_profile(_PROFILE_CACHE.get(user_id))
    if ctx.get("program_name"):
        base += f"\n\nProgram: {ctx['program_name']}"
    if ctx.get("goals"):
        base += f"\nGoals: {', '.join(ctx['goals'])}"
    if ctx.get("tools"):
        base += f"\nTeam tools: {', '.join(ctx['tools'])}"
    if ctx.get("stakeholders"):
        base += f"\nStakeholders: {', '.join(ctx['stakeholders'])}"
    if ctx.get("constraints"):
        base += f"\nConstraints: {', '.join(ctx['constraints'])}"
    if ctx.get("recent_guidance"):
        base += "\n\nRecent PM guidance (use this to shape priorities):"
        for g in ctx["recent_guidance"]:
            base += f"\n- {g}"
    return base


PM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "poll_jira",
            "description": "Get issues assigned to the current user from Jira. Use when they ask about their work, sprint, or tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Max issues to return (default 20)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_jira",
            "description": "Search Jira with a JQL query or text. Use for specific queries like blockers, sprint issues, or project-scoped searches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jql": {
                        "type": "string",
                        "description": "JQL query (e.g. 'status = Blocked AND assignee = currentUser()')",
                    },
                    "text": {
                        "type": "string",
                        "description": "Free text search (alternative to JQL)",
                    },
                    "max_results": {"type": "integer", "description": "Max results (default 20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_issue",
            "description": "Get full details of a specific Jira issue by key (e.g. PROJ-123).",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira issue key like PROJ-123"},
                },
                "required": ["issue_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_blockers",
            "description": "Find blocked or at-risk issues. Use when user asks about blockers, risks, or what's stuck.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "Max results (default 25)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_confluence",
            "description": "Search Confluence for documentation, specs, or meeting notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_as_action",
            "description": "Save the current action as a reusable button on the Program dashboard. Use when the user says 'save that', 'do this again', 'every morning', etc. Pass the capability that was just used (e.g. poll_jira, check_blockers, search_jira, search_confluence, generate_exec_summary).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short name for the button (e.g. 'Morning Standup Poll', 'Blocker Alert')",
                    },
                    "description": {
                        "type": "string",
                        "description": "What this button does when clicked",
                    },
                    "capability": {
                        "type": "string",
                        "description": "The tool to run when clicked: poll_jira, check_blockers, search_jira, search_confluence, or generate_exec_summary",
                    },
                },
                "required": ["name", "capability"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_agent_button",
            "description": "Create a new agent button on the Program dashboard. Use when the user wants to add a new capability, save a workflow as a button, or create a recurring action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Display name (e.g. 'Sprint Check', 'Blocker Alert')",
                    },
                    "description": {"type": "string", "description": "What this agent does"},
                    "capability": {
                        "type": "string",
                        "description": "The tool to run: poll_jira, search_jira, check_blockers, search_confluence",
                    },
                    "payload": {
                        "type": "object",
                        "description": 'Default arguments (e.g. {"jql": "project = MY_PROJECT AND status = Blocked"})',
                    },
                },
                "required": ["name", "capability"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_agent_button",
            "description": "Modify an existing agent button on the Program dashboard. Use when user says 'rename it', 'change the query', 'update the description'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "ID of the agent to modify (use list_agents to find it)",
                    },
                    "name": {"type": "string", "description": "New name (optional)"},
                    "description": {"type": "string", "description": "New description (optional)"},
                    "capability": {"type": "string", "description": "New capability (optional)"},
                    "payload": {
                        "type": "object",
                        "description": "New default arguments (optional)",
                    },
                },
                "required": ["agent_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_agent_button",
            "description": "Remove an agent button from the Program dashboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "ID of the agent to remove"},
                },
                "required": ["agent_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_agent_buttons",
            "description": "List all current agent buttons on the Program dashboard. Use to find IDs for modification.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # ── Memory tools ──
    {
        "type": "function",
        "function": {
            "name": "memory_add",
            "description": "Store a memory/fact. Use when user shares info that doesn't fit a profile field.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact to remember"},
                    "namespace": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Search stored memories.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "namespace": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_delete",
            "description": "Delete a memory by ID.",
            "parameters": {
                "type": "object",
                "properties": {"entry_id": {"type": "string"}},
                "required": ["entry_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_edit",
            "description": "Edit a memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entry_id": {"type": "string"},
                    "value": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["entry_id", "value"],
            },
        },
    },
    # ── Profile tools ──
    {
        "type": "function",
        "function": {
            "name": "profile_get",
            "description": "Get user profile. Check what's known before asking. Returns filled fields + schema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": [
                            "identity",
                            "work_context",
                            "preferences",
                            "goals",
                            "communication",
                        ],
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "profile_set",
            "description": "Set a profile field. Use for structured facts about the user.",
            "parameters": {
                "type": "object",
                "properties": {"field": {"type": "string"}, "value": {"type": "string"}},
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "profile_delete",
            "description": "Remove a profile field.",
            "parameters": {
                "type": "object",
                "properties": {"field": {"type": "string"}},
                "required": ["field"],
            },
        },
    },
    # ── Metrics ──
    {
        "type": "function",
        "function": {
            "name": "query_metrics",
            "description": "Query runtime metrics — latency, tokens, cost, success rate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "time_range": {"type": "string", "enum": ["1h", "24h", "7d", "30d"]},
                },
                "required": [],
            },
        },
    },
    # ── Airtable ──
    {
        "type": "function",
        "function": {
            "name": "airtable_query",
            "description": "Query an Airtable table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_id": {"type": "string"},
                    "table": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "airtable_describe",
            "description": "List tables and fields in an Airtable base.",
            "parameters": {
                "type": "object",
                "properties": {"base_id": {"type": "string"}},
                "required": [],
            },
        },
    },
    # ── Dashboard widgets ──
    {
        "type": "function",
        "function": {
            "name": "create_dashboard_widget",
            "description": "Create a dashboard widget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["kpi", "chart", "list", "table"]},
                    "title": {"type": "string"},
                    "config": {"type": "object"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_widgets",
            "description": "Suggest dashboard widgets based on available data.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_dashboard",
            "description": "Analyze current dashboard for gaps.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── Model curation ──
    {
        "type": "function",
        "function": {
            "name": "favorite_model",
            "description": "Manage model preferences: favorite, hide, or set per-task defaults.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["add", "remove", "hide", "unhide", "set_task"],
                    },
                    "task": {"type": "string", "enum": ["chat", "widget_wizard", "biographer"]},
                },
                "required": ["model", "action"],
            },
        },
    },
]


_JIRA_BASE = os.environ.get("JIRA_SERVER_URL", "")


def _jira_headers(jira_pat: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jira_pat}", "Accept": "application/json"}


async def _tool_poll_jira(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    if not jira_pat:
        return {"error": "No Jira PAT configured. Go to Credentials and add your Jira PAT."}
    if not _JIRA_BASE:
        return {"error": "JIRA_SERVER_URL not configured"}
    import httpx

    max_results = min(args.get("max_results", 10), 15)
    jql = "project = MY_PROJECT AND updated >= -7d ORDER BY updated DESC"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_JIRA_BASE}/rest/api/2/search",
                params={
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": "summary,status,assignee,issuetype,priority,updated",
                },
                headers=_jira_headers(jira_pat),
            )
            r.raise_for_status()
            data = r.json()
            issues = [
                {
                    "key": i.get("key"),
                    "summary": (f := i.get("fields", {})).get("summary"),
                    "status": (f.get("status") or {}).get("name"),
                    "type": (f.get("issuetype") or {}).get("name"),
                    "priority": (f.get("priority") or {}).get("name"),
                    "updated": f.get("updated"),
                }
                for i in data.get("issues", [])
            ]
            return {"total": data.get("total", 0), "issues": issues, "jql": jql}
    except httpx.HTTPStatusError as e:
        return {"error": f"Jira returned {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Jira connection failed: {e}"}


async def _tool_search_jira(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    if not jira_pat:
        return {"error": "No Jira PAT configured."}
    if not _JIRA_BASE:
        return {"error": "JIRA_SERVER_URL not configured"}
    import httpx

    jql = args.get("jql") or ""
    text = args.get("text") or ""
    if not jql and text:
        jql = f'text ~ "{text}" ORDER BY updated DESC'
    if not jql:
        return {"error": "Provide 'jql' or 'text' to search"}
    max_results = min(args.get("max_results", 10), 15)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_JIRA_BASE}/rest/api/2/search",
                params={
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": "summary,status,assignee,issuetype,priority,updated",
                },
                headers=_jira_headers(jira_pat),
            )
            r.raise_for_status()
            data = r.json()
            issues = [
                {
                    "key": i.get("key"),
                    "summary": (f := i.get("fields", {})).get("summary"),
                    "status": (f.get("status") or {}).get("name"),
                    "type": (f.get("issuetype") or {}).get("name"),
                    "assignee": ((f.get("assignee") or {}).get("displayName")),
                    "updated": f.get("updated"),
                }
                for i in data.get("issues", [])
            ]
            return {"total": data.get("total", 0), "issues": issues, "jql": jql}
    except httpx.HTTPStatusError as e:
        return {"error": f"Jira returned {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Jira search failed: {e}"}


async def _tool_get_issue(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    if not jira_pat:
        return {"error": "No Jira PAT configured."}
    if not _JIRA_BASE:
        return {"error": "JIRA_SERVER_URL not configured"}
    import httpx

    issue_key = args.get("issue_key") or args.get("key") or ""
    if not issue_key:
        return {"error": "issue_key is required"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_JIRA_BASE}/rest/api/2/issue/{issue_key}",
                headers=_jira_headers(jira_pat),
            )
            r.raise_for_status()
            data = r.json()
            f = data.get("fields", {})
            return {
                "key": data.get("key"),
                "summary": f.get("summary"),
                "status": (f.get("status") or {}).get("name"),
                "assignee": ((f.get("assignee") or {}).get("displayName")),
                "type": (f.get("issuetype") or {}).get("name"),
                "priority": (f.get("priority") or {}).get("name"),
                "description": (f.get("description") or "")[:2000],
                "labels": f.get("labels", []),
                "created": f.get("created"),
                "updated": f.get("updated"),
            }
    except httpx.HTTPStatusError as e:
        return {"error": f"Jira returned {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Get issue failed: {e}"}


async def _tool_generate_exec_summary(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    # Chain: pull Jira state + blockers, format as text for LLM
    jira_state = await _execute_tool("poll_jira", {"max_results": 10}, user_id)
    blockers = await _execute_tool("check_blockers", {}, user_id)
    # Format as readable text so LLM doesn't try to call more tools
    lines = [f"Sprint: {jira_state.get('total', 0)} active issues"]
    for i in (jira_state.get("issues") or [])[:5]:
        lines.append(f"  • {i.get('key')} [{i.get('status')}] {i.get('summary')}")
    lines.append(f"\nBlockers: {blockers.get('total', 0)}")
    for i in (blockers.get("issues") or [])[:5]:
        lines.append(f"  ⚠ {i.get('key')} [{i.get('status')}] {i.get('summary')}")
    return {
        "summary": "\n".join(lines),
        "sprint_total": jira_state.get("total", 0),
        "blockers_total": blockers.get("total", 0),
    }


async def _tool_check_blockers(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    if not jira_pat:
        return {"error": "No Jira PAT configured."}
    if not _JIRA_BASE:
        return {"error": "JIRA_SERVER_URL not configured"}
    import httpx

    jql = (
        "project = MY_PROJECT AND resolution = Unresolved AND "
        "(status = Blocked OR flagged is not EMPTY) ORDER BY priority DESC"
    )
    max_results = min(args.get("max_results", 10), 15)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_JIRA_BASE}/rest/api/2/search",
                params={
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": "summary,status,assignee,issuetype,priority,flagged",
                },
                headers=_jira_headers(jira_pat),
            )
            r.raise_for_status()
            data = r.json()
            issues = [
                {
                    "key": i.get("key"),
                    "summary": (f := i.get("fields", {})).get("summary"),
                    "status": (f.get("status") or {}).get("name"),
                    "priority": (f.get("priority") or {}).get("name"),
                }
                for i in data.get("issues", [])
            ]
            return {"total": data.get("total", 0), "issues": issues, "jql": jql}
    except httpx.HTTPStatusError as e:
        # Fallback JQL if the flagged field doesn't exist
        if e.response.status_code == 400:
            return await _execute_tool(
                "search_jira",
                {"jql": "assignee = currentUser() AND status = Blocked ORDER BY updated DESC"},
                user_id,
            )
        return {"error": f"Blocker check failed: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Blocker check failed: {e}"}


def _get_confluence_pat(user_id: str) -> str | None:
    try:
        from services import user_credentials as cred_svc

        store = cred_svc.get_credential_store()
        if not store:
            return None
        for pid in ("atlassian_server_confluence", "confluence"):
            try:
                if store.has_secret(user_id, pid):
                    return _use_secret(store, user_id, pid)
            except Exception:
                continue
    except Exception:
        return None
    return None


async def _tool_search_confluence(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    confluence_pat = _get_confluence_pat(user_id)
    if not confluence_pat:
        return {"error": "No Confluence PAT configured."}
    query = args.get("query", "")
    if not query:
        return {"error": "query is required"}
    import httpx

    confluence_base = os.environ.get("CONFLUENCE_SERVER_URL", "")
    if not confluence_base:
        return {"error": "CONFLUENCE_SERVER_URL not configured"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{confluence_base}/rest/api/content/search",
                params={"cql": f'text ~ "{query}"', "limit": args.get("max_results", 10)},
                headers={"Authorization": f"Bearer {confluence_pat}", "Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
            results = [
                {
                    "title": p.get("title"),
                    "id": p.get("id"),
                    "type": p.get("type"),
                    "url": p.get("_links", {}).get("webui"),
                }
                for p in data.get("results", [])
            ]
            return {"total": data.get("size", 0), "results": results}
    except Exception as e:
        return {"error": f"Confluence search failed: {e}"}


async def _tool_save_as_action(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    # Save as a real agent button on the Program page
    from datetime import UTC, datetime
    from uuid import uuid4

    import stores
    from models.schemas import Agent as AgentModel

    agent_id = str(uuid4())[:8]
    name = args.get("name", "Saved Action")
    # Infer capability from conversation context
    capability = args.get("capability", "poll_jira")
    stores.agents[agent_id] = AgentModel(
        id=agent_id,
        name=name,
        description=args.get("description", "Saved from chat"),
        status="idle",
        model="gemini-3.5-flash",
        capabilities=[capability],
        primary_capability=capability,
        primary_action_label=name,
        created_at=datetime.now(UTC),
        config={},
    )
    return {"saved": True, "agent_id": agent_id, "name": name}


async def _tool_create_agent_button(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    from datetime import UTC, datetime
    from uuid import uuid4

    import stores
    from models.schemas import Agent as AgentModel

    agent_id = str(uuid4())[:8]
    capability = args.get("capability", "poll_jira")
    agent = AgentModel(
        id=agent_id,
        name=args.get("name", "New Agent"),
        description=args.get("description", ""),
        status="idle",
        model="gemini-3.5-flash",
        capabilities=[capability],
        primary_capability=capability,
        primary_action_label=args.get("name", "Run"),
        created_at=datetime.now(UTC),
        config={"default_payload": args.get("payload", {})},
    )
    stores.agents[agent_id] = agent
    return {
        "created": True,
        "agent": {"id": agent_id, "name": agent.name, "capability": capability},
    }


async def _tool_modify_agent_button(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    import stores

    agent_id = args.get("agent_id", "")
    if agent_id not in stores.agents:
        return {
            "error": f"Agent '{agent_id}' not found. Use list_agent_buttons to see available IDs."
        }
    agent = stores.agents[agent_id]
    updates = {}
    if args.get("name"):
        updates["name"] = args["name"]
    if args.get("description"):
        updates["description"] = args["description"]
    if args.get("capability"):
        updates["capabilities"] = [args["capability"]]
        updates["primary_capability"] = args["capability"]
    if hasattr(agent, "model_copy"):
        agent = agent.model_copy(update=updates)
    else:
        for k, v in updates.items():
            if isinstance(agent, dict):
                agent[k] = v
    stores.agents[agent_id] = agent
    return {"modified": True, "agent_id": agent_id, "updates": updates}


async def _tool_remove_agent_button(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    import stores

    agent_id = args.get("agent_id", "")
    if agent_id not in stores.agents:
        return {"error": f"Agent '{agent_id}' not found."}
    removed = stores.agents.pop(agent_id)
    return {"removed": True, "agent_id": agent_id, "name": removed.get("name", "")}


async def _tool_list_agent_buttons(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    import stores

    agents = []
    for aid, a in stores.agents.items():
        if isinstance(a, dict):
            agents.append(
                {"id": aid, "name": a.get("name"), "capabilities": a.get("capabilities", [])}
            )
        else:
            agents.append(
                {
                    "id": aid,
                    "name": getattr(a, "name", "?"),
                    "capabilities": getattr(a, "capabilities", []),
                }
            )
    return {"agents": agents}


# Tool name (and aliases) → handler. Unknown tools fall back to poll_jira.
_TOOL_HANDLERS: dict[str, Any] = {
    "poll_jira": _tool_poll_jira,
    "fetch_program_state": _tool_poll_jira,
    "search_jira": _tool_search_jira,
    "get_issue": _tool_get_issue,
    "get_jira_issue": _tool_get_issue,
    "generate_exec_summary": _tool_generate_exec_summary,
    "check_blockers": _tool_check_blockers,
    "detect_blockers": _tool_check_blockers,
    "scan_risks": _tool_check_blockers,
    "search_confluence": _tool_search_confluence,
    "save_as_action": _tool_save_as_action,
    "create_agent_button": _tool_create_agent_button,
    "modify_agent_button": _tool_modify_agent_button,
    "remove_agent_button": _tool_remove_agent_button,
    "list_agent_buttons": _tool_list_agent_buttons,
}

# ── Memory tools ──


async def _tool_memory_add(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    from datetime import UTC, datetime
    from uuid import uuid4

    from models.schemas import MemoryEntry

    content = args.get("content", "")
    if not content:
        return {"error": "content is required"}
    eid = str(uuid4())
    t = datetime.now(UTC)
    entry = MemoryEntry(
        id=eid,
        user_id=user_id,
        key=content[:60],
        value=content,
        namespace=args.get("namespace", "general"),
        tags=args.get("tags", []),
        embedding=None,
        created_at=t,
        updated_at=t,
    )
    import stores

    stores.memory_entries[eid] = entry
    return {"saved": True, "id": eid, "content": content}


async def _tool_memory_search(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    import stores

    query = args.get("query", "").lower()
    entries = [e for e in stores.memory_entries.values() if e.user_id == user_id]
    if query:
        entries = [
            e
            for e in entries
            if query in e.value.lower()
            or query in e.key.lower()
            or query in " ".join(e.tags).lower()
        ]
    return {
        "results": [
            {"id": e.id, "key": e.key, "value": e.value, "namespace": e.namespace, "tags": e.tags}
            for e in entries[:10]
        ],
        "count": len(entries),
    }


async def _tool_memory_delete(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    import stores

    entry_id = args.get("entry_id", "")
    if not entry_id:
        return {"error": "entry_id required"}
    if entry_id in stores.memory_entries and stores.memory_entries[entry_id].user_id == user_id:
        del stores.memory_entries[entry_id]
        return {"deleted": True, "id": entry_id}
    return {"error": "not found"}


async def _tool_memory_edit(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    from datetime import UTC, datetime

    import stores

    entry_id = args.get("entry_id", "")
    value = args.get("value", "")
    if not entry_id or not value:
        return {"error": "entry_id and value required"}
    if entry_id not in stores.memory_entries or stores.memory_entries[entry_id].user_id != user_id:
        return {"error": "not found"}
    entry = stores.memory_entries[entry_id]
    entry.value = value
    entry.key = value[:60]
    entry.updated_at = datetime.now(UTC)
    if "tags" in args:
        entry.tags = args["tags"]
    return {"updated": True, "id": entry_id, "value": value}


# ── Profile tools ──

PROFILE_SCHEMA = {
    "identity": ["name", "role", "team", "department", "location", "timezone"],
    "work_context": [
        "projects",
        "tools",
        "languages",
        "platforms",
        "recurring_tasks",
        "stakeholders",
    ],
    "preferences": [
        "response_style",
        "interaction_style",
        "model_preferences",
        "topics_to_avoid",
        "assumptions_to_avoid",
    ],
    "goals": ["current_focus", "okrs", "blockers", "definition_of_done"],
    "communication": ["challenge_style", "presentation_format", "terminology"],
}

_PROFILE_CACHE: dict[str, dict] = {}


async def hydrate_profile_cache(user_id: str) -> None:
    """Load profile into cache. Uses pg_store if available, else local cache."""
    if user_id in _PROFILE_CACHE:
        return
    try:
        from services.pg_store import pg_get

        rows = await pg_get("user_profiles", {"id": f"eq.{user_id}"})
        _PROFILE_CACHE[user_id] = (rows[0] if rows else {}).get("preferences", {})
    except Exception:
        _PROFILE_CACHE.setdefault(user_id, {})


async def _tool_profile_get(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    await hydrate_profile_cache(user_id)
    profile = _PROFILE_CACHE.get(user_id, {})
    section = args.get("section")
    if section and section in PROFILE_SCHEMA:
        return {
            "section": section,
            "fields": {k: profile.get(k) for k in PROFILE_SCHEMA[section] if profile.get(k)},
        }
    return {"profile": {k: v for k, v in profile.items() if v}, "schema": PROFILE_SCHEMA}


async def _tool_profile_set(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    await hydrate_profile_cache(user_id)
    profile = _PROFILE_CACHE.get(user_id, {})
    field = args.get("field", "")
    value = args.get("value", "")
    if not field or not value:
        return {"error": "field and value required"}
    profile[field] = value
    _PROFILE_CACHE[user_id] = profile
    try:
        from services.pg_store import pg_upsert

        await pg_upsert("user_profiles", {"id": user_id, "preferences": profile})
    except Exception:
        pass
    return {"updated": True, "field": field, "value": value}


async def _tool_profile_delete(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    await hydrate_profile_cache(user_id)
    profile = _PROFILE_CACHE.get(user_id, {})
    field = args.get("field", "")
    if not field:
        return {"error": "field required"}
    removed = profile.pop(field, None)
    if removed is None:
        return {"error": f"field '{field}' not found"}
    _PROFILE_CACHE[user_id] = profile
    try:
        from services.pg_store import pg_upsert

        await pg_upsert("user_profiles", {"id": user_id, "preferences": profile})
    except Exception:
        pass
    return {"deleted": True, "field": field}


# ── Metrics tools ──


async def _tool_query_metrics(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    """Query runtime metrics — latency, tokens, cost, success rate."""
    from services.node_metrics_store import get_metrics_summary

    try:
        return get_metrics_summary(args.get("node_id"), args.get("time_range", "7d"))
    except Exception:
        return {"error": "metrics unavailable"}


# ── Airtable tools ──


async def _tool_airtable_query(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    """Query an Airtable base/table."""
    import os

    base_id = args.get("base_id", os.environ.get("AIRTABLE_BASE_ID", ""))
    table = args.get("table", "")
    if not base_id or not table:
        return {"error": "base_id and table required"}
    pat = os.environ.get("AIRTABLE_PAT", "")
    if not pat:
        return {"error": "AIRTABLE_PAT not configured"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"https://api.airtable.com/v0/{base_id}/{table}",
                headers={"Authorization": f"Bearer {pat}"},
                params={"maxRecords": str(args.get("limit", 20))},
            )
            r.raise_for_status()
            records = r.json().get("records", [])
            return {"records": [rec.get("fields", {}) for rec in records], "count": len(records)}
    except Exception as e:
        return {"error": str(e)[:100]}


async def _tool_airtable_describe(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    """Describe tables in an Airtable base."""
    import os

    base_id = args.get("base_id", os.environ.get("AIRTABLE_BASE_ID", ""))
    pat = os.environ.get("AIRTABLE_PAT", "")
    if not base_id or not pat:
        return {"error": "base_id and AIRTABLE_PAT required"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
                headers={"Authorization": f"Bearer {pat}"},
            )
            r.raise_for_status()
            tables = r.json().get("tables", [])
            return {
                "tables": [
                    {"name": t["name"], "fields": [f["name"] for f in t.get("fields", [])]}
                    for t in tables
                ]
            }
    except Exception as e:
        return {"error": str(e)[:100]}


# ── Dashboard widget tools ──


async def _tool_create_dashboard_widget(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    """Create a dashboard widget."""
    from uuid import uuid4

    widget = {
        "id": str(uuid4()),
        "type": args.get("type", "kpi"),
        "title": args.get("title", "Widget"),
        "config": args.get("config", {}),
        "created_by": user_id,
    }
    import stores

    if not hasattr(stores, "widgets"):
        stores.widgets = {}
    stores.widgets[widget["id"]] = widget
    return {"created": True, "widget_id": widget["id"], "title": widget["title"]}


async def _tool_suggest_widgets(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    """Suggest widgets based on available data."""
    return {
        "suggestions": [
            {"type": "kpi", "title": "Open Issues", "data_source": "jira"},
            {"type": "chart", "title": "Sprint Burndown", "data_source": "jira"},
            {"type": "list", "title": "Recent Confluence Updates", "data_source": "confluence"},
            {"type": "kpi", "title": "Blocked Items", "data_source": "jira"},
        ]
    }


async def _tool_analyze_dashboard(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    """Analyze current dashboard for gaps."""
    import stores

    widgets = list(getattr(stores, "widgets", {}).values())
    return {
        "widget_count": len(widgets),
        "types": list({w.get("type") for w in widgets}),
        "suggestion": "Consider adding a blocker tracker"
        if len(widgets) < 3
        else "Dashboard looks solid",
    }


# ── Model curation ──


async def _tool_favorite_model(
    args: dict[str, Any], user_id: str, jira_pat: str | None
) -> dict[str, Any]:
    """Manage model preferences: favorite, hide, or set per-task defaults."""
    await hydrate_profile_cache(user_id)
    profile = _PROFILE_CACHE.get(user_id, {})
    model = args.get("model", "")
    action = args.get("action", "add")
    task = args.get("task", "")
    if not model:
        return {"error": "model required"}
    favorites = profile.get("favorite_models", [])
    hidden = profile.get("hidden_models", [])
    task_models = profile.get("task_models", {})
    if action == "add" and model not in favorites:
        favorites.append(model)
    elif action == "remove" and model in favorites:
        favorites.remove(model)
    elif action == "hide" and model not in hidden:
        hidden.append(model)
    elif action == "unhide" and model in hidden:
        hidden.remove(model)
    elif action == "set_task" and task:
        task_models[task] = model
    profile["favorite_models"] = favorites
    profile["hidden_models"] = hidden
    profile["task_models"] = task_models
    _PROFILE_CACHE[user_id] = profile
    try:
        from services.pg_store import pg_upsert

        await pg_upsert("user_profiles", {"id": user_id, "preferences": profile})
    except Exception:
        pass
    return {"updated": True, "favorites": favorites, "hidden": hidden, "task_models": task_models}


# ── Tool scoping ──

TOOL_SCOPES: dict[str, list[str] | None] = {
    "memory": [
        "memory_add",
        "memory_search",
        "memory_delete",
        "memory_edit",
        "profile_get",
        "profile_set",
        "profile_delete",
        "favorite_model",
    ],
    "dashboard_view": [
        "poll_jira",
        "search_jira",
        "check_blockers",
        "search_confluence",
        "airtable_query",
        "query_metrics",
        "memory_search",
        "profile_get",
    ],
    "dashboard_edit": [
        "poll_jira",
        "search_jira",
        "check_blockers",
        "search_confluence",
        "airtable_query",
        "query_metrics",
        "memory_search",
        "profile_get",
        "create_dashboard_widget",
        "suggest_widgets",
        "analyze_dashboard",
    ],
    "chat": None,
}


def get_scoped_tools(scope: str | None) -> list[dict]:
    """Return tool definitions filtered by scope. None = all tools."""
    if scope is None or scope == "chat":
        return PM_TOOLS
    allowed = TOOL_SCOPES.get(scope)
    if allowed is None:
        return PM_TOOLS
    return [t for t in PM_TOOLS if t.get("function", {}).get("name") in allowed]


_TOOL_HANDLERS.update(
    {
        "memory_add": _tool_memory_add,
        "memory_search": _tool_memory_search,
        "memory_delete": _tool_memory_delete,
        "memory_edit": _tool_memory_edit,
        "profile_get": _tool_profile_get,
        "profile_set": _tool_profile_set,
        "profile_delete": _tool_profile_delete,
        "query_metrics": _tool_query_metrics,
        "airtable_query": _tool_airtable_query,
        "airtable_describe": _tool_airtable_describe,
        "create_dashboard_widget": _tool_create_dashboard_widget,
        "suggest_widgets": _tool_suggest_widgets,
        "analyze_dashboard": _tool_analyze_dashboard,
        "favorite_model": _tool_favorite_model,
    }
)

# Substrate tools — domain-agnostic DAG execution, eval, hill-climb
from services.substrate_tools import SUBSTRATE_TOOL_HANDLERS  # noqa: E402

_TOOL_HANDLERS.update(SUBSTRATE_TOOL_HANDLERS)


async def _execute_tool(tool_name: str, args: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Execute a PM tool for real. No stubs. Calls Jira REST API directly."""
    jira_pat = _get_jira_pat(user_id)
    handler = _TOOL_HANDLERS.get(tool_name, _tool_poll_jira)
    return await handler(args, user_id, jira_pat)


async def run_chat_completion(
    req: ChatCompletionRequest,
    user_id: str = "",
    _llm: LLMPort | None = None,
) -> dict[str, Any]:
    """PM Fleet chat — real tools, real data, real LLM synthesis."""
    s = get_settings()
    model = req.model or os.environ.get("CHAT_DEFAULT_MODEL") or s.chat_default_model
    llm = _llm or build_llm_port()

    # Build messages with PM system prompt
    messages: list[dict[str, Any]] = list(req.messages)
    if not any(m.get("role") == "system" for m in messages):
        await hydrate_profile_cache(user_id)
        system_prompt = _build_system_prompt(user_id)
        messages.insert(0, {"role": "system", "content": system_prompt})

    # Tool-use loop (max 5 iterations)
    for _ in range(5):
        tool_req = ChatCompletionRequest(
            messages=messages,
            model=model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            tools=get_scoped_tools(getattr(req, "tools_scope", None)),
        )
        out = await llm.complete(tool_req)

        choice = (out.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls")

        if not tool_calls:
            # Ensure content exists before returning
            content = msg.get("content")
            if not content:
                out["choices"][0]["message"]["content"] = "(Processing complete)"
            return out

        # Execute tool calls
        messages.append(
            {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
        )
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            logger.info("tool_call name=%s args=%s user=%s", name, args, user_id)
            result = await _execute_tool(name, args, user_id)
            logger.info(
                "tool_result name=%s keys=%s",
                name,
                list(result.keys()) if isinstance(result, dict) else "?",
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result),
                }
            )

    # Final synthesis after tool loop exhausted — call WITHOUT tools to force content
    final_req = ChatCompletionRequest(messages=messages, model=model, temperature=req.temperature)
    final_out = await llm.complete(final_req)
    # Ensure we never return raw tool_calls to the frontend
    choice = (final_out.get("choices") or [{}])[0]
    content = choice.get("message", {}).get("content")
    if not content:
        synth = _synthesize_fallback_content(messages)
        final_out = {
            "choices": [{"message": {"role": "assistant", "content": synth}}],
            "model": model,
        }
    return final_out


def _synthesize_fallback_content(messages: list[dict[str, Any]]) -> str:
    """Format the most recent tool results as readable bullet points for the user."""
    tool_results = [m.get("content", "") for m in messages if m.get("role") == "tool"]
    lines: list[str] = []
    for tr in tool_results[-2:]:
        try:
            d = json.loads(tr)
        except Exception:
            continue
        for issue in (d.get("issues") or [])[:10]:
            lines.append(f"• **{issue.get('key')}** [{issue.get('status')}] {issue.get('summary')}")
        total = d.get("total", 0)
        if total:
            lines.insert(0, f"**{total} issues** (showing first {min(total, 10)})\n")

    if not lines:
        return (
            "Request completed but no summary was generated. Try asking a more specific question."
        )
    content = "\n".join(lines)
    content += (
        "\n\n---\n**Summary:** "
        + f"{len(lines) - 1} issues shown. Use chat to drill into specific items "
        "or ask follow-up questions."
    )
    return content


async def run_chat_completion_streaming(
    req: ChatCompletionRequest,
    user_id: str = "",
):
    """Streaming version — yields SSE events with real status updates."""
    import os

    s = get_settings()
    model = req.model or os.environ.get("CHAT_DEFAULT_MODEL") or s.chat_default_model
    llm = build_llm_port()

    messages: list[dict[str, Any]] = list(req.messages)
    if not any(m.get("role") == "system" for m in messages):
        await hydrate_profile_cache(user_id)
        system_prompt = _build_system_prompt(user_id)
        messages.insert(0, {"role": "system", "content": system_prompt})

    for iteration in range(5):
        yield {
            "type": "status",
            "message": "Sending to LLM…" if iteration == 0 else "Processing tool results…",
        }

        tool_req = ChatCompletionRequest(
            messages=messages,
            model=model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            tools=get_scoped_tools(getattr(req, "tools_scope", None)),
        )
        out = await llm.complete(tool_req)

        choice = (out.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls")

        if not tool_calls:
            content = msg.get("content", "")
            yield {"type": "done", "content": content, "model": model}
            return

        messages.append(
            {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
        )

        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            yield {"type": "tool_call", "tool": name, "args": args}
            result = await _execute_tool(name, args, user_id)
            yield {"type": "tool_result", "tool": name, "summary": _summarize_result(result)}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result),
                }
            )

    # Final synthesis
    yield {"type": "status", "message": "Finalizing…"}
    final_req = ChatCompletionRequest(messages=messages, model=model, temperature=req.temperature)
    final_out = await llm.complete(final_req)
    content = (final_out.get("choices") or [{}])[0].get("message", {}).get("content", "")
    yield {"type": "done", "content": content, "model": model}


def _summarize_result(result: dict[str, Any]) -> str:
    """Short summary of a tool result for the status stream."""
    if "error" in result:
        return f"Error: {result['error'][:80]}"
    if "issues" in result:
        return f"Got {result.get('total', len(result['issues']))} issues"
    if "results" in result:
        return f"Got {result.get('total', len(result['results']))} results"
    if "created" in result:
        return "Created"
    if "saved" in result:
        return "Saved"
    return "Done"
