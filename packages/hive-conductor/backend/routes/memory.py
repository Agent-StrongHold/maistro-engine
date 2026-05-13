from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from models.schemas import MemoryEntry, MemoryNamespace

import stores

router = APIRouter(tags=["memory"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("/namespaces", response_model=list[MemoryNamespace])
def list_namespaces() -> list[MemoryNamespace]:
    return list(stores.memory_namespaces.values())


@router.get("/entries", response_model=list[MemoryEntry])
def list_entries(namespace: str | None = None) -> list[MemoryEntry]:
    entries = list(stores.memory_entries.values())
    if namespace:
        entries = [e for e in entries if e.namespace == namespace]
    return entries


class PutEntryBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    value: str
    namespace: str = "default"
    tags: list[str] = []


@router.post("/entries", response_model=MemoryEntry)
def create_entry(body: PutEntryBody) -> MemoryEntry:
    eid = str(uuid4())
    t = _now()
    entry = MemoryEntry(
        id=eid,
        key=body.key,
        value=body.value,
        namespace=body.namespace,
        tags=body.tags,
        embedding=None,
        created_at=t,
        updated_at=t,
    )
    stores.memory_entries[eid] = entry
    return entry


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: str) -> None:
    if entry_id not in stores.memory_entries:
        raise HTTPException(status_code=404, detail="not found")
    stores.memory_entries.pop(entry_id)
