"""Tests for the daily_status_runner service.

Boy Scout Rule: services/daily_status_runner.py was created in this PR;
it must reach ≥95% line + ≥95% branch coverage with strong assertions
(value checks, not isinstance).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import sys
import pathlib
_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

from services.daily_status_runner import (  # noqa: E402
    _get_registry,
    _inject_jira_credentials,
    _node_resolver,
    _result_to_jira_section,
    run_daily_status_dag,
)


# --- _get_registry: idempotent + carries the seed ---------------------------


def test_get_registry_returns_same_instance_each_call() -> None:
    a = _get_registry()
    b = _get_registry()
    assert a is b
    assert "daily-status" in a


def test_registry_contains_daily_status_with_pm_use_case() -> None:
    reg = _get_registry()
    desc = reg.get("daily-status")
    assert desc is not None
    assert desc.use_case == "pm_fleet"
    assert desc.agent_id == "dag:daily-status"


# --- _inject_jira_credentials --------------------------------------------


def test_inject_jira_credentials_mutates_jira_poll_node_only() -> None:
    snap = {
        "nodes": [
            {"id": "jira_poll", "inputs": {"base_url": "", "pat": "", "flavor": "server"}},
            {"id": "other", "inputs": {"untouched": True}},
        ]
    }
    _inject_jira_credentials(
        snap, pat="abc-pat", base_url="https://example.atlassian.net", flavor="cloud"
    )
    poll = next(n for n in snap["nodes"] if n["id"] == "jira_poll")
    other = next(n for n in snap["nodes"] if n["id"] == "other")
    assert poll["inputs"]["pat"] == "abc-pat"
    assert poll["inputs"]["base_url"] == "https://example.atlassian.net"
    assert poll["inputs"]["flavor"] == "cloud"
    assert other["inputs"] == {"untouched": True}


def test_inject_credentials_no_jira_poll_is_noop() -> None:
    """If a snapshot lacks the jira_poll node, the helper returns the
    snapshot unchanged (no KeyError)."""
    snap = {"nodes": [{"id": "alt"}]}
    out = _inject_jira_credentials(snap, pat="x", base_url="y")
    assert out["nodes"] == [{"id": "alt"}]


# --- _node_resolver --------------------------------------------------------


def test_node_resolver_returns_registered_node_by_id() -> None:
    dag = {
        "nodes": [
            {"id": "n1", "kind": "transform.alias_keys"},
        ]
    }
    node = _node_resolver("n1", dag)
    assert type(node).__name__ == "TransformAliasKeysNode"


def test_node_resolver_unknown_id_raises_key_error() -> None:
    with pytest.raises(KeyError):
        _node_resolver("ghost", {"nodes": []})


# --- _result_to_jira_section -----------------------------------------------


class _FakeRecord:
    """Minimal stand-in for DurableRunRecord — only the fields the helper
    reads."""

    def __init__(self, status: Any, node_records: list[Any],
                 error_code: str | None = None, error_message: str | None = None) -> None:
        self.status = status
        self.node_records = node_records
        self.error_code = error_code
        self.error_message = error_message


class _FakeNodeRec:
    def __init__(self, node_id: str, output: dict[str, Any] | None = None,
                 error_code: str | None = None,
                 error_message: str | None = None) -> None:
        self.node_id = node_id
        self.output = output
        self.error_code = error_code
        self.error_message = error_message


def test_result_to_jira_section_completed_returns_ok_with_issues() -> None:
    from maistro.graph.durable_runs import RunStatus

    jp_record = _FakeNodeRec(
        "jira_poll",
        output={
            "count": 2,
            "issues": [
                {"key": "P-1", "summary": "Ship X", "status": "Done", "updated": "t1",
                 "url": "https://jira.example.com/browse/P-1"},
                {"key": "P-2", "summary": "Hire Y", "status": "Open", "updated": "t2",
                 "url": "https://jira.example.com/browse/P-2"},
            ],
        },
    )
    filt_record = _FakeNodeRec("jira_epic_filter", output={"kept": 1, "dropped": 1})
    rec = _FakeRecord(RunStatus.COMPLETED, [jp_record, filt_record])
    section = _result_to_jira_section(rec, base_url="https://jira.example.com", flavor="server")
    assert section["status"] == "ok"
    assert section["count"] == 2
    assert section["epics_kept"] == 1
    assert section["source"] == "dag:daily-status"
    assert section["flavor"] == "server"
    keys = [i["key"] for i in section["issues"]]
    assert keys == ["P-1", "P-2"]


def test_result_to_jira_section_failed_permission_returns_auth_failed() -> None:
    from maistro.graph.durable_runs import RunStatus

    jp_record = _FakeNodeRec(
        "jira_poll",
        error_code="PermissionError",
        error_message="jira_auth_failed status=401 base=https://jira.example.com",
    )
    rec = _FakeRecord(
        RunStatus.FAILED, [jp_record],
        error_code="PermissionError", error_message="propagated",
    )
    section = _result_to_jira_section(rec, base_url="https://jira.example.com", flavor="server")
    assert section["status"] == "auth_failed"
    assert "jira_auth_failed" in section["detail"]
    assert section["issues"] == []
    assert section["source"] == "dag:daily-status"


def test_result_to_jira_section_other_failure_returns_error() -> None:
    from maistro.graph.durable_runs import RunStatus

    jp_record = _FakeNodeRec(
        "jira_poll", error_code="RuntimeError",
        error_message="jira_http_error status=500",
    )
    rec = _FakeRecord(
        RunStatus.FAILED, [jp_record],
        error_code="RuntimeError", error_message="propagated",
    )
    section = _result_to_jira_section(rec, base_url="https://x", flavor="server")
    assert section["status"] == "error"
    assert section["issues"] == []
    assert "propagated" in section["detail"] or "RuntimeError" in section["detail"]


def test_result_to_jira_section_missing_url_uses_constructed_browse_url() -> None:
    from maistro.graph.durable_runs import RunStatus

    jp_record = _FakeNodeRec(
        "jira_poll",
        output={
            "count": 1,
            "issues": [{"key": "P-9", "summary": "x", "status": "Open"}],  # no url
        },
    )
    rec = _FakeRecord(RunStatus.COMPLETED, [jp_record])
    section = _result_to_jira_section(rec, base_url="https://jira.example.com/", flavor="server")
    assert section["issues"][0]["url"] == "https://jira.example.com/browse/P-9"


# --- end-to-end run_daily_status_dag with httpx mocked --------------------


async def test_run_daily_status_dag_completes_with_mocked_jira(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_issues = {
        "issues": [
            {
                "key": "PROJ-1",
                "fields": {
                    "summary": "Ship feature A",
                    "status": {"name": "In Progress"},
                    "updated": "2026-05-22T08:00:00Z",
                    "issuetype": {"name": "Epic"},
                },
            }
        ]
    }

    class _Resp:
        status_code = 200
        def json(self) -> Any: return fake_issues

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None: ...
        async def __aenter__(self) -> "_Client": return self
        async def __aexit__(self, *a: Any) -> None: ...
        async def get(self, *a: Any, **kw: Any) -> _Resp: return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    section = await run_daily_status_dag(
        user_id="u1", project_id="p1", pat="tk",
        base_url="https://jira.example.com", flavor="server",
    )
    assert section["status"] == "ok"
    assert section["count"] == 1
    assert section["epics_kept"] == 1
    assert section["source"] == "dag:daily-status"
    assert section["issues"][0]["key"] == "PROJ-1"
    assert section["flavor"] == "server"


async def test_run_daily_status_dag_401_returns_auth_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Resp:
        status_code = 401
        def json(self) -> Any: return {}

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None: ...
        async def __aenter__(self) -> "_Client": return self
        async def __aexit__(self, *a: Any) -> None: ...
        async def get(self, *a: Any, **kw: Any) -> _Resp: return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    section = await run_daily_status_dag(
        user_id="u1", project_id="p1", pat="bad",
        base_url="https://jira.example.com", flavor="server",
    )
    assert section["status"] == "auth_failed"
    assert section["issues"] == []


async def test_run_daily_status_dag_catches_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route MUST never crash on a runtime failure inside the executor;
    runner returns a structured 'error' section instead."""
    # Patch run_durable_dag to raise; verifies the outer try/except guard.
    import services.daily_status_runner as runner

    async def _boom(*a: Any, **kw: Any) -> Any:
        raise RuntimeError("synthetic boom")

    monkeypatch.setattr(runner, "run_durable_dag", _boom)
    section = await run_daily_status_dag(
        user_id="u1", project_id="p1", pat="tk",
        base_url="https://jira.example.com", flavor="server",
    )
    assert section["status"] == "error"
    assert "RuntimeError" in section["detail"]
    assert section["issues"] == []
