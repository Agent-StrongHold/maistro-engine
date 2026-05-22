"""Day 2 PM runner — real LLM call path tests.

Covers the rewrite of `pm_runner.run_pm_task()` from stub-only dispatch
to JedAI-gateway-backed Claude calls. Live LLM test gated by
`RUN_LIVE_LLM=1` so default CI doesn't burn tokens; the offline tests
monkeypatch `jedai_llm_call` and exercise schema/contract paths.
"""
from __future__ import annotations

import json
import os

import pytest

from maistro.agents import pm_runner
from maistro.agents.types import ConductorOutput
from maistro.graph.types import AgentRole, PMRoleOutput
from maistro.tasks.models import TaskCreate


def _task(*, agent_id: str = "intake", capability: str = "create_initiative",
          description: str = "Launch a new agent platform",
          confirmed: bool = False) -> TaskCreate:
    return TaskCreate(
        description=description,
        agent_id=agent_id,
        capability=capability,
        program_context={"program_name": "JedAI v0", "goals": ["ship in 7 days"],
                         "confirmed": confirmed},
    )


@pytest.mark.asyncio
async def test_runner_calls_llm_for_non_gated_capability(monkeypatch):
    """Non-gated capabilities (e.g. create_initiative) must invoke jedai_llm_call."""
    captured: dict[str, object] = {}

    async def fake_llm_call(messages, *, model=None, temperature=None,
                             json_mode=True, timeout=120.0):
        captured["messages"] = messages
        captured["model"] = model
        return json.dumps({
            "capability": "create_initiative",
            "summary": "Drafted initiative for the JedAI v0 launch program — 6 goals identified.",
            "result": {"title": "JedAI v0 launch", "goals": ["ship in 7 days"],
                       "draft_status": "needs_confirm"},
            "source": "llm",
        })

    monkeypatch.setattr(pm_runner, "jedai_llm_call", fake_llm_call)
    monkeypatch.delenv("MAISTRO_PM_USE_STUBS", raising=False)

    result = await pm_runner.run_pm_task(_task())
    assert isinstance(result, ConductorOutput)
    assert result.success
    # The LLM call must have been routed (2 messages: system + user).
    msgs = captured.get("messages")
    assert msgs is not None and len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "Intake Agent" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "create_initiative" in msgs[1]["content"]
    # Final answer must include the LLM summary, not a stub marker.
    assert "Drafted initiative" in result.final_answer
    assert "POC stub completed" not in result.final_answer


@pytest.mark.asyncio
async def test_runner_short_circuits_no_data_capabilities(monkeypatch):
    """poll_jira and the rest of _NO_DATA_WITHOUT_TOOLS must not call the LLM
    and must return source='no_data' rather than fabricate."""
    called = False

    async def fake_llm_call(*args, **kwargs):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr(pm_runner, "jedai_llm_call", fake_llm_call)
    monkeypatch.delenv("MAISTRO_PM_USE_STUBS", raising=False)

    result = await pm_runner.run_pm_task(
        _task(agent_id="delivery", capability="poll_jira",
              description="Fetch open issues for Alice")
    )
    assert called is False, "poll_jira must not invoke the LLM in v0 (no MCP wired)"
    assert "source=no_data" in result.final_answer


@pytest.mark.asyncio
async def test_gated_capability_generates_draft_without_raising(monkeypatch):
    """v0: gated capabilities produce drafts in pm_runner (with
    draft_status='needs_confirm' embedded in the LLM output). The actual
    write gate lives in Hive's confirm handler, not here."""
    monkeypatch.setattr(
        pm_runner, "jedai_llm_call",
        # `create_jira_ticket` is in _NO_DATA_WITHOUT_TOOLS so it short-circuits
        # before LLM in v0; we test create_initiative instead since it's gated
        # but not in the no-data set.
        _ := __import__("asyncio").coroutine(lambda *a, **kw: '{"capability":"create_initiative","summary":"x","result":{"draft_status":"needs_confirm"},"source":"llm"}') if False else (
            lambda *args, **kwargs: __import__("asyncio").sleep(0)
        ),
    )
    # Use a proper async stub via monkeypatch + an actual async fn:
    async def fake_llm_call(*args, **kwargs):
        return ('{"capability":"create_initiative","summary":"Drafted initiative",'
                '"result":{"draft_status":"needs_confirm"},"source":"llm"}')
    monkeypatch.setattr(pm_runner, "jedai_llm_call", fake_llm_call)
    monkeypatch.delenv("MAISTRO_PM_USE_STUBS", raising=False)

    # create_initiative is gated AND not in _NO_DATA_WITHOUT_TOOLS — exercise the gate path.
    result = await pm_runner.run_pm_task(
        _task(agent_id="intake", capability="create_initiative", confirmed=False)
    )
    assert result.success
    # The output is a draft — the LLM was called, output includes draft_status.
    assert "needs_confirm" in result.final_answer
    # Write capabilities that are also no-data (create_jira_ticket) still short-circuit.
    result_no_data = await pm_runner.run_pm_task(
        _task(agent_id="delivery", capability="create_jira_ticket", confirmed=False)
    )
    assert "source=no_data" in result_no_data.final_answer


@pytest.mark.asyncio
async def test_stub_rollback_mode_uses_legacy_handlers(monkeypatch):
    """MAISTRO_PM_USE_STUBS=true reverts to the legacy stub dispatch."""
    monkeypatch.setenv("MAISTRO_PM_USE_STUBS", "true")
    called = False

    async def fake_llm_call(*args, **kwargs):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr(pm_runner, "jedai_llm_call", fake_llm_call)

    result = await pm_runner.run_pm_task(_task())
    assert called is False, "rollback mode must not hit the LLM"
    assert result.success
    assert "stub-rollback" in result.final_answer


@pytest.mark.asyncio
async def test_malformed_llm_response_doesnt_crash(monkeypatch):
    """If the gateway returns non-JSON or wrong shape, we still return a
    valid ConductorOutput rather than 500ing the user."""

    async def fake_llm_call(*args, **kwargs):
        return "This is not JSON — the gateway returned plain text."

    monkeypatch.setattr(pm_runner, "jedai_llm_call", fake_llm_call)
    monkeypatch.delenv("MAISTRO_PM_USE_STUBS", raising=False)

    result = await pm_runner.run_pm_task(_task())
    assert result.success
    # The raw text gets surfaced in the summary so the operator can debug.
    assert "This is not JSON" in result.final_answer


# Live LLM test — only runs with RUN_LIVE_LLM=1 + valid .env settings.
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_LLM") != "1",
    reason="Live JedAI gateway call; set RUN_LIVE_LLM=1 + LITELLM_URL + LITELLM_MASTER_KEY"
        " + DEFAULT_MODEL to enable.",
)
async def test_intake_create_initiative_live_through_jedai_gateway():
    """End-to-end: hit the real JedAI gateway via jedai_llm_call, parse a
    real Claude response into PMRoleOutput, wrap in ConductorOutput.
    Asserts the response is substantive (no stub markers, len > 80)."""
    task = _task(description="Build a self-improving DAG-shaped PM hyperagent for JFC v0")
    result = await pm_runner.run_pm_task(task)
    assert isinstance(result, ConductorOutput)
    assert result.success
    assert "source=llm" in result.final_answer
    assert "source=stub" not in result.final_answer
    # Substantive output — not a one-liner from a misconfigured model.
    assert len(result.final_answer) > 200, (
        f"Live response unexpectedly short: {result.final_answer!r}"
    )
