"""SQLite-backed learning store (homelab/single-instance deployments)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from maistro.types.memory import Learning, MemoryScope

if TYPE_CHECKING:
    import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT 'general',
    trigger_keys TEXT NOT NULL DEFAULT '[]',
    learning TEXT NOT NULL DEFAULT '',
    tool_name TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    user_id TEXT,
    scope TEXT NOT NULL DEFAULT 'agent',
    hit_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    rca_category TEXT,
    rca_prevention TEXT NOT NULL DEFAULT '',
    success_after_use INTEGER NOT NULL DEFAULT 0,
    failure_after_use INTEGER NOT NULL DEFAULT 0
)
"""


class SqliteLearningStore:
    """SQLite-backed learning store implementing the same protocol as PgLearningStore."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def ensure_schema(self) -> None:
        """Create the learnings table if it doesn't exist."""
        await self._conn.execute(_SCHEMA)
        await self._conn.commit()

    async def store(self, learning: Learning) -> int:
        """Store a learning. Dedup by tool_name + trigger_key overlap."""
        cursor = await self._conn.execute(
            "SELECT id, trigger_keys FROM learnings WHERE tool_name = ? AND status = 'active'",
            (learning.tool_name,),
        )
        existing = await cursor.fetchall()
        new_keys = set(learning.trigger_keys)
        for row in existing:
            existing_keys = set(json.loads(row[1]))
            if new_keys and existing_keys:
                overlap = len(new_keys & existing_keys) / len(new_keys)
                if overlap >= 0.5:
                    await self._conn.execute(
                        "UPDATE learnings SET hit_count = hit_count + 1 WHERE id = ?",
                        (row[0],),
                    )
                    await self._conn.commit()
                    return int(row[0])

        insert_cursor = await self._conn.execute(
            """INSERT INTO learnings
               (category, trigger_keys, learning, tool_name,
                agent_id, user_id, scope, status,
                rca_category, rca_prevention,
                success_after_use, failure_after_use)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                learning.category,
                json.dumps(list(learning.trigger_keys)),
                learning.learning,
                learning.tool_name,
                learning.agent_id or "",
                learning.user_id,
                learning.scope,
                learning.status,
                learning.rca_category,
                learning.rca_prevention,
                learning.success_after_use,
                learning.failure_after_use,
            ),
        )
        await self._conn.commit()
        return insert_cursor.lastrowid or 0

    async def find_relevant(
        self,
        user_text: str,
        *,
        agent_id: str | None = None,
        org_id: str = "",
        max_results: int = 10,
    ) -> list[Learning]:
        """Find relevant learnings by keyword match."""
        query = "SELECT * FROM learnings WHERE status = 'active'"
        params: list[Any] = []
        if agent_id:
            query += " AND (agent_id = ? OR agent_id = '')"
            params.append(agent_id)

        cursor = await self._conn.execute(query, params)
        columns = [d[0] for d in cursor.description]
        rows = await cursor.fetchall()

        text_lower = user_text.lower()
        scored: list[tuple[float, Learning]] = []
        for raw in rows:
            row = dict(zip(columns, raw, strict=True))
            keys: list[str] = json.loads(row["trigger_keys"])
            score = sum(1 for k in keys if k.lower() in text_lower)
            if score > 0:
                scored.append((float(score), _row_to_learning(row)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [lr for _, lr in scored[:max_results]]

    async def mark_used(self, learning_ids: list[int]) -> None:
        """Increment hit_count for given IDs."""
        if not learning_ids:
            return
        placeholders = ",".join("?" for _ in learning_ids)
        await self._conn.execute(
            f"UPDATE learnings SET hit_count = hit_count + 1 WHERE id IN ({placeholders})",  # nosec B608
            learning_ids,
        )
        await self._conn.commit()

    async def mark_outcome(
        self, learning_ids: list[int], success: bool, *, org_id: str = ""
    ) -> None:
        """Increment success/failure counters per id."""
        if not learning_ids:
            return
        placeholders = ",".join("?" for _ in learning_ids)
        column = "success_after_use" if success else "failure_after_use"
        await self._conn.execute(
            f"UPDATE learnings SET {column} = {column} + 1 WHERE id IN ({placeholders})",  # nosec B608
            learning_ids,
        )
        await self._conn.commit()

    async def check_auto_promotions(
        self,
        threshold: int = 5,
        org_id: str = "",
    ) -> list[Learning]:
        """Promote learnings with hit_count >= threshold."""
        cursor = await self._conn.execute(
            "SELECT id FROM learnings WHERE status = 'active' AND hit_count >= ?",
            (threshold,),
        )
        ids = [r[0] for r in await cursor.fetchall()]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        await self._conn.execute(
            f"UPDATE learnings SET status = 'promoted' WHERE id IN ({placeholders})",  # nosec B608
            ids,
        )
        await self._conn.commit()

        select_cursor = await self._conn.execute(
            f"SELECT * FROM learnings WHERE id IN ({placeholders})",  # nosec B608
            ids,
        )
        columns = [d[0] for d in select_cursor.description]
        rows = await select_cursor.fetchall()
        return [_row_to_learning(dict(zip(columns, r, strict=True))) for r in rows]

    async def get_promoted(
        self,
        task_type: str | None = None,
        org_id: str = "",
    ) -> list[Learning]:
        """Get promoted learnings."""
        query = "SELECT * FROM learnings WHERE status = 'promoted'"
        params: list[Any] = []
        if task_type:
            query += " AND category = ?"
            params.append(task_type)
        cursor = await self._conn.execute(query, params)
        columns = [d[0] for d in cursor.description]
        rows = await cursor.fetchall()
        return [_row_to_learning(dict(zip(columns, r, strict=True))) for r in rows]

    async def list_all(self, org_id: str = "", limit: int = 200) -> list[Learning]:
        """List all learnings (admin endpoint)."""
        cursor = await self._conn.execute(
            "SELECT * FROM learnings ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        columns = [d[0] for d in cursor.description]
        rows = await cursor.fetchall()
        return [_row_to_learning(dict(zip(columns, r, strict=True))) for r in rows]


def _row_to_learning(row: dict[str, Any]) -> Learning:
    return Learning(
        id=row["id"],
        category=row.get("category") or "",
        trigger_keys=json.loads(row.get("trigger_keys") or "[]"),
        learning=row["learning"],
        tool_name=row.get("tool_name") or "",
        agent_id=row.get("agent_id") or None,
        user_id=row.get("user_id"),
        scope=MemoryScope(row.get("scope") or "agent"),
        hit_count=row.get("hit_count", 0),
        status=row.get("status") or "active",
        rca_category=row.get("rca_category"),
        rca_prevention=row.get("rca_prevention") or "",
        success_after_use=row.get("success_after_use", 0),
        failure_after_use=row.get("failure_after_use", 0),
    )
