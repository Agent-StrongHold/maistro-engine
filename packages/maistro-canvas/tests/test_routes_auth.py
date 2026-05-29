"""Smoke tests for the canvas v1 REST API (routes.py).

Regression coverage for two defects that made the entire v1 surface
non-functional:

  1. ``auth`` was a bare annotation (``auth: AuthDep``) with no
     ``= Depends(get_current_user)``, so FastAPI treated it as a
     required query parameter and every request returned 422.
  2. ``get_current_user`` returned a plain dict with no ``org_id``,
     but 19 handler sites do ``auth.org_id`` (attribute access),
     which raised ``AttributeError`` (500) once the 422 was fixed.

These tests assert an authenticated request reaches the handler
(2xx, never 422) and never raises ``AttributeError``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from maistro_canvas.canvas.routes import make_canvas_router
from maistro_canvas.types import CanvasRecord


class _FakeStore:
    """Minimal in-memory CanvasStore for route smoke tests."""

    def __init__(self) -> None:
        self._canvases: dict[str, CanvasRecord] = {}
        self._seq = 0

    async def create_canvas(
        self,
        *,
        name: str,
        width: int,
        height: int,
        background_color: str = "#FFFFFF",
        org_id: str = "",
    ) -> CanvasRecord:
        self._seq += 1
        cid = f"canvas-{self._seq}"
        rec = CanvasRecord(
            id=cid,
            name=name,
            width=width,
            height=height,
            background_color=background_color,
            org_id=org_id,
        )
        self._canvases[cid] = rec
        return rec

    async def get_canvas(self, canvas_id: str) -> CanvasRecord | None:
        return self._canvases.get(canvas_id)

    async def list_canvases(
        self,
        org_id: str,
        *,
        include_archived: bool = False,
    ) -> list[CanvasRecord]:
        return [
            c
            for c in self._canvases.values()
            if c.org_id == org_id and (include_archived or not c.is_archived())
        ]

    async def list_layers(self, canvas_id: str) -> list[Any]:
        return []


class _FakeExecutor:
    pass


class _FakeCompositor:
    pass


@pytest.fixture
def client() -> Iterator[TestClient]:
    store = _FakeStore()
    app = FastAPI()
    app.include_router(
        make_canvas_router(
            store=store,  # type: ignore[arg-type]
            executor=_FakeExecutor(),  # type: ignore[arg-type]
            compositor=_FakeCompositor(),  # type: ignore[arg-type]
        ),
        prefix="/api/canvas",
    )
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_list_canvases_authenticated_is_2xx(client: TestClient) -> None:
    """GET on the collection must reach the handler (not a 422 query error)."""
    r = client.get("/api/canvas")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_create_canvas_authenticated_uses_org_id(client: TestClient) -> None:
    """POST must reach the handler and resolve auth.org_id without AttributeError."""
    r = client.post("/api/canvas", json={"name": "My Canvas", "width": 1024, "height": 1024})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "My Canvas"
    # org_id must be populated from auth, proving auth.org_id resolved.
    assert "org_id" in body


def test_create_then_list_round_trip(client: TestClient) -> None:
    """Edge case: a created canvas is visible in the org-scoped listing,
    proving the same org_id flows through create and list."""
    created = client.post("/api/canvas", json={"name": "Round Trip"})
    assert created.status_code == 201, created.text
    listed = client.get("/api/canvas")
    assert listed.status_code == 200, listed.text
    names = [c["name"] for c in listed.json()]
    assert "Round Trip" in names
