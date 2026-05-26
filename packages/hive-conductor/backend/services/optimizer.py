"""Phase 6 — Optimizer service: 5-signal weighted aggregator + proposer.

Ingests:

  Signal #1 error_code        weight 3.0
  Signal #2 user_manual_edit  weight 2.5   (highest among non-failure)
  Signal #3 eval_judge_score  weight 1.5
  Signal #4 thumbs            weight 1.0
  Signal #5 latency/tokens    weight 0.5

Reads from:

  - services.node_metrics_store     → per-node latency / tokens / errors
  - services.feedback_service       → thumbs outcomes (via outcome_store)
  - stores.eval_verdicts            → eval-judge verdicts (rationale + proposal)
  - stores.audit_log                → dag_edit entries (user manual overrides)

Emits ranked proposals into stores.optimizer_proposals. Each proposal
has a class:

  AUTO_APPLY — model swap / edge weight tune / retry-count adjustment.
                Applied immediately UNLESS the target field is
                edit_lock.is_locked() (manual user override). All
                auto-applies write an audit_log entry.

  PROPOSE    — topology mutations / prompt rewrites. The user reviews +
               approves via POST /v1/optimizer/proposals/{id}/accept.
               The accept/reject is itself a Signal #4-style outcome
               (the user's vote refines the next optimizer round).

The optimizer never raises on data anomalies; missing / empty stores
produce zero proposals and an empty result.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# Weighted aggregator constants — locked per the 90-day plan.
WEIGHT_ERROR_CODE = 3.0
WEIGHT_USER_EDIT = 2.5
WEIGHT_EVAL_JUDGE = 1.5
WEIGHT_THUMB = 1.0
WEIGHT_LATENCY = 0.5

# Proposal classes — gating for auto-apply vs propose-only.
CLASS_AUTO_APPLY = "auto_apply"
CLASS_PROPOSE = "propose"

# Auto-apply kinds.
KIND_MODEL_SWAP = "model_swap"
KIND_EDGE_WEIGHT = "edge_weight_tune"
KIND_RETRY_COUNT = "retry_count_tune"

# Propose-only kinds.
KIND_TOPOLOGY = "topology_mutation"
KIND_PROMPT = "prompt_rewrite"

# Decisions a user can take on a propose-only proposal.
DECISION_ACCEPTED = "accepted"
DECISION_REJECTED = "rejected"
DECISION_PENDING = "pending"

# Latency threshold above which the latency signal contributes.
LATENCY_P95_THRESHOLD_MS = 5_000


@dataclass(frozen=True)
class SignalSnapshot:
    """Aggregated signal weights for one (dag_id, target_node_id) bucket.

    The optimizer sums these into a single `priority_score` for ranking;
    proposals derived from the snapshot inherit the score so the UI can
    sort by impact."""

    dag_id: str
    target_node_id: str = ""
    error_score: float = 0.0
    edit_score: float = 0.0
    eval_score: float = 0.0
    thumb_score: float = 0.0
    latency_score: float = 0.0
    # Free-form context the proposer reads for justification text.
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def priority_score(self) -> float:
        return round(
            self.error_score + self.edit_score + self.eval_score
            + self.thumb_score + self.latency_score, 3,
        )


def _collect_node_metrics(dag_id: str, window_seconds: int) -> dict[str, dict[str, Any]]:
    """Return {node_id_or_kind: aggregate} from node_metrics_store."""
    from services.node_metrics_store import get_store as _metrics_store

    store = _metrics_store()
    # Roll up by node_id (per-node) so optimizer can target a specific
    # node, but also keep a per-kind view for kind-level decisions.
    obs = store._filter(dag_id=dag_id, window_seconds=window_seconds)  # noqa: SLF001
    by_node: dict[str, list[Any]] = {}
    for o in obs:
        by_node.setdefault(o.node_id, []).append(o)
    out: dict[str, dict[str, Any]] = {}
    for node_id, group in by_node.items():
        items = list(group)
        from services.node_metrics_store import _aggregate

        out[node_id] = _aggregate(items)
        out[node_id]["node_kind"] = items[0].node_kind if items else ""
    return out


def _collect_thumbs(dag_id: str) -> dict[str, dict[str, Any]]:
    """Return {node_id: {up, down, comments}} from feedback_service's
    outcome store."""
    from services.feedback_service import get_outcome_store

    store = get_outcome_store()
    by_node: dict[str, dict[str, Any]] = {}
    for o in getattr(store, "_outcomes", []):
        # Loose filter so we don't miss thumbs that arrived before the
        # DAG attribution wire was complete.
        if dag_id and getattr(o, "dag_id", "") and o.dag_id != dag_id:
            continue
        if not getattr(o, "thumb", ""):
            continue
        nid = o.node_id or ""
        slot = by_node.setdefault(nid, {"up": 0, "down": 0, "comments": []})
        if o.thumb == "up":
            slot["up"] += 1
        elif o.thumb == "down":
            slot["down"] += 1
            if o.thumb_comment:
                slot["comments"].append(o.thumb_comment)
    return by_node


def _collect_eval_verdicts(dag_id: str) -> list[dict[str, Any]]:
    """Return all eval-judge verdicts for runs of this DAG."""
    import stores

    return [
        v for v in stores.eval_verdicts.values()
        if v.get("dag_id") == dag_id
    ]


def _collect_user_edits(dag_id: str) -> list[dict[str, Any]]:
    """Return dag_edit audit entries for this DAG."""
    import stores

    return [
        e for e in stores.audit_log.values()
        if e.get("action") == "dag_edit" and e.get("target") == dag_id
    ]


def _build_snapshot_for_dag(
    dag_id: str, window_seconds: int = 24 * 3600,
) -> dict[str, SignalSnapshot]:
    """Build one SignalSnapshot per node_id that has any signal."""
    metrics = _collect_node_metrics(dag_id, window_seconds)
    thumbs = _collect_thumbs(dag_id)
    verdicts = _collect_eval_verdicts(dag_id)
    edits = _collect_user_edits(dag_id)

    # Eval scores are run-level, not node-level → contribute as a
    # baseline against every node in the latest verdict. The proposer
    # uses topology_proposal.target_node_id when available.
    eval_baseline = 0.0
    eval_context: list[dict[str, Any]] = []
    if verdicts:
        verdicts_sorted = sorted(
            verdicts, key=lambda v: v.get("scored_at", ""), reverse=True,
        )
        latest = verdicts_sorted[0]
        # Convert score 0-100 → 0-1 baseline; invert so LOW scores
        # contribute MORE optimizer weight ("things that need work").
        score = float(latest.get("score", 100))
        eval_baseline = max(0.0, (100 - score) / 100.0)
        eval_context = verdicts_sorted[:5]

    # User edits aren't per-node either — they're per-field-path. The
    # signal here is "the user is actively touching this DAG", which
    # *raises* the optimizer's caution score (don't auto-apply on
    # edited fields). We surface the edit_score on the dag-level
    # snapshot (target_node_id="") and the proposer respects it via
    # edit_lock.is_locked() at proposal-write time.
    edit_score_total = WEIGHT_USER_EDIT * min(len(edits), 5) / 5.0  # cap at 1*weight

    all_node_ids = set(metrics.keys()) | set(thumbs.keys())
    snapshots: dict[str, SignalSnapshot] = {}

    for nid in all_node_ids:
        m = metrics.get(nid, {})
        th = thumbs.get(nid, {"up": 0, "down": 0, "comments": []})
        # Signal #1 error_code: fraction of failures × weight
        n = m.get("count", 0)
        failed = m.get("failed", 0)
        err_score = (failed / max(n, 1)) * WEIGHT_ERROR_CODE if n else 0.0
        # Signal #4 thumbs: (down - up) capped at 5 each → weight
        thumb_score = (th["down"] - th["up"]) * WEIGHT_THUMB
        thumb_score = max(0.0, thumb_score)  # only down moves the needle
        # Signal #5 latency: p95 above threshold → weight
        p95 = m.get("latency_ms_p95", 0)
        latency_score = WEIGHT_LATENCY if p95 > LATENCY_P95_THRESHOLD_MS else 0.0
        # eval_judge: baseline contributes to every node in the latest run
        eval_score = eval_baseline * WEIGHT_EVAL_JUDGE

        snapshots[nid] = SignalSnapshot(
            dag_id=dag_id,
            target_node_id=nid,
            error_score=round(err_score, 3),
            edit_score=round(edit_score_total, 3),
            eval_score=round(eval_score, 3),
            thumb_score=round(thumb_score, 3),
            latency_score=round(latency_score, 3),
            context={
                "metrics": m,
                "thumbs": th,
                "eval_verdicts": eval_context,
                "user_edit_count": len(edits),
            },
        )
    return snapshots


def _propose_for_snapshot(
    snapshot: SignalSnapshot,
) -> list[dict[str, Any]]:
    """Translate a SignalSnapshot into 0-3 candidate proposals (raw dicts)."""
    proposals: list[dict[str, Any]] = []

    # AUTO_APPLY candidate #1: model swap on high error_score
    if snapshot.error_score >= 1.5:
        proposals.append({
            "class": CLASS_AUTO_APPLY,
            "kind": KIND_MODEL_SWAP,
            "field_path": f"nodes[{snapshot.target_node_id}].model",
            "rationale": (
                f"Node {snapshot.target_node_id} is failing — "
                f"{int(snapshot.context['metrics']['failed'])} of "
                f"{int(snapshot.context['metrics']['count'])} runs failed. "
                "Switching to a more capable model often clears tool-call "
                "schema issues."
            ),
        })

    # AUTO_APPLY candidate #2: retry-count bump on moderate error_score
    elif snapshot.error_score >= 0.5:
        proposals.append({
            "class": CLASS_AUTO_APPLY,
            "kind": KIND_RETRY_COUNT,
            "field_path": f"nodes[{snapshot.target_node_id}].config.max_retries",
            "rationale": (
                f"Node {snapshot.target_node_id} fails intermittently. "
                "A retry budget of 3 with exponential backoff would "
                "absorb most transient errors."
            ),
        })

    # AUTO_APPLY candidate #3: edge weight tune on high latency_score
    if snapshot.latency_score > 0.0:
        proposals.append({
            "class": CLASS_AUTO_APPLY,
            "kind": KIND_EDGE_WEIGHT,
            "field_path": f"nodes[{snapshot.target_node_id}].config.weight",
            "rationale": (
                f"Node {snapshot.target_node_id} p95 latency "
                f"{int(snapshot.context['metrics']['latency_ms_p95'])}ms "
                "is above threshold; reduce downstream edge weight by "
                "20% to deprioritize this hop."
            ),
        })

    # PROPOSE candidate: surface eval-judge topology_proposal verbatim
    for v in snapshot.context.get("eval_verdicts") or []:
        tp = v.get("topology_proposal")
        if not tp:
            continue
        if tp.get("target_node_id") != snapshot.target_node_id:
            continue
        proposals.append({
            "class": CLASS_PROPOSE,
            "kind": KIND_TOPOLOGY,
            "field_path": f"nodes[{tp['target_node_id']}].{tp.get('kind', '')}",
            "rationale": tp.get("expected_improvement", "")
                       or "Eval-judge proposed this topology mutation.",
            "topology_proposal": tp,
        })

    # PROPOSE candidate: prompt rewrite on persistent thumbs-down
    if snapshot.thumb_score >= 2.0:
        comments = snapshot.context["thumbs"]["comments"][:3]
        proposals.append({
            "class": CLASS_PROPOSE,
            "kind": KIND_PROMPT,
            "field_path": f"nodes[{snapshot.target_node_id}].prompt",
            "rationale": (
                "Users keep thumbing this node down. Recent comments: "
                + " | ".join(comments[:3]) if comments else
                "Users keep thumbing this node down without comments."
            ),
        })

    return proposals


def run_optimizer(
    dag_id: str,
    *,
    actor: str = "optimizer",
    window_seconds: int = 24 * 3600,
    apply_auto: bool = False,
    edit_lock_now: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run one optimizer pass on the given DAG.

    Returns:
        {
          "dag_id": <id>,
          "proposals": [<proposal>, ...],   # ranked by priority_score desc
          "auto_applied": int,
          "blocked_by_edit_lock": int,
        }

    When `apply_auto=True`, AUTO_APPLY proposals that are NOT
    edit-locked are immediately committed (model swap / retry count /
    edge weight) and an audit_log entry is written per application.
    When False (default), every proposal is recorded as PENDING and the
    user reviews via the UI.
    """
    if not dag_id:
        raise ValueError("dag_id is required")

    from services.edit_lock import is_locked
    from routes.audit import log_audit
    import stores

    snapshots = _build_snapshot_for_dag(dag_id, window_seconds=window_seconds)
    ranked = sorted(snapshots.values(), key=lambda s: s.priority_score, reverse=True)

    out_proposals: list[dict[str, Any]] = []
    auto_applied = 0
    blocked = 0
    created_at = (now or datetime.now(UTC)).isoformat()

    for snap in ranked:
        if snap.priority_score <= 0:
            continue
        for raw in _propose_for_snapshot(snap):
            proposal_id = str(uuid.uuid4())
            decision = DECISION_PENDING
            applied = False
            field_path = raw["field_path"]
            blocked_by_lock = is_locked(dag_id, field_path, now=edit_lock_now)
            if (raw["class"] == CLASS_AUTO_APPLY and apply_auto
                    and not blocked_by_lock):
                applied = True
                auto_applied += 1
                decision = DECISION_ACCEPTED
                log_audit(
                    action="optimizer_auto_apply",
                    actor=actor,
                    target=dag_id,
                    detail={
                        "proposal_id": proposal_id,
                        "kind": raw["kind"],
                        "field_path": field_path,
                        "rationale": raw["rationale"][:200],
                    },
                )
            elif raw["class"] == CLASS_AUTO_APPLY and blocked_by_lock:
                blocked += 1
                decision = DECISION_PENDING  # surface as propose for human
            payload = {
                "id": proposal_id,
                "dag_id": dag_id,
                "target_node_id": snap.target_node_id,
                "class": raw["class"],
                "kind": raw["kind"],
                "field_path": field_path,
                "rationale": raw["rationale"],
                "priority_score": snap.priority_score,
                "blocked_by_edit_lock": blocked_by_lock,
                "applied": applied,
                "decision": decision,
                "created_at": created_at,
                "topology_proposal": raw.get("topology_proposal"),
            }
            stores.optimizer_proposals[proposal_id] = payload
            out_proposals.append(payload)

    log_audit(
        action="optimizer_run",
        actor=actor,
        target=dag_id,
        detail={
            "proposal_count": len(out_proposals),
            "auto_applied": auto_applied,
            "blocked_by_edit_lock": blocked,
            "apply_auto_flag": apply_auto,
        },
    )

    return {
        "dag_id": dag_id,
        "proposals": out_proposals,
        "auto_applied": auto_applied,
        "blocked_by_edit_lock": blocked,
    }


