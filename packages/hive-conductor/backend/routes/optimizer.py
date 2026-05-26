"""Phase 6 — Optimizer endpoints.

  POST /v1/optimizer/{dag_id}/run
      Run one optimizer pass. Query: ?apply_auto=false (default).
      Returns the ranked proposal list + auto_applied count.

  GET /v1/optimizer/{dag_id}/proposals
      List proposals for one DAG. Query: ?decision=pending|accepted|rejected.

  GET /v1/optimizer/proposals
      List proposals across all DAGs (newest first).

  POST /v1/optimizer/proposals/{proposal_id}/accept
  POST /v1/optimizer/proposals/{proposal_id}/reject
      Record the user's decision on a propose-only proposal.

Auth: AuthMiddleware. Decisions write audit_log + a Signal #4-equivalent
outcome so user judgment becomes input to the NEXT optimizer pass.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from services.optimizer import (
    DECISION_ACCEPTED,
    DECISION_REJECTED,
    list_proposals,
    record_decision,
    run_optimizer,
)

router = APIRouter(tags=["optimizer"])


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    uid = str(user.get("id") or "")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required")
    return uid


@router.post("/{dag_id}/run")
def trigger_optimizer(
    dag_id: str, request: Request, apply_auto: bool = False,
) -> dict[str, Any]:
    actor = _user_id(request)
    try:
        return run_optimizer(dag_id, actor=actor, apply_auto=apply_auto)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/{dag_id}/proposals")
def list_for_dag(
    dag_id: str, decision: str = "", limit: int = 50,
) -> list[dict[str, Any]]:
    return list_proposals(dag_id=dag_id, decision=decision, limit=limit)


@router.get("/proposals")
def list_all_proposals(
    decision: str = "", limit: int = 50,
) -> list[dict[str, Any]]:
    return list_proposals(decision=decision, limit=limit)


@router.post("/proposals/{proposal_id}/accept")
def accept_proposal(proposal_id: str, request: Request) -> dict[str, Any]:
    actor = _user_id(request)
    try:
        return record_decision(proposal_id, DECISION_ACCEPTED, actor=actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="proposal not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, request: Request) -> dict[str, Any]:
    actor = _user_id(request)
    try:
        return record_decision(proposal_id, DECISION_REJECTED, actor=actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="proposal not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
