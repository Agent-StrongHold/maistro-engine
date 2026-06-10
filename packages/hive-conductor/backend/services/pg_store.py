"""Shared PostgREST persistence for hive stores — chat, memory, credentials."""

import os
import httpx

POSTGREST_URL = os.environ.get("STUDIOSHARE_POSTGREST_URL", "")


async def pg_get(table: str, params: dict) -> list:
    if not POSTGREST_URL:
        return []
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{POSTGREST_URL}/{table}", params=params)
        return r.json() if r.status_code == 200 else []


async def pg_get_one(table: str, params: dict):
    rows = await pg_get(table, {**params, "limit": "1"})
    return rows[0] if rows else None


async def pg_upsert(table: str, data: dict) -> dict | None:
    if not POSTGREST_URL:
        return None
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.post(
            f"{POSTGREST_URL}/{table}", json=data,
            headers={"Prefer": "resolution=merge-duplicates,return=representation", "Content-Type": "application/json"},
        )
        rows = r.json() if r.status_code in (200, 201) else []
        return rows[0] if rows else None


async def pg_insert(table: str, data: dict) -> dict | None:
    if not POSTGREST_URL:
        return None
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.post(
            f"{POSTGREST_URL}/{table}", json=data,
            headers={"Prefer": "return=representation", "Content-Type": "application/json"},
        )
        rows = r.json() if r.status_code in (200, 201) else []
        return rows[0] if rows else None


async def pg_update(table: str, params: dict, data: dict) -> None:
    if not POSTGREST_URL:
        return
    async with httpx.AsyncClient(timeout=5) as c:
        await c.patch(f"{POSTGREST_URL}/{table}", params=params, json=data, headers={"Content-Type": "application/json"})


async def pg_delete(table: str, params: dict) -> None:
    if not POSTGREST_URL:
        return
    async with httpx.AsyncClient(timeout=5) as c:
        await c.delete(f"{POSTGREST_URL}/{table}", params=params)


def is_pg_available() -> bool:
    return bool(POSTGREST_URL)
