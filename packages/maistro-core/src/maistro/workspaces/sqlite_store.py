"""SQLite persistence for canonical Workspace identity and membership."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from maistro.projects.scope_store import ProjectScopeStore
from maistro.workspaces.model import (
    Workspace,
    WorkspaceAccessDenied,
    WorkspaceMembership,
    WorkspaceNotFound,
    WorkspaceRole,
)

if TYPE_CHECKING:
    import aiosqlite

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS canonical_workspaces (
    workspace_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_workspace_memberships (
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (workspace_id, user_id),
    FOREIGN KEY (workspace_id) REFERENCES canonical_workspaces(workspace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_canonical_workspace_memberships_user
    ON canonical_workspace_memberships(user_id, workspace_id);
"""


class SqliteWorkspaceStore:
    """Durable Workspace store that provisions the canonical Root Project."""

    def __init__(self, conn: aiosqlite.Connection, *, project_store: ProjectScopeStore) -> None:
        self._conn = conn
        self.project_store = project_store

    async def ensure_schema(self) -> None:
        """Create canonical Workspace and membership tables."""

        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def create(
        self,
        *,
        creator_user_id: str,
        name: str,
        description: str = "",
    ) -> Workspace:
        """Persist a Workspace, its owner membership, and exactly one Root Project."""

        workspace = Workspace(name=name, description=description)
        owner = WorkspaceMembership(
            workspace_id=workspace.workspace_id,
            user_id=creator_user_id,
            role=WorkspaceRole.OWNER,
            added_at=workspace.created_at,
        )
        try:
            await self._conn.execute(
                "INSERT INTO canonical_workspaces (workspace_id, payload) VALUES (?, ?)",
                (workspace.workspace_id, workspace.model_dump_json()),
            )
            await self._conn.execute(
                """INSERT INTO canonical_workspace_memberships
                   (workspace_id, user_id, role, payload)
                   VALUES (?, ?, ?, ?)""",
                (
                    owner.workspace_id,
                    owner.user_id,
                    owner.role.value,
                    owner.model_dump_json(),
                ),
            )
            await self.project_store.create_root(workspace.workspace_id)
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise
        return workspace

    async def get(self, workspace_id: str) -> Workspace | None:
        """Load a Workspace by identity."""

        row = await self._fetchone(
            "SELECT payload FROM canonical_workspaces WHERE workspace_id = ?",
            (workspace_id,),
        )
        return Workspace.model_validate_json(row[0]) if row is not None else None

    async def update(self, workspace: Workspace) -> Workspace:
        """Replace mutable Workspace fields while preserving identity."""

        await self._require_workspace(workspace.workspace_id)
        updated = workspace.model_copy(update={"updated_at": datetime.now(UTC)}, deep=True)
        await self._conn.execute(
            "UPDATE canonical_workspaces SET payload = ? WHERE workspace_id = ?",
            (updated.model_dump_json(), updated.workspace_id),
        )
        await self._conn.commit()
        return updated

    async def delete(self, workspace_id: str) -> None:
        """Remove one Workspace and all canonical scope-tree state it owns."""

        await self._require_workspace(workspace_id)
        try:
            await self._purge_project_scope(workspace_id)
            await self._conn.execute(
                "DELETE FROM canonical_workspaces WHERE workspace_id = ?",
                (workspace_id,),
            )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    async def list_for_user(self, user_id: str) -> list[Workspace]:
        """List Workspaces visible through explicit WorkspaceMembership."""

        cursor = await self._conn.execute(
            """SELECT w.payload
               FROM canonical_workspaces AS w
               JOIN canonical_workspace_memberships AS m
                 ON m.workspace_id = w.workspace_id
               WHERE m.user_id = ?""",
            (user_id,),
        )
        rows = await cursor.fetchall()
        workspaces = [Workspace.model_validate_json(row[0]) for row in rows]
        workspaces.sort(key=lambda item: item.created_at, reverse=True)
        return workspaces

    async def list_memberships(self, workspace_id: str) -> list[WorkspaceMembership]:
        """List all explicit memberships for a Workspace."""

        await self._require_workspace(workspace_id)
        cursor = await self._conn.execute(
            "SELECT payload FROM canonical_workspace_memberships WHERE workspace_id = ?",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        memberships = [WorkspaceMembership.model_validate_json(row[0]) for row in rows]
        memberships.sort(key=lambda item: (item.added_at, item.user_id))
        return memberships

    async def get_membership(
        self,
        workspace_id: str,
        *,
        user_id: str,
    ) -> WorkspaceMembership | None:
        """Load one Workspace membership when present."""

        await self._require_workspace(workspace_id)
        row = await self._fetchone(
            """SELECT payload FROM canonical_workspace_memberships
               WHERE workspace_id = ? AND user_id = ?""",
            (workspace_id, user_id),
        )
        return WorkspaceMembership.model_validate_json(row[0]) if row is not None else None

    async def set_membership(
        self,
        workspace_id: str,
        *,
        user_id: str,
        role: WorkspaceRole,
    ) -> WorkspaceMembership:
        """Create or replace a membership without allowing an ownerless Workspace."""

        await self._require_workspace(workspace_id)
        existing = await self.get_membership(workspace_id, user_id=user_id)
        if (
            existing is not None
            and existing.role is WorkspaceRole.OWNER
            and role is not WorkspaceRole.OWNER
        ):
            await self._ensure_another_owner(workspace_id, excluding_user_id=user_id)

        membership = WorkspaceMembership(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            added_at=existing.added_at if existing is not None else datetime.now(UTC),
        )
        await self._conn.execute(
            """INSERT INTO canonical_workspace_memberships
               (workspace_id, user_id, role, payload)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(workspace_id, user_id) DO UPDATE SET
                 role = excluded.role,
                 payload = excluded.payload""",
            (
                membership.workspace_id,
                membership.user_id,
                membership.role.value,
                membership.model_dump_json(),
            ),
        )
        await self._conn.commit()
        return membership

    async def remove_membership(self, workspace_id: str, *, user_id: str) -> None:
        """Remove a membership while guaranteeing that at least one owner remains."""

        await self._require_workspace(workspace_id)
        existing = await self.get_membership(workspace_id, user_id=user_id)
        if existing is None:
            return
        if existing.role is WorkspaceRole.OWNER:
            await self._ensure_another_owner(workspace_id, excluding_user_id=user_id)
        await self._conn.execute(
            """DELETE FROM canonical_workspace_memberships
               WHERE workspace_id = ? AND user_id = ?""",
            (workspace_id, user_id),
        )
        await self._conn.commit()

    async def _require_workspace(self, workspace_id: str) -> Workspace:
        workspace = await self.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFound(workspace_id)
        return workspace

    async def _ensure_another_owner(self, workspace_id: str, *, excluding_user_id: str) -> None:
        row = await self._fetchone(
            """SELECT 1 FROM canonical_workspace_memberships
               WHERE workspace_id = ? AND user_id != ? AND role = ? LIMIT 1""",
            (workspace_id, excluding_user_id, WorkspaceRole.OWNER.value),
        )
        if row is None:
            raise WorkspaceAccessDenied("a Workspace must retain at least one owner")

    async def _purge_project_scope(self, workspace_id: str) -> None:
        """Purge a Workspace's canonical Project tree during Workspace teardown only."""

        await self._conn.execute(
            "DELETE FROM canonical_project_resources WHERE workspace_id = ?",
            (workspace_id,),
        )
        await self._conn.execute(
            "DELETE FROM canonical_project_memberships WHERE workspace_id = ?",
            (workspace_id,),
        )

        cursor = await self._conn.execute(
            """SELECT project_id, parent_project_id
               FROM canonical_projects WHERE workspace_id = ?""",
            (workspace_id,),
        )
        rows = await cursor.fetchall()
        remaining = {str(row[0]): (str(row[1]) if row[1] is not None else None) for row in rows}
        while remaining:
            parent_ids = {parent_id for parent_id in remaining.values() if parent_id is not None}
            leaves = [project_id for project_id in remaining if project_id not in parent_ids]
            if not leaves:
                raise RuntimeError("canonical Project tree contains a cycle during Workspace purge")
            await self._conn.executemany(
                "DELETE FROM canonical_projects WHERE project_id = ?",
                [(project_id,) for project_id in leaves],
            )
            for project_id in leaves:
                del remaining[project_id]

    async def _fetchone(
        self,
        sql: str,
        params: tuple[str, ...],
    ) -> tuple[Any, ...] | None:
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return tuple(row) if row is not None else None


__all__ = ["SqliteWorkspaceStore"]
