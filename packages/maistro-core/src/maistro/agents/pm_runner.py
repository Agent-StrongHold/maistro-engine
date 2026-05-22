"""PM fleet task executor — real LLM calls via the JedAI gateway (v0).

Replaces the stub-only POC dispatch. Each PM capability invocation maps
to a single Claude call through the JedAI gateway. The agent's persona
prompt + per-capability prompt template produce a PMRoleOutput JSON,
which is wrapped in ConductorOutput so the Hive backend contract stays
intact.

The DAG composition (intake → program_manager → fan-out → reporting)
lives at the program_hyperagent level — `run_program_pulse()` in
hive-conductor invokes `run_pm_task()` per node and propagates outputs
through the GraphBlackboard. v0.5 lifts to `maistro.graph.run_graph()`
for self-optimizing cycles + beam search.

Rollback path: `MAISTRO_PM_USE_STUBS=true` env var reverts to the
legacy `_run_stub()` dispatch in `tools.pm_stubs`.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import structlog

from maistro.agents.pm_capabilities import is_gated, normalize_capability
from maistro.agents.pm_fleet import get_pm_def
from maistro.agents.pm_llm_call import jedai_llm_call
from maistro.agents.types import ConductorOutput, PlanOutput, SubTask
from maistro.graph.pm_domain import (
    PM_PRIMARY_CAPABILITY,
    build_capability_prompt,
)
from maistro.graph.types import (
    DEFAULT_SYSTEM_PROMPTS,
    JSON_OUTPUT_SCHEMAS,
    AgentRole,
    PMRoleOutput,
)
from maistro.tasks.models import TaskCreate
from maistro.tools.atlassian import AtlassianMCPClient, AtlassianMCPError
from maistro.tools.browser import BrowserClient, BrowserToolError

_log = logging.getLogger("hive.engine.pm")
logger = structlog.get_logger()
_CAPABILITY_RE = re.compile(r"\]\s+(\w+):\s")

# Mapping pm_fleet agent names → graph AgentRole enum values.
_PM_AGENT_TO_ROLE: dict[str, AgentRole] = {
    "intake": AgentRole.INTAKE,
    "program_manager": AgentRole.PROGRAM_MANAGER,
    "research": AgentRole.RESEARCH,
    "delivery": AgentRole.DELIVERY,
    "risk_dependency": AgentRole.RISK_DEPENDENCY,
    "reporting": AgentRole.REPORTING,
}

# Capabilities whose data inputs live in an external system we may not
# have wired yet. They short-circuit with source="no_data" before the
# LLM is called. v0 Day 3 wires Atlassian (poll_jira, detect_blockers,
# parts of fetch_program_state) — those moved to _JIRA_DRIVEN_CAPABILITIES
# below. Airtable + GitHub remain no-data until later wiring.
_NO_DATA_WITHOUT_TOOLS: set[str] = {
    "sync_jira",
    "create_jira_ticket",
    "create_subtask",
    "poll_airtable",
    "fetch_program_metrics",
    "fetch_dependency_graph",
    "publish_dashboard",
}

# Capabilities that drive a Jira/Confluence MCP tool call BEFORE the LLM,
# then feed the real data into the LLM context for synthesis. PATs come
# from task.program_context["atlassian_pats"] populated by Hive from the
# encrypted credential store. Never read PATs from env.
_JIRA_DRIVEN_CAPABILITIES: set[str] = {
    "poll_jira",
    "detect_blockers",
    "fetch_program_state",
}

# Capabilities that drive a real Chromium browser via browser-use BEFORE
# the LLM, then feed the search results into the LLM for synthesis.
# Day 4 — RESEARCH role's web tool. Requires the maistro-engine image
# (Chromium + browser-use baked in via Dockerfile).
_BROWSER_DRIVEN_CAPABILITIES: set[str] = {
    "web_search_background",
}


def _resolve_capability(task: TaskCreate) -> str:
    if task.capability:
        return task.capability
    match = _CAPABILITY_RE.search(task.description)
    if match:
        return match.group(1)
    return "unknown"


def _build_messages(role: AgentRole, capability: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    """Construct the OpenAI-compatible messages for one PM-agent invocation."""
    system = DEFAULT_SYSTEM_PROMPTS[role] + JSON_OUTPUT_SCHEMAS[role]
    user = build_capability_prompt(capability, payload)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _no_data_response(capability: str, payload: dict[str, Any]) -> PMRoleOutput:
    return PMRoleOutput(
        capability=capability,
        summary=(
            f"Capability '{capability}' requires a data source that is not wired in v0 yet. "
            "Returning source='no_data' rather than fabricating output."
        ),
        result={"payload": payload, "reason": "tool_unavailable"},
        source="no_data",
    )


def _extract_atlassian_pats(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Pull Jira + Confluence PATs out of program_context. Hive populates
    `program_context["atlassian_pats"] = {"jira": "...", "confluence": "..."}`
    from the per-user encrypted credential store before invoking pm_runner.
    PATs MUST NOT come from env per the v0 security model.
    """
    program = payload.get("program") if isinstance(payload, dict) else None
    if not isinstance(program, dict):
        return (None, None)
    pats = program.get("atlassian_pats")
    if not isinstance(pats, dict):
        return (None, None)
    jira_pat = pats.get("jira") if isinstance(pats.get("jira"), str) else None
    confluence_pat = pats.get("confluence") if isinstance(pats.get("confluence"), str) else None
    return (jira_pat or None, confluence_pat or None)


