"""SQLite persistence for the one live Persona owned by each Workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from maistro.personas.model import Persona
from maistro.personas.store import (
    PersonaAlreadyExists,
    PersonaNotFound,
    WorkspacePersonaAlreadyExists,
)

if TYPE_CHECKING:
    import aiosqlite

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS canonical_personas (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES canonical_workspaces(workspace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_canonical_personas_workspace
    ON canonical_personas(workspace_id);
"""


class SqlitePersonaStore:
    """Durable Persona store enforcing one live Persona per Workspace."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def ensure_schema(self) -> None:
        """Create the canonical Persona table and uniqueness constraint."""

        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def create(self, persona: Persona) -> Persona:
        """Persist a Persona after checking both identity and Workspace uniqueness."""

        if await self.get(persona.id) is not None:
            raise PersonaAlreadyExists(persona.id)
        existing = await self.get_for_workspace(persona.workspace_id)
        if existing is not None:
            raise WorkspacePersonaAlreadyExists(
                f"workspace {persona.workspace_id!r} already owns persona {existing.id!r}"
            )
        await self._conn.execute(
            "INSERT INTO canonical_personas (id, workspace_id, payload) VALUES (?, ?, ?)",
            (persona.id, persona.workspace_id, persona.model_dump_json()),
        )
        await self._conn.commit()
        return persona.model_copy(deep=True)

    async def get(self, persona_id: str) -> Persona | None:
        """Load a Persona by identity."""

        row = await self._fetchone(
            "SELECT payload FROM canonical_personas WHERE id = ?",
            (persona_id,),
        )
        return Persona.model_validate_json(row[0]) if row is not None else None

    async def get_for_workspace(self, workspace_id: str) -> Persona | None:
        """Load the one live Persona owned by a Workspace."""

        row = await self._fetchone(
            "SELECT payload FROM canonical_personas WHERE workspace_id = ?",
            (workspace_id,),
        )
        return Persona.model_validate_json(row[0]) if row is not None else None

    async def update(self, persona: Persona) -> Persona:
        """Update a Persona without allowing it to collide with another Workspace Persona."""

        current = await self.get(persona.id)
        if current is None:
            raise PersonaNotFound(persona.id)
        occupant = await self.get_for_workspace(persona.workspace_id)
        if occupant is not None and occupant.id != persona.id:
            raise WorkspacePersonaAlreadyExists(
                f"workspace {persona.workspace_id!r} already owns persona {occupant.id!r}"
            )
        updated = persona.model_copy(update={"updated_at": datetime.now(UTC)}, deep=True)
        await self._conn.execute(
            """UPDATE canonical_personas
               SET workspace_id = ?, payload = ?
               WHERE id = ?""",
            (updated.workspace_id, updated.model_dump_json(), updated.id),
        )
        await self._conn.commit()
        return updated

    async def delete(self, persona_id: str) -> None:
        """Delete one Persona by identity."""

        if await self.get(persona_id) is None:
            raise PersonaNotFound(persona_id)
        await self._conn.execute("DELETE FROM canonical_personas WHERE id = ?", (persona_id,))
        await self._conn.commit()

    async def _fetchone(
        self,
        sql: str,
        params: tuple[str, ...],
    ) -> tuple[Any, ...] | None:
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return tuple(row) if row is not None else None


__all__ = ["SqlitePersonaStore"]
