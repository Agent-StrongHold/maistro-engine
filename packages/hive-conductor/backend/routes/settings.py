from __future__ import annotations

from fastapi import APIRouter

from models.schemas import SettingsModel

import stores

router = APIRouter(tags=["settings"])


@router.get("", response_model=SettingsModel)
def get_settings() -> SettingsModel:
    return stores.settings


@router.put("", response_model=SettingsModel)
def put_settings(body: SettingsModel) -> SettingsModel:
    stores.settings = body
    return stores.settings
