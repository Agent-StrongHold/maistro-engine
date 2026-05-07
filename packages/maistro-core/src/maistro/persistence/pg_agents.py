"""PostgreSQL agent registry using SQLModel.

Reads and writes agent definitions to the `agents` table.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from maistro.types.agent import AgentIdentity

logger = logging.getLogger("maistro.persistence.pg_agents")


class PgAgentRegistry:
    """CRUD for agent definitions in PostgreSQL via SQLModel."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def list_active(self) -> list[AgentIdentity]:
        """List all active agents."""
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                text("SELECT * FROM agents WHERE active = TRUE ORDER BY name"),
            )
            rows = result.mappings().all()
            return [_coerce_row(r) for r in rows]

    async def get(self, name: str) -> dict[str, Any] | None:
        """Get a single agent by name."""
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                text("SELECT * FROM agents WHERE name = :name"),
                {"name": name},
            )
            row = result.mappings().first()
            return _coerce_row(row) if row else None

    async def upsert(self, record: dict[str, Any]) -> dict[str, Any]:
        """Atomically insert or update an agent definition."""
        record["updated_at"] = datetime.now(UTC)
        async with AsyncSession(self._engine) as session:
            await session.execute(
                text("""
                    INSERT INTO agents (
                        name, version, description, active,
                        created_at, updated_at
                    ) VALUES (
                        :name, :version, :description, :active,
                        :created_at, :updated_at
                    )
                    ON CONFLICT (name) DO UPDATE SET
                        version = EXCLUDED.version,
                        description = EXCLUDED.description,
                        active = EXCLUDED.active,
                        updated_at = EXCLUDED.updated_at
                """),
                record,
            )
            await session.commit()
        return record

    async def count(self) -> int:
        """Count active agents in the database."""
        async with AsyncSession(self._engine) as session:
            result = await session.execute(text("SELECT COUNT(*) FROM agents WHERE active = TRUE"))
            row = result.first()
            return row[0] if row else 0

    async def delete(self, name: str) -> bool:
        """Soft-delete an agent."""
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                text(
                    "UPDATE agents SET active = FALSE, updated_at = NOW()"
                    " WHERE name = :name AND active = TRUE"
                ),
                {"name": name},
            )
            await session.commit()
            return bool(getattr(result, "rowcount", 0) > 0)


def _coerce_row(row: Any) -> dict[str, Any]:
    """Coerce raw SQL row to dict."""
    data = dict(row)
    for field in ("tools", "skills", "model_fallbacks"):
        if data.get(field) is None:
            data[field] = []
    for field in ("config", "model_constraints", "memory_config"):
        if data.get(field) is None:
            data[field] = {}
    return data