async def _run_browser_driven(
    role: AgentRole,
    capability: str,
    payload: dict[str, Any],
) -> PMRoleOutput:
    """Real Chromium → synthesize via LLM. Real web data, real Claude synthesis.

    Used by the RESEARCH role's `web_search_background` capability. Pulls
    query terms from the request payload; if the program context already
    has a `program_name` or `goals`, those feed the query.
    """
    # Build a query from the payload — program_name + goals if available,
    # else fall back to the description.
    program = payload.get("program") if isinstance(payload, dict) else None
    query_parts: list[str] = []
    if isinstance(program, dict):
        if program.get("program_name"):
            query_parts.append(str(program["program_name"]))
        goals = program.get("goals")
        if isinstance(goals, list) and goals:
            query_parts.append(str(goals[0]))
    if not query_parts and isinstance(payload, dict):
        desc = payload.get("description")
        if desc:
            query_parts.append(str(desc))
    query = " ".join(query_parts).strip() or "AI agent platforms"

    client = BrowserClient()
    try:
        search = await client.search_web(query, max_results=3)
    except BrowserToolError as exc:
        return PMRoleOutput(
            capability=capability,
            summary=(
                f"Web search unavailable: {exc}. "
                "RESEARCH agent skipped browser step; downstream agents see "
                "no scout_context for this run."
            ),
            result={"query": query, "error": str(exc)},
            source="no_data",
        )
    finally:
        await client.aclose()

    # Feed the real search results into the LLM for capability synthesis.
    enriched_payload = {**payload, "web_search": search.to_dict()}
    messages = _build_messages(role, capability, enriched_payload)
    try:
        raw = await jedai_llm_call(messages, temperature=0.2, json_mode=True)
    except Exception as exc:
        # Fall back to returning the search result directly — better than
        # losing the live data because synthesis failed.
        return PMRoleOutput(
            capability=capability,
            summary=(
                f"Web search returned {len(search.citations)} results; "
                f"LLM synthesis failed ({exc}). Raw results preserved."
            ),
            result={"web_search": search.to_dict(), "llm_error": str(exc)},
            source="no_data",
        )
    out = _parse_pm_output(raw, capability)
    if isinstance(out.result, dict):
        out.result.setdefault("web_search", search.to_dict())
    return out


