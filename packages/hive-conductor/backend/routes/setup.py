"""Setup wizard API — persists to SQLite, creates admin + user accounts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["setup"])

_SETUP_KEY = "__hive_setup__"


def _get_kv() -> Any:
    import stores

    return stores.sessions if stores.sessions._persisted else None


def _is_setup_complete() -> bool:
    kv = _get_kv()
    if kv is not None:
        return _SETUP_KEY in kv
    import stores

    return len(stores.users) > 0


@router.get("/status")
def setup_status() -> dict[str, Any]:
    from settings_defaults import is_pm_poc_mode

    complete = _is_setup_complete()
    result: dict[str, Any] = {
        "setup_complete": complete,
        "pm_poc_mode": is_pm_poc_mode(),
    }
    if complete:
        kv = _get_kv()
        if kv is not None and _SETUP_KEY in kv:
            result["config"] = kv[_SETUP_KEY]
    return result


class SetupCompleteBody:
    pass


def _maybe_generate_identity(modules: list[str]) -> tuple[str | None, list[str] | None, str | None]:
    """Generate the ConductorSeed identity root when requested.

    Returns (did, mnemonic_words, unavailable_reason). The operator asked for a
    crypto identity root — a missing `identity` extra must be loud, not a
    silently-None mnemonic (the reveal screen is the only chance to show it).
    """
    if "crypto_identity" not in modules:
        return None, None, None
    try:
        from maistro.identity import ConductorSeed
    except ImportError as exc:
        import logging as _logging

        _logging.getLogger("hive.setup").error(
            "crypto_identity requested but maistro.identity is unavailable: %s", exc
        )
        return None, None, str(exc)
    seed = ConductorSeed.generate()
    user_did = seed.did_key()
    mnemonic = seed.mnemonic_words()
    seed.zero()
    return user_did, mnemonic, None


@router.post("/complete")
def complete_setup(body: dict[str, Any]) -> dict[str, Any]:
    import stores

    from maistro.security.passwords import hash_password

    # /v1/setup/ is a PUBLIC (unauthenticated) prefix. Setup must be a one-shot
    # first-run operation — once complete, re-running it would let any
    # unauthenticated caller overwrite the admin/user credentials (account
    # takeover). Guard with the same check setup_status() reads.
    if _is_setup_complete():
        raise HTTPException(
            status_code=409,
            detail="Setup already complete. This endpoint is disabled after first-run provisioning.",
        )

    hardware_preset = body.get("hardware_preset")
    admin_username = body.get("admin_username", "admin")
    admin_password = body.get("admin_password")
    user_username = body.get("user_username", "user")
    user_password = body.get("user_password")

    if not hardware_preset:
        raise HTTPException(status_code=422, detail="hardware_preset required")
    if not admin_password:
        raise HTTPException(status_code=422, detail="admin_password required")
    if not user_password:
        raise HTTPException(status_code=422, detail="user_password required")

    now_ts = datetime.now(UTC)

    modules = body.get("optional_modules", [])
    user_did, config_mnemonic, identity_unavailable = _maybe_generate_identity(modules)

    admin_hash = hash_password(admin_password)
    user_hash = hash_password(user_password)

    stores.users["admin"] = stores.users._model_class(
        id="admin",
        username=admin_username,
        password_hash=admin_hash,
        role="admin",
        is_active=True,
        created_at=now_ts,
        did=None,
    )
    stores.users["user"] = stores.users._model_class(
        id="user",
        username=user_username,
        password_hash=user_hash,
        role="user",
        is_active=True,
        created_at=now_ts,
        did=user_did,
    )

    # v0 fix: persist the Setup-chosen default_model into stores.settings so
    # the Settings page reflects what the user actually picked (was showing
    # the hardcoded legacy cerebras- alias regardless of Setup choice).
    from config import get_settings

    chosen_default_model = body.get("default_model") or get_settings().chat_default_model
    config = {
        "hardware_preset": hardware_preset,
        "optional_modules": modules,
        "conductor_name": body.get("conductor_name", "Hive Conductor"),
        "default_model": chosen_default_model,
        "admin_username": admin_username,
        "user_username": user_username,
        "user_did": user_did,
        "completed_at": now_ts.isoformat(),
    }

    try:
        stores.settings.default_model = chosen_default_model
    except Exception as exc:
        # best-effort — don't fail Setup over a settings shape mismatch.
        import logging as _logging

        _logging.getLogger("hive.setup").warning(
            "default_model_set_failed: %s",
            exc,
        )

    kv = _get_kv()
    if kv is not None:
        kv[_SETUP_KEY] = config

    result = {"setup_complete": True, "config": config}
    if config_mnemonic is not None:
        result["mnemonic"] = config_mnemonic
        result["mnemonic_warning"] = (
            "Write these words down. This is the only time they will be shown. They are your root of trust for everything."
        )
    if identity_unavailable is not None:
        result["identity_unavailable"] = identity_unavailable
    return result


@router.get("/presets")
def list_presets() -> dict[str, Any]:
    from maistro.config.presets import HARDWARE_PRESETS

    return {
        "kind": "hardware_presets",
        "presets": {
            name: {
                "name": p.name,
                "label": p.label,
                "description": p.description,
                "max_vcpu": p.max_vcpu,
                "max_memory_gb": p.max_memory_gb,
                "db_backend": p.db_backend,
                "networking": p.networking,
                "gpu_available": p.gpu_available,
                "reactor_enabled": p.reactor_enabled,
                "max_agents": p.max_agents,
            }
            for name, p in HARDWARE_PRESETS.items()
        },
    }


@router.get("/presets/{preset_name}")
def get_preset(preset_name: str) -> dict[str, Any]:
    from maistro.config.presets import HARDWARE_PRESETS

    p = HARDWARE_PRESETS.get(preset_name)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")
    return {"kind": "hardware_preset", **p.model_dump()}


@router.post("/presets/resolve")
def resolve_preset_auto(body: dict[str, Any] | None = None) -> dict[str, Any]:
    from maistro.config.presets import resolve_preset

    body = body or {}
    name = body.get("name", "auto")
    total_memory_gb = body.get("total_memory_gb")
    p = resolve_preset(name=name, total_memory_gb=total_memory_gb)
    return {
        "kind": "resolved_preset",
        "preset": p.name,
        "config": p.to_config(),
    }
