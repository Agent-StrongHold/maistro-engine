"""PM Fleet chat completion — real PM agent with real tools.

This is not a generic chatbot. It knows your program, has access to your
Jira/Confluence via stored credentials, and can take real actions.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from adapters.llm_http import HttpOpenAIProtocolLLM, StubLLMPort
from config import get_settings
from models.schemas import ChatCompletionRequest
from protocols.llm import LLMPort

logger = logging.getLogger("hive.chat")


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
                    return store.use_secret(user_id, provider_id, lambda s: s)
            except Exception:
                continue
        return None
    except Exception:
        return None


def _build_system_prompt(user_id: str) -> str:
    """Build a PM-specific system prompt with program context."""
    ctx = _get_program_context(user_id)
    base = (
        "You are a PM Fleet agent — an AI project manager assistant. "
        "You help manage software programs by interacting with real tools (Jira, Confluence). "
        "When the user asks about their work, use the available tools to get real data. "
        "Be concise and actionable. Format Jira issues as bullet lists with keys and status. "
        "Never say you can't access Jira — use the poll_jira or search_jira tools. "
        "After completing an action, ask if they'd like to save it as a recurring action."
    )
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
]


async def _execute_tool(tool_name: str, args: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Execute a PM tool for real. No stubs. Calls Jira REST API directly."""
    import httpx

    jira_pat = _get_jira_pat(user_id)
    jira_base = "https://jira.example.com"

    if tool_name in ("poll_jira", "fetch_program_state"):
        if not jira_pat:
            return {
                "error": "No Jira PAT configured. Go to Credentials and add your Jira PAT."
            }
        max_results = min(args.get("max_results", 10), 15)
        jql = "project = MY_PROJECT AND updated >= -7d ORDER BY updated DESC"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{jira_base}/rest/api/2/search",
                    params={
                        "jql": jql,
                        "maxResults": max_results,
                        "fields": "summary,status,assignee,issuetype,priority,updated",
                    },
                    headers={"Authorization": f"Bearer {jira_pat}", "Accept": "application/json"},
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
                            "type": (f.get("issuetype") or {}).get("name"),
                            "priority": (f.get("priority") or {}).get("name"),
                            "updated": f.get("updated"),
                        }
                    )
                return {"total": data.get("total", 0), "issues": issues, "jql": jql}
        except httpx.HTTPStatusError as e:
            return {"error": f"Jira returned {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            return {"error": f"Jira connection failed: {e}"}

    elif tool_name == "search_jira":
        if not jira_pat:
            return {"error": "No Jira PAT configured."}
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
                    f"{jira_base}/rest/api/2/search",
                    params={
                        "jql": jql,
                        "maxResults": max_results,
                        "fields": "summary,status,assignee,issuetype,priority,updated",
                    },
                    headers={"Authorization": f"Bearer {jira_pat}", "Accept": "application/json"},
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
                            "type": (f.get("issuetype") or {}).get("name"),
                            "assignee": ((f.get("assignee") or {}).get("displayName")),
                            "updated": f.get("updated"),
                        }
                    )
                return {"total": data.get("total", 0), "issues": issues, "jql": jql}
        except httpx.HTTPStatusError as e:
            return {"error": f"Jira returned {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            return {"error": f"Jira search failed: {e}"}

    elif tool_name in ("get_issue", "get_jira_issue"):
        if not jira_pat:
            return {"error": "No Jira PAT configured."}
        issue_key = args.get("issue_key") or args.get("key") or ""
        if not issue_key:
            return {"error": "issue_key is required"}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{jira_base}/rest/api/2/issue/{issue_key}",
                    headers={"Authorization": f"Bearer {jira_pat}", "Accept": "application/json"},
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

    elif tool_name == "generate_exec_summary":
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

    elif tool_name in ("check_blockers", "detect_blockers", "scan_risks"):
        if not jira_pat:
            return {"error": "No Jira PAT configured."}
        jql = "project = MY_PROJECT AND resolution = Unresolved AND (status = Blocked OR flagged is not EMPTY) ORDER BY priority DESC"
        max_results = min(args.get("max_results", 10), 15)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{jira_base}/rest/api/2/search",
                    params={
                        "jql": jql,
                        "maxResults": max_results,
                        "fields": "summary,status,assignee,issuetype,priority,flagged",
                    },
                    headers={"Authorization": f"Bearer {jira_pat}", "Accept": "application/json"},
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
                            "priority": (f.get("priority") or {}).get("name"),
                        }
                    )
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

    elif tool_name == "search_confluence":
        # Use on-prem Jira Server Confluence PAT
        confluence_pat = None
        try:
            from services import user_credentials as cred_svc

            store = cred_svc.get_credential_store()
            if store:
                for pid in ("atlassian_server_confluence", "confluence"):
                    try:
                        if store.has_secret(user_id, pid):
                            confluence_pat = store.use_secret(user_id, pid, lambda s: s)
                            break
                    except Exception:
                        continue
        except Exception:
            pass
        if not confluence_pat:
            return {"error": "No Confluence PAT configured."}
        query = args.get("query", "")
        if not query:
            return {"error": "query is required"}
        confluence_base = "https://wiki.example.com"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{confluence_base}/rest/api/content/search",
                    params={"cql": f'text ~ "{query}"', "limit": args.get("max_results", 10)},
                    headers={
                        "Authorization": f"Bearer {confluence_pat}",
                        "Accept": "application/json",
                    },
                )
                r.raise_for_status()
                data = r.json()
                results = []
                for p in data.get("results", []):
                    results.append(
                        {
                            "title": p.get("title"),
                            "id": p.get("id"),
                            "type": p.get("type"),
                            "url": p.get("_links", {}).get("webui"),
                        }
                    )
                return {"total": data.get("size", 0), "results": results}
        except Exception as e:
            return {"error": f"Confluence search failed: {e}"}

    elif tool_name == "save_as_action":
        # Save as a real agent button on the Program page
        from datetime import UTC, datetime
        from uuid import uuid4

        import stores
        from models.schemas import Agent as AgentModel

        agent_id = str(uuid4())[:8]
        name = args.get("name", "Saved Action")
        # Infer capability from conversation context
        capability = args.get("capability", "poll_jira")
        agent = AgentModel(
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
        stores.agents[agent_id] = agent
        return {"saved": True, "agent_id": agent_id, "name": name}

    elif tool_name == "create_agent_button":
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

    elif tool_name == "modify_agent_button":
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

    elif tool_name == "remove_agent_button":
        import stores

        agent_id = args.get("agent_id", "")
        if agent_id not in stores.agents:
            return {"error": f"Agent '{agent_id}' not found."}
        removed = stores.agents.pop(agent_id)
        return {"removed": True, "agent_id": agent_id, "name": removed.get("name", "")}

    elif tool_name == "list_agent_buttons":
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

    return await _execute_tool(
        "poll_jira", args, user_id
    )  # fallback: unknown tools default to poll_jira


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
        system_prompt = _build_system_prompt(user_id)
        messages.insert(0, {"role": "system", "content": system_prompt})

    # Tool-use loop (max 5 iterations)
    for _ in range(5):
        tool_req = ChatCompletionRequest(
            messages=messages,
            model=model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            tools=PM_TOOLS,
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
        # Format tool results as readable bullet points
        import json as _json

        tool_results = [m.get("content", "") for m in messages if m.get("role") == "tool"]
        lines = []
        for tr in tool_results[-2:]:
            try:
                d = _json.loads(tr)
                for issue in (d.get("issues") or [])[:10]:
                    lines.append(
                        f"• **{issue.get('key')}** [{issue.get('status')}] {issue.get('summary')}"
                    )
                total = d.get("total", 0)
                if total:
                    lines.insert(0, f"**{total} issues** (showing first {min(total, 10)})\n")
            except Exception:
                pass
        content = (
            "\n".join(lines)
            if lines
            else "Request completed but no summary was generated. Try asking a more specific question."
        )
        if lines:
            content += (
                "\n\n---\n**Summary:** "
                + f"{len(lines) - 1} issues shown. Use chat to drill into specific items or ask follow-up questions."
            )
        final_out = {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "model": model,
        }
    return final_out


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
            tools=PM_TOOLS,
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
