"""PM fleet task executor — real LLM calls via the LLM gateway (v0).

Replaces the stub-only POC dispatch. Each PM capability invocation maps
to a single Claude call through the LLM gateway. The agent's persona
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
from maistro.agents.pm_llm_call import maistro_llm_call
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
# LLM is called. v0 Atlassian (Day 3) replaces the Jira items here with
# real MCP tool-call paths; until then we don't fabricate data.
_NO_DATA_WITHOUT_TOOLS: set[str] = {
    "poll_jira",
    "sync_jira",
    "create_jira_ticket",
    "create_subtask",
    "detect_blockers",
    "poll_airtable",
    "fetch_program_metrics",
    "fetch_program_state",
    "fetch_dependency_graph",
    "publish_dashboard",
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
    """Execute a PM fleet capability via real Claude via the LLM gateway."""
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

    # Short-circuit capabilities that require unwired data tools — never
    # fabricate. Day 3+ wires Atlassian MCP, Day 4 wires browser-use.
    if capability in _NO_DATA_WITHOUT_TOOLS:
        out = _no_data_response(capability, payload)
    else:
        messages = _build_messages(role, capability, payload)
        try:
            raw = await maistro_llm_call(messages, temperature=0.2, json_mode=True)
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
