from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["quotas"])

ROUTER_BASE = os.environ.get("CONDUCTOR_ROUTER_URL", "http://10.10.42.100:8100")
ROUTER_KEY = os.environ.get("ROUTER_API_KEY", "sk-conductor-router-2026")
TIMEOUT = 8.0


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ROUTER_KEY}"}


def _fallback_providers() -> list[dict]:
    return []


def _fallback_models() -> list[dict]:
    return []


def _fallback_outcomes() -> dict:
    return {"total": 0, "succeeded": 0, "failed": 0, "rate": 0.0, "by_model": {}, "days": 7}


@router.get("/providers")
def list_providers() -> list[dict]:
    try:
        r = httpx.get(f"{ROUTER_BASE}/status/quotas", headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        raw = r.json()
        result = []
        for name, info in raw.items():
            free = info.get("free_tokens", 0)
            used = info.get("used_tokens", 0)
            remaining = info.get("remaining_tokens", free - used)
            limit = free if free < 999_999_999 else None
            result.append({
                "provider": name.title(),
                "status": info.get("status", "active"),
                "billing_cycle": info.get("billing_cycle", "monthly"),
                "cycle_key": info.get("cycle_key", ""),
                "used_tokens": used,
                "free_tokens": free,
                "remaining_tokens": remaining,
                "limit": limit,
                "usage_pct": info.get("usage_pct", 0.0),
                "request_count": info.get("request_count", 0),
                "unit": "tokens",
            })
        return result
    except Exception:
        logger.warning("Failed to fetch quotas from conductor-router, using fallback")
        return _fallback_providers()


@router.get("/outcomes")
def list_outcomes() -> dict:
    try:
        r = httpx.get(f"{ROUTER_BASE}/status/outcomes", headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.warning("Failed to fetch outcomes from conductor-router, using fallback")
        return _fallback_outcomes()


@router.get("/models")
def list_models() -> list[dict]:
    try:
        r = httpx.get(f"{ROUTER_BASE}/status/models", headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        raw = r.json()
        result = []
        for name, info in raw.items():
            result.append({
                "model": name,
                "provider": info.get("provider", "unknown"),
                "tier": info.get("tier", "medium"),
                "quality": info.get("quality", 0.0),
                "speed": info.get("speed", 0),
                "usage_pct": info.get("usage_pct", 0.0),
                "available": info.get("available", True),
                "context": info.get("context"),
                "modality": info.get("modality"),
                "strengths": info.get("strengths", []),
            })
        return result
    except Exception:
        logger.warning("Failed to fetch models from conductor-router, using fallback")
        return _fallback_models()
