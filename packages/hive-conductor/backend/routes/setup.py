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
    complete = _is_setup_complete()
    result: dict[str, Any] = {"setup_complete": complete}
    if complete:
        kv = _get_kv()
        if kv is not None and _SETUP_KEY in kv:
            result["config"] = kv[_SETUP_KEY]
    return result


class SetupCompleteBody:
    pass


@router.post("/complete")
def complete_setup(body: dict[str, Any]) -> dict[str, Any]:
    import bcrypt
    import stores

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
    user_did: str | None = None
    if "crypto_identity" in modules:
        try:
            from maistro.identity import ConductorSeed

            seed = ConductorSeed.generate()
            user_did = seed.did_key()
            config_mnemonic = seed.mnemonic_words()
            seed.zero()
        except Exception:
            config_mnemonic = None
    else:
        config_mnemonic = None

    admin_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
    user_hash = bcrypt.hashpw(user_password.encode(), bcrypt.gensalt()).decode()

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

    config = {
        "hardware_preset": hardware_preset,
        "optional_modules": modules,
        "conductor_name": body.get("conductor_name", "Hive Conductor"),
        "default_model": body.get("default_model", "cerebras-qwen-3-235b-a22b-2507"),
        "admin_username": admin_username,
        "user_username": user_username,
        "user_did": user_did,
        "completed_at": now_ts.isoformat(),
    }

    kv = _get_kv()
    if kv is not None:
        kv[_SETUP_KEY] = config

    result = {"setup_complete": True, "config": config}
    if config_mnemonic is not None:
        result["mnemonic"] = config_mnemonic
        result["mnemonic_warning"] = "Write these words down. This is the only time they will be shown. They are your root of trust for everything."
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
