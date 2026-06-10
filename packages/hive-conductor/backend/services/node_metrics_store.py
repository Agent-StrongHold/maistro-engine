"""Phase 5 — Signal #5: per-node latency + token metrics aggregator.

When a durable run completes, the runner calls
`record_run_completion(run)` and this module fans every COMPLETED
DurableNodeRecord into a ring-buffered observation. The endpoint
`GET /v1/dag-runs/metrics` reads back per-node aggregates over a time
window (default 1h):

  - count, p50, p95, p99 latency_ms
  - total + mean tokens_in / tokens_out
  - success rate (COMPLETED / total)
  - per-(node_kind, project_id) slicing

The store is a fixed-size deque so memory stays bounded across long
uptimes. Persistent backing lands later — when it does, the public
API on this module stays stable.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

DEFAULT_MAX_OBSERVATIONS = 10_000


@dataclass(frozen=True)
class NodeObservation:
    """One per-node completion event, captured for metric aggregation."""

    run_id: str
    node_id: str
    node_kind: str
    project_id: str
    dag_id: str
    phase: str  # "COMPLETED" | "FAILED" | other
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model_used: str
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class NodeMetricsStore:
    """In-memory ring buffer of node observations."""

    def __init__(self, *, max_observations: int = DEFAULT_MAX_OBSERVATIONS) -> None:
        self._buf: deque[NodeObservation] = deque(maxlen=max_observations)

    def append(self, obs: NodeObservation) -> None:
        self._buf.append(obs)

    def __len__(self) -> int:
        return len(self._buf)

    def clear(self) -> None:
        self._buf.clear()

    def _filter(
        self,
        *,
        node_kind: str = "",
        project_id: str = "",
        node_id: str = "",
        dag_id: str = "",
        window_seconds: int = 3600,
        now: datetime | None = None,
    ) -> list[NodeObservation]:
        cutoff = (now or datetime.now(UTC)) - timedelta(seconds=window_seconds)
        out: list[NodeObservation] = []
        for obs in self._buf:
            if obs.recorded_at < cutoff:
                continue
            if node_kind and obs.node_kind != node_kind:
                continue
            if project_id and obs.project_id != project_id:
                continue
            if node_id and obs.node_id != node_id:
                continue
            if dag_id and obs.dag_id != dag_id:
                continue
            out.append(obs)
        return out

    def aggregate(
        self,
        *,
        node_kind: str = "",
        project_id: str = "",
        node_id: str = "",
        dag_id: str = "",
        window_seconds: int = 3600,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return aggregate stats for the filtered observation set."""
        obs = self._filter(
            node_kind=node_kind,
            project_id=project_id,
            node_id=node_id,
            dag_id=dag_id,
            window_seconds=window_seconds,
            now=now,
        )
        return _aggregate(obs)

    def list_observations(
        self,
        *,
        node_kind: str = "",
        project_id: str = "",
        window_seconds: int = 3600,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        obs = self._filter(
            node_kind=node_kind,
            project_id=project_id,
            window_seconds=window_seconds,
            now=now,
        )
        # newest first; cap to `limit`
        return [_to_dict(o) for o in reversed(obs[-limit:])]


def _percentile(values: list[int], pct: float) -> int:
    """Linear-interpolation percentile over a pre-sorted list."""
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    rank = (pct / 100.0) * (len(values) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return values[lo]
    frac = rank - lo
    return int(values[lo] + (values[hi] - values[lo]) * frac)


def _aggregate(obs: Iterable[NodeObservation]) -> dict[str, Any]:
    items = list(obs)
    n = len(items)
    if n == 0:
        return {
            "count": 0,
            "succeeded": 0,
            "failed": 0,
            "success_rate": 0.0,
            "latency_ms_p50": 0,
            "latency_ms_p95": 0,
            "latency_ms_p99": 0,
            "latency_ms_mean": 0.0,
            "tokens_in_total": 0,
            "tokens_in_mean": 0.0,
            "tokens_out_total": 0,
            "tokens_out_mean": 0.0,
            "cost_usd_total": 0.0,
        }
    latencies = sorted(o.latency_ms for o in items)
    succeeded = sum(1 for o in items if o.phase == "COMPLETED")
    failed = sum(1 for o in items if o.phase == "FAILED")
    tokens_in = sum(o.tokens_in for o in items)
    tokens_out = sum(o.tokens_out for o in items)
    cost = sum(o.cost_usd for o in items)
    return {
        "count": n,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate": round(succeeded / n, 4),
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
        "latency_ms_p99": _percentile(latencies, 99),
        "latency_ms_mean": round(sum(latencies) / n, 1),
        "tokens_in_total": tokens_in,
        "tokens_in_mean": round(tokens_in / n, 1),
        "tokens_out_total": tokens_out,
        "tokens_out_mean": round(tokens_out / n, 1),
        "cost_usd_total": round(cost, 4),
    }


def _to_dict(obs: NodeObservation) -> dict[str, Any]:
    return {
        "run_id": obs.run_id,
        "node_id": obs.node_id,
        "node_kind": obs.node_kind,
        "project_id": obs.project_id,
        "dag_id": obs.dag_id,
        "phase": obs.phase,
        "latency_ms": obs.latency_ms,
        "tokens_in": obs.tokens_in,
        "tokens_out": obs.tokens_out,
        "cost_usd": obs.cost_usd,
        "model_used": obs.model_used,
        "recorded_at": obs.recorded_at.isoformat(),
    }


# Module-level singleton — replaceable from tests via set_store().
_store = NodeMetricsStore()


def get_store() -> NodeMetricsStore:
    return _store


def set_store(store: NodeMetricsStore) -> None:
    global _store
    _store = store


def record_run_completion(run_record: Any) -> int:
    """Ingest every node from a finished DurableRunRecord into the store.

    Accepts the Pydantic record (or any duck-typed object with
    `.run_id`, `.dag_id`, `.project_id`, and `.node_records[*]` with
    `node_id`, `kind`, `phase`, `latency_ms`, `tokens_in`, `tokens_out`,
    `model_used`, `cost_usd`).

    Returns the number of node observations appended.
    """
    if run_record is None:
        return 0
    run_id = str(getattr(run_record, "run_id", "") or "")
    project_id = str(getattr(run_record, "project_id", "") or "")
    dag_id = str(getattr(run_record, "dag_id", "") or "")
    records = getattr(run_record, "node_records", None) or []
    appended = 0
    for nr in records:
        phase = getattr(nr, "phase", "")
        # Phase is a StrEnum — coerce via str() so the str-comparison
        # in `_aggregate` sees the canonical "COMPLETED" / "FAILED" form.
        phase_str = str(phase).split(".")[-1] if phase else ""
        obs = NodeObservation(
            run_id=run_id,
            node_id=str(getattr(nr, "node_id", "") or ""),
            node_kind=str(getattr(nr, "kind", "") or ""),
            project_id=project_id,
            dag_id=dag_id,
            phase=phase_str.upper(),
            latency_ms=int(getattr(nr, "latency_ms", 0) or 0),
            tokens_in=int(getattr(nr, "tokens_in", 0) or 0),
            tokens_out=int(getattr(nr, "tokens_out", 0) or 0),
            cost_usd=float(getattr(nr, "cost_usd", 0.0) or 0.0),
            model_used=str(getattr(nr, "model_used", "") or ""),
        )
        _store.append(obs)
        appended += 1
    return appended