async def _run_jira_driven(
    role: AgentRole,
    capability: str,
    payload: dict[str, Any],
) -> PMRoleOutput:
    """Tool-call then LLM-synthesize. Real Atlassian data, real Claude synthesis.

    Flow:
      1. Pull user's Jira PAT from program_context (never env).
      2. If absent — return source='no_data' with a clear hint to set credentials.
      3. Call mcp-jedai-atlassian → get real issues / state.
      4. Inject the real data into the LLM prompt context.
      5. Let Claude synthesize the PMRoleOutput.
    """
    jira_pat, _ = _extract_atlassian_pats(payload)
    if not jira_pat:
        return PMRoleOutput(
            capability=capability,
            summary=(
                "No Disney Jira PAT in credentials. "
                "Open Hive → Credentials → 'Disney Jira PAT (on-prem)' and "
                "paste a token from "
                "https://myjira.disney.com/secure/ViewProfile.jspa"
                "?selectedTab=com.atlassian.pats.pats-plugin:jira-user-personal-access-tokens"
            ),
            result={"reason": "no_jira_pat"},
            source="no_data",
        )

    client = AtlassianMCPClient()

    # Capability-specific query — capability-bound tool scope per the v0
    # security model. poll_jira uses jira_get_my_issues (read-only); other
    # capabilities pick the right read tool with hardcoded shape.
    try:
        if capability == "poll_jira":
            search = await client.jira_get_my_issues(max_results=25, jira_pat=jira_pat)
            tool_result = search.to_dict()
        elif capability == "detect_blockers":
            # Look for issues likely to block — JQL filter against the current
            # user, sorted by status. The LLM then identifies actual blockers.
            search = await client.jira_search_issues(
                jql="assignee = currentUser() AND resolution = Unresolved "
                "AND status in (Blocked, 'In Progress', Open) ORDER BY updated DESC",
                max_results=50,
                jira_pat=jira_pat,
            )
            tool_result = search.to_dict()
        elif capability == "fetch_program_state":
            # Program state = current user's active issues + recently updated.
            search = await client.jira_get_my_issues(max_results=50, jira_pat=jira_pat)
            tool_result = search.to_dict()
        else:
            # Unknown Jira-driven capability — return no_data rather than guess.
            return _no_data_response(capability, payload)
    except AtlassianMCPError as exc:
        return PMRoleOutput(
            capability=capability,
            summary=(
                f"Atlassian MCP error: {exc}. "
                "If your PAT has 2FA, regenerate it at the same Jira URL and "
                "save again under Hive → Credentials."
            ),
            result={"error": str(exc)},
            source="no_data",
        )

    # Feed real data into the LLM for synthesis.
    enriched_payload = {**payload, "jira_data": tool_result}
    messages = _build_messages(role, capability, enriched_payload)
    try:
        raw = await jedai_llm_call(messages, temperature=0.2, json_mode=True)
    except Exception as exc:
        return PMRoleOutput(
            capability=capability,
            summary=(
                f"Got {tool_result.get('total', 0)} Jira issues from {tool_result.get('jql', '?')}, "
                f"but LLM synthesis failed: {exc}"
            ),
            result={"jira_data": tool_result, "llm_error": str(exc)},
            source="no_data",
        )
    out = _parse_pm_output(raw, capability)
    # Always preserve the raw Jira data so downstream agents can re-use it.
    if isinstance(out.result, dict):
        out.result.setdefault("jira_data", tool_result)
    return out


