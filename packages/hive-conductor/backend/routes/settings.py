from __future__ import annotations

import stores
from fastapi import APIRouter
from models.schemas import SettingsModel
from pydantic import BaseModel, ConfigDict

from routes.audit import log_audit

router = APIRouter(tags=["settings"])


@router.get("", response_model=SettingsModel)
def get_settings() -> SettingsModel:
    return stores.settings


@router.put("", response_model=SettingsModel)
def put_settings(body: SettingsModel) -> SettingsModel:
    stores.settings = body
    log_audit("settings_update", "system", detail=body.model_dump())
    return stores.settings


class PatchSettingsBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    api_base_url: str | None = None
    default_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stream_responses: bool | None = None
    theme: str | None = None
    notifications_enabled: bool | None = None
    auto_save_sessions: bool | None = None
    telemetry_enabled: bool | None = None
    log_level: str | None = None


@router.patch("", response_model=SettingsModel)
def patch_settings(body: PatchSettingsBody) -> SettingsModel:
    updates = body.model_dump(exclude_none=True)
    stores.settings = stores.settings.model_copy(update=updates)
    log_audit("settings_patch", "system", detail=updates)
    return stores.settings


@router.post("/reload")
def reload_settings() -> dict:
    return {"status": "reloaded"}


@router.get("/audit")
def settings_audit() -> list:
    return []


@router.get("/quotas")
def settings_quotas() -> dict:
    return {"providers": []}


@router.get("/models")
def settings_models() -> dict:
    return {"models": [stores.settings.default_model]}


@router.get("/features")
def settings_features() -> dict:
    return {
        "stream_responses": stores.settings.stream_responses,
        "notifications_enabled": stores.settings.notifications_enabled,
        "auto_save_sessions": stores.settings.auto_save_sessions,
        "telemetry_enabled": stores.settings.telemetry_enabled,
    }
