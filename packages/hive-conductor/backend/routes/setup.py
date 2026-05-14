"""Setup wizard API — hardware presets and initial configuration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["setup"])


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
        from fastapi import HTTPException

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