def _parse_pm_output(raw: str, capability: str) -> PMRoleOutput:
    """Parse the LLM's JSON response into a PMRoleOutput. Defensive against
    minor schema drift — fall back to wrapping the raw text in `summary`."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return PMRoleOutput(
            capability=capability,
            summary=raw[:2000],
            result={"raw": raw},
            source="llm",
        )
    if not isinstance(data, dict):
        return PMRoleOutput(
            capability=capability,
            summary=str(data),
            result={"raw": raw},
            source="llm",
        )
    data.setdefault("capability", capability)
    data.setdefault("summary", "")
    data.setdefault("result", {k: v for k, v in data.items() if k not in {"capability", "summary", "result", "source"}})
    data.setdefault("source", "llm")
    try:
        return PMRoleOutput.model_validate(data)
    except Exception:
        return PMRoleOutput(
            capability=capability,
            summary=str(data.get("summary", ""))[:2000],
            result=data,
            source="llm",
        )


def _wrap_for_hive(output: PMRoleOutput, agent_label: str, task_description: str) -> ConductorOutput:
    """Wrap PMRoleOutput in the legacy ConductorOutput shape the Hive
    backend expects until the program_hyperagent surface is migrated to
    HyperagentOutput (v0.5)."""
    summary = (
        f"[{agent_label}] {output.capability} -> source={output.source}\n"
        f"{output.summary}\n\n"
        f"```json\n{json.dumps(output.result, indent=2)}\n```"
    )
    return ConductorOutput(
        plan=PlanOutput(
            summary=f"PM capability: {output.capability}",
            subtasks=[SubTask(title=output.capability, description=task_description)],
        ),
        final_answer=summary,
        success=True,
    )


async def run_pm_task(task: TaskCreate) -> ConductorOutput:
    """Execute a PM fleet capability via real Claude via the JedAI gateway."""
    if os.environ.get("MAISTRO_PM_USE_STUBS", "").lower() in {"1", "true", "yes"}:
        # Emergency rollback path: keep the legacy stub behavior available
        # but only when an operator explicitly opts in.
        from maistro.tools.pm_stubs import PM_STUB_HANDLERS

        capability = normalize_capability(_resolve_capability(task))
        result_dict = PM_STUB_HANDLERS.get(capability, lambda p: {})(
            {"description": task.description, "program": task.program_context or {}}
        )
        out = PMRoleOutput(
            capability=capability,
            summary=f"[stub-rollback] {capability}",
            result=result_dict,
            source="no_data",
        )
        return _wrap_for_hive(out, "PM Agent (stub-rollback)", task.description)

    capability = normalize_capability(_resolve_capability(task))
    prog_ctx = task.program_context if isinstance(task.program_context, dict) else {}
    # v0 note: pm_runner produces DRAFTS only. Every output from gated capabilities
    # carries draft_status='needs_confirm' (enforced by the capability prompt
    # templates in graph/pm_domain.py). The actual write to Jira/Confluence
    # happens in Hive's draft-confirm handler, which checks
    # `program_context["confirmed"]` before invoking the Atlassian MCP. The old
    # pre-call gate raised before the LLM ever ran, which blocked draft
    # generation itself — wrong for v0. v1 may reintroduce a finer-grained gate.
    if is_gated(capability) and not prog_ctx.get("confirmed"):
        logger.info(
            "pm_gated_draft_generation",
            capability=capability,
            note="draft_status='needs_confirm' is enforced in the prompt; write occurs in Hive after confirm",
        )

    agent_id = task.agent_id or ""
    defn = get_pm_def(agent_id) if agent_id else None
    agent_label = defn.display_name if defn else agent_id or "PM Agent"

    role = _PM_AGENT_TO_ROLE.get(agent_id) if agent_id else None
    if role is None:
        # Fall back: derive role from capability via the primary-capability map.
        for r, primary in PM_PRIMARY_CAPABILITY.items():
            if primary == capability:
                role = r
                break
    if role is None:
        return _wrap_for_hive(
            _no_data_response(capability, {"description": task.description}),
            agent_label,
            task.description,
        )

    payload: dict[str, Any] = {"description": task.description}
    if task.program_context:
        payload["program"] = task.program_context

    # Routing:
    #   1. Jira-driven capabilities → real MCP tool call → real data into LLM
    #      synthesis (Day 3).
    #   2. Browser-driven capabilities → real Chromium via browser-use → real
    #      search results into LLM synthesis (Day 4).
    #   3. _NO_DATA_WITHOUT_TOOLS → short-circuit to source='no_data' (Airtable
    #      etc., not wired yet — never fabricate).
    #   4. Everything else → straight LLM call with persona + capability prompt.
    if capability in _JIRA_DRIVEN_CAPABILITIES:
        out = await _run_jira_driven(role, capability, payload)
    elif capability in _BROWSER_DRIVEN_CAPABILITIES:
        out = await _run_browser_driven(role, capability, payload)
    elif capability in _NO_DATA_WITHOUT_TOOLS:
        out = _no_data_response(capability, payload)
    else:
        messages = _build_messages(role, capability, payload)
        try:
            raw = await jedai_llm_call(messages, temperature=0.2, json_mode=True)
        except Exception as exc:
            logger.warning(
                "pm_llm_call_failed",
                agent_id=agent_id,
                role=role.value,
                capability=capability,
                error=str(exc),
            )
            raise
        out = _parse_pm_output(raw, capability)

    await logger.ainfo(
        "pm_task_complete",
        agent_id=agent_id,
        role=role.value,
        capability=capability,
        source=out.source,
        summary_len=len(out.summary),
    )
    _log.debug(
        "pm_task_complete agent=%s role=%s capability=%s source=%s",
        agent_id,
        role.value,
        capability,
        out.source,
    )

    return _wrap_for_hive(out, agent_label, task.description)
