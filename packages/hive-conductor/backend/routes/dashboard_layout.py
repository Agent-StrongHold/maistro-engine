"""Dashboard layout persistence — per-user widget configuration.

Uses the same SQLite persistence layer as the rest of Hive's stores.
Falls back to in-memory if persistence isn't configured.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import ClassVar

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])
logger = logging.getLogger("hive.dashboard")

# SQLite-backed file (same dir as other Hive state)
_DB_PATH = Path("data/dashboard_layouts.json")
_LAYOUTS: dict[str, dict] = {}


def _load_from_disk() -> None:
    """Load persisted layouts on startup."""
    if _DB_PATH.is_file():
        try:
            _LAYOUTS.update(json.loads(_DB_PATH.read_text()))
        except Exception as e:
            logger.warning("Failed to load dashboard layouts: %s", e)


def _save_to_disk() -> None:
    """Persist layouts to disk."""
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DB_PATH.write_text(json.dumps(_LAYOUTS, indent=2))
    except Exception as e:
        logger.warning("Failed to save dashboard layouts: %s", e)


# Load on import
_load_from_disk()


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    return str(user.get("id") or user.get("username") or "dev")


class WidgetConfig(BaseModel):
    id: str
    type: str
    title: str
    size: str = "1"
    config: dict | None = None


class DashboardLayout(BaseModel):
    model_config: ClassVar[dict] = {"extra": "allow"}
    widgets: list[WidgetConfig] = []
    tabs: list[dict] = []
    activeTab: int = 0
    updatedAt: str = ""


@router.get("/layout")
async def get_layout(request: Request) -> dict:
    """Get the current user's dashboard layout. Seeds preset for known users."""
    uid = _user_id(request)
    if uid not in _LAYOUTS:
        preset = _PRESETS.get(uid)
        if preset:
            demo_path = Path(__file__).parent.parent / "data" / "demo_dashboards" / f"{preset}.json"
            if demo_path.is_file():
                try:
                    _LAYOUTS[uid] = json.loads(demo_path.read_text())
                    _save_to_disk()
                except Exception:
                    pass
    return _LAYOUTS.get(uid, {"widgets": []})


# Users with pre-configured dashboard templates (loaded on first access)
_PRESETS: dict[str, str] = {
    "carlos": "portfolio-overview",
}


@router.put("/layout")
async def save_layout(request: Request, body: DashboardLayout) -> dict:
    """Save the current user's dashboard layout."""
    uid = _user_id(request)
    _LAYOUTS[uid] = body.model_dump()
    _save_to_disk()
    return {"ok": True}


@router.get("/metrics")
async def get_metrics() -> dict:
    """Get live chat completion metrics."""
    from services.chat_completion import get_chat_metrics_summary

    return get_chat_metrics_summary()


@router.get("/widget-examples")
async def get_widget_examples(category: str | None = None) -> list[dict]:
    """Return curated widget example templates."""
    from pathlib import Path

    path = Path(__file__).parent.parent / "data" / "widget_examples.json"
    try:
        examples = json.loads(path.read_text())
    except Exception:
        return []
    if category:
        examples = [e for e in examples if category.lower() in e.get("category", "").lower()]
    return examples


@router.get("/demos")
async def list_demo_dashboards() -> list[dict]:
    """List available demo dashboard templates."""
    from pathlib import Path

    demos_dir = Path(__file__).parent.parent / "data" / "demo_dashboards"
    if not demos_dir.exists():
        return []
    results = []
    for f in sorted(demos_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            results.append(
                {
                    "id": f.stem,
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "widget_count": len(data.get("widgets", [])),
                }
            )
        except Exception:
            continue
    return results


@router.get("/demos/{demo_id}")
async def get_demo_dashboard(demo_id: str) -> dict:
    """Load a demo dashboard template."""
    from pathlib import Path

    path = Path(__file__).parent.parent / "data" / "demo_dashboards" / f"{demo_id}.json"
    if not path.exists():
        return {"error": "not found"}
    return json.loads(path.read_text())