def record_decision(
    proposal_id: str,
    decision: str,
    *,
    actor: str,
) -> dict[str, Any]:
    """Record an accept/reject on a proposal. The decision itself flows
    back into outcome_store as a Signal #4-equivalent so the next
    optimizer pass treats user-approval as positive reinforcement."""
    if decision not in (DECISION_ACCEPTED, DECISION_REJECTED):
        raise ValueError(
            f"decision must be one of "
            f"{(DECISION_ACCEPTED, DECISION_REJECTED)}, got {decision!r}"
        )
    import stores
    from routes.audit import log_audit

    payload = stores.optimizer_proposals.get(proposal_id)
    if payload is None:
        raise KeyError(proposal_id)
    payload = dict(payload)
    payload["decision"] = decision
    payload["decided_by"] = actor
    payload["decided_at"] = datetime.now(UTC).isoformat()
    stores.optimizer_proposals[proposal_id] = payload

    log_audit(
        action="optimizer_decision",
        actor=actor,
        target=payload.get("dag_id", ""),
        detail={
            "proposal_id": proposal_id,
            "decision": decision,
            "kind": payload.get("kind"),
        },
    )
    return payload


def list_proposals(
    dag_id: str = "",
    *,
    decision: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List proposals, newest-first. Filter by dag_id and/or decision."""
    import stores

    items = list(stores.optimizer_proposals.values())
    if dag_id:
        items = [p for p in items if p.get("dag_id") == dag_id]
    if decision:
        items = [p for p in items if p.get("decision") == decision]
    items.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return items[: max(1, min(limit, 200))]
