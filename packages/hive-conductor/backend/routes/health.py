from __future__ import annotations

import time
from datetime import UTC, datetime

from config import get_settings
from fastapi import APIRouter
from models.schemas import ReadyResponse

_START = time.monotonic()
_STARTED_AT = datetime.now(UTC).isoformat()

router = APIRouter(tags=["health"])


def _llm_state() -> tuple[bool, bool]:
    """`(llm_configured, allow_stub_llm)` — the F3 degraded-mode signal.

    Lazy + defensive on purpose: /health is a public liveness probe (compose
    and the image healthcheck hit it), so it must never fail because a
    settings import blew up. An unreadable state is reported as "degraded",
    never as healthy.
    """
    try:
        from services.graph_runner import llm_gateway_configured, stub_llm_allowed

        return llm_gateway_configured(), stub_llm_allowed()
    except Exception:
        return False, False


def _memory_decay_state() -> dict:
    """Episodic decay state (SPEC-080126-9e42) — the F3 signal for "memory forgets".

    Same defensive contract as `_llm_state`: /health is a liveness probe and must
    never fail because of this. Unreadable state reports as disabled, never as
    healthy — a false "decay is on" would recreate the silent gap it closes.
    """
    try:
        from services.memory_decay import memory_decay_status

        return memory_decay_status()
    except Exception:
        return {"enabled": False, "state": "unavailable"}


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    uptime = time.monotonic() - _START
    try:
        from services.foundation import get_foundation

        f = get_foundation()
        vault_enabled = f.vault_available
        state_enabled = f.state_available
        privilege_available = f.privilege_available
        reactor_available = f.reactor_available
    except RuntimeError:
        vault_enabled = False
        state_enabled = False
        privilege_available = False
        reactor_available = False
    from settings_defaults import is_pm_poc_mode

    llm_configured, allow_stub_llm = _llm_state()
    memory_decay = _memory_decay_state()
    memory_decay_enabled = bool(memory_decay.get("enabled"))

    return {
        "status": "ok",
        "version": "0.9.0",
        "pm_poc_mode": is_pm_poc_mode(),
        "uptime_seconds": uptime,
        "started_at": _STARTED_AT,
        "router_model": settings.chat_default_model,
        "vault_enabled": vault_enabled,
        "state_enabled": state_enabled,
        "privilege_enabled": privilege_available,
        "reactor_enabled": reactor_available,
        # F3: report degradation, do not become an outage. `status` stays "ok"
        # and this endpoint stays 200 — it is the liveness probe.
        "llm_configured": llm_configured,
        "allow_stub_llm": allow_stub_llm,
        # SPEC-080126-9e42: decay off means memory never forgets, which
        # contradicts a documented product behaviour — degraded, never silent.
        "memory_decay": memory_decay,
        "memory_decay_enabled": memory_decay_enabled,
        "degraded": (not llm_configured) or (not memory_decay_enabled),
    }


@router.get("/health/ready")
def ready() -> ReadyResponse:
    try:
        from services.foundation import get_foundation

        f = get_foundation()
        checks = {
            "api": True,
            "vault": f.vault_available,
            "state": f.state_available,
            "privilege": f.privilege_available,
            "reactor": f.reactor_available,
        }
    except RuntimeError:
        checks = {"api": True, "vault": False, "state": False, "privilege": False, "reactor": False}
    # Informational only: `ready` stays keyed on "api" so a missing LLM gateway
    # degrades the conductor without taking it out of rotation.
    checks["llm"] = _llm_state()[0]
    checks["memory_decay"] = bool(_memory_decay_state().get("enabled"))
    return ReadyResponse(ready=checks["api"], checks=checks)
