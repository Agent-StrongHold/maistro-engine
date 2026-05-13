"""Install plan API — parity with `maistro-install --json` when run from monorepo checkout."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["install"])

_SECRETS_DOC = "docs/install/USERS-AND-AGENTS.md"


def _ensure_bootstrap_on_path() -> bool:
    """Resolve `packages/maistro-bootstrap/src` next to this Hive package (monorepo layout)."""
    mono_packages = Path(__file__).resolve().parents[3]
    src = mono_packages / "maistro-bootstrap" / "src"
    if not src.is_dir():
        return False
    s = str(src)
    if s not in sys.path:
        sys.path.insert(0, s)
    return True


def _bootstrap_or_503() -> None:
    if not _ensure_bootstrap_on_path():
        raise HTTPException(
            status_code=503,
            detail=(
                "Install planner requires maistro-bootstrap on disk next to this package "
                "(maistro-engine monorepo checkout). The standalone Hive image does not bundle it."
            ),
        )


@router.get("/session")
def get_install_session() -> dict[str, Any]:
    """Return default answers shape + secrets policy pointer (draft wizard bootstrap)."""
    _bootstrap_or_503()
    from maistro_bootstrap.schema import InstallAnswersV1

    return {
        "kind": "maistro_install_session_template",
        "schema_version": "1",
        "defaults": InstallAnswersV1().model_dump(mode="json"),
        "secrets_policy_doc": _SECRETS_DOC,
        "hint": "POST /v1/install/session with a partial JSON body to merge into defaults and validate.",
    }


@router.post("/session")
def post_install_session(body: dict[str, Any]) -> dict[str, Any]:
    """Merge partial answers with defaults; validates to full InstallAnswersV1 (no plan yet)."""
    _bootstrap_or_503()
    from maistro_bootstrap.schema import merge_session_payload

    answers = merge_session_payload(body)
    return {
        "kind": "maistro_install_session",
        "answers": answers.model_dump(mode="json"),
        "secrets_policy_doc": _SECRETS_DOC,
    }


@router.post("/plan")
def post_install_plan(
    body: dict[str, Any],
    maistro_root: str | None = Query(
        default=None,
        description="Optional maistro-engine root (default: auto-detect MAISTRO_REPO_ROOT / cwd).",
    ),
) -> dict[str, Any]:
    _bootstrap_or_503()
    from maistro_bootstrap.plan import build_install_plan
    from maistro_bootstrap.repo_root import find_maistro_engine_root
    from maistro_bootstrap.schema import parse_answers_dict

    answers = parse_answers_dict(body)
    rr = Path(maistro_root).resolve() if maistro_root else find_maistro_engine_root()
    return build_install_plan(answers, repo_root=rr, copier_dest="../my-product")
