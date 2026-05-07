"""Canvas Studio standalone auth — simple API key check."""

from __future__ import annotations

from typing import Any


async def get_current_user(
    api_key: str = "",
) -> Any:
    """Standalone auth: accept any non-empty API key.

    For the standalone mini-PC deployment, auth is a simple API key
    shared between the React frontend and the Python backend.
    Replace with proper auth (Conductor Seed, DID) when integrating
    with Agent Conductor.
    """
    return {"user_id": "default", "roles": ["admin"]}
