"""Run the daily-status DAG and shape the result for the Daily Report
frontend.

This is the Phase 4 proof-point that the substrate composes — instead of
the Hive route polling Jira inline, it builds a DurableRunStore, registers
the daily_status_seed via dag_registry, injects the per-user PAT + base
URL, runs through run_durable_dag, and translates the result back into
the response shape DailyReport.tsx already consumes. No frontend change
required.

The legacy inline polling stays as a fallback for the case where the
substrate is unavailable / the run fails — graceful degradation matters
for an observability surface.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from maistro.container import build_node_resolver
from maistro.graph.dag_registry import DagRegistry
from maistro.graph.durable_runs import InMemoryDurableRunStore, RunStatus, run_durable_dag
from maistro.graph.seeds import daily_status_seed

logger = logging.getLogger(__name__)


# Module-level registry so a per-process boot registers once + reuses.
_registry: DagRegistry | None = None

# Module-level resolver: this app imports maistro-core pieces directly rather
# than constructing a full Container, so build_node_resolver()'s no-arg
# defaults (the shared usage log, an empty harness-adapter map) are what it
# picks up -- the same pattern a full Container would wire, just reachable
# without needing one. Falls back to the plain registry lookup
# (`get_node(kind)()`) for kinds like jira.poll that need no special wiring.
_node_resolver = build_node_resolver()


def _get_registry() -> DagRegistry:
    """Lazily build the DagRegistry + register the bundled seeds."""
    global _registry
    if _registry is None:
        _registry = DagRegistry()
        # Register the canonical PM-fleet daily-status seed under
        # `dag:daily-status`. Subsequent re-imports are no-ops (the
        # registry's version-bump path tolerates re-register).
        _registry.register(daily_status_seed())
    return _registry


def _inject_jira_credentials(
    dag: dict[str, Any], *, pat: str, base_url: str, flavor: str = "server"
) -> dict[str, Any]:
    """Mutate (in-place) the daily-status DAG snapshot's jira_poll inputs to
    include the per-request user PAT + base URL. The DAG snapshot itself
    came from the registry's frozen copy; this is the per-call overlay."""
    for spec in dag.get("nodes", []):
        if spec.get("id") == "jira_poll":
            inputs = dict(spec.get("inputs", {}))
            inputs["pat"] = pat
            inputs["base_url"] = base_url
            inputs["flavor"] = flavor
            spec["inputs"] = inputs
            break
    return dag


async def run_daily_status_dag(
    *,
    user_id: str | None,
    project_id: str | None,
    pat: str,
    base_url: str,
    flavor: str = "server",
) -> dict[str, Any]:
    """Run the daily-status DAG with per-user credentials. Returns the JIRA
    section shape that the existing daily_report route emits — `status`,
    `issues`, `count`, plus a `source` field set to `"dag:daily-status"`
    so the UI can tell the DAG-backed path apart from any legacy fallback.
    """
    registry = _get_registry()
    snapshot = dict(registry.get("daily-status").snapshot)  # shallow copy
    # Deep enough to mutate the jira_poll node's inputs without touching
    # the registry's frozen template.
    snapshot["nodes"] = [dict(n) for n in snapshot["nodes"]]
    _inject_jira_credentials(snapshot, pat=pat, base_url=base_url, flavor=flavor)

    store = InMemoryDurableRunStore()
    try:
        result = await run_durable_dag(
            snapshot,
            store=store,
            node_resolver=_node_resolver,
            user_id=user_id,
            project_id=project_id,
        )
    except Exception as exc:
        logger.warning("daily_status_dag_run_failed: %s", exc)
        return {
            "status": "error",
            "detail": f"daily-status DAG run raised: {type(exc).__name__}",
            "issues": [],
            "source": "dag:daily-status",
        }

    # Phase 5 Signal #5: fan every COMPLETED node into the metrics store
    # so /v1/dag-runs/metrics aggregates this run's contribution to the
    # node-kind histograms.
    try:
        from services.node_metrics_store import record_run_completion

        record_run_completion(result)
    except Exception as exc:
        # metrics ingestion must never fail the user-facing daily report
        logger.warning("daily_status_metrics_ingest_failed: %s", exc)

    return _result_to_jira_section(result, base_url=base_url, flavor=flavor)


def _result_to_jira_section(
    result: Any,  # DurableRunRecord; typed loose to avoid the cross-package import
    *,
    base_url: str,
    flavor: str,
) -> dict[str, Any]:
    """Translate the DAG run's per-node records into the response shape
    DailyReport.tsx already consumes."""
    by_id = {nr.node_id: nr for nr in result.node_records}

    if result.status == RunStatus.FAILED:
        # If jira_poll itself raised a PermissionError, surface the same
        # "auth_failed" / "no_pat" shape the inline path emitted.
        jp = by_id.get("jira_poll")
        if jp is not None and jp.error_code == "PermissionError":
            return {
                "status": "auth_failed",
                "detail": jp.error_message or "Jira authentication failed",
                "issues": [],
                "source": "dag:daily-status",
            }
        return {
            "status": "error",
            "detail": (result.error_message or f"daily-status run failed: {result.error_code}"),
            "issues": [],
            "source": "dag:daily-status",
        }

    # Successful run — lift jira_poll's output for the issues list +
    # filter for the kept count.
    jp_out = (by_id.get("jira_poll") or _missing()).output or {}
    filt_out = (by_id.get("jira_epic_filter") or _missing()).output or {}

    # The kept items have been formatted into a Markdown section appended
    # to the run's blackboard at metadata["dashboard:daily-status"]; we
    # return both the raw issues (for the section card) and the kept-Epic
    # count for the headline.
    issues = []
    for raw in jp_out.get("issues") or []:
        issues.append(
            {
                "key": raw.get("key", ""),
                "summary": raw.get("summary", ""),
                "status": raw.get("status", ""),
                "updated": raw.get("updated", ""),
                "url": raw.get("url", f"{base_url.rstrip('/')}/browse/{raw.get('key', '')}"),
            }
        )

    return {
        "status": "ok",
        "issues": issues,
        "count": int(jp_out.get("count") or 0),
        "epics_kept": int(filt_out.get("kept") or 0),
        "source": "dag:daily-status",
        "flavor": flavor,
    }


class _MissingNode:
    """Sentinel for `by_id.get(...) or _missing()` — keeps the lookups
    branch-free + None-safe."""

    output: ClassVar[dict[str, Any]] = {}


def _missing() -> _MissingNode:
    return _MissingNode()
