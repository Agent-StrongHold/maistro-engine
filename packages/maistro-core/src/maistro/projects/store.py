"""Project persistence — Protocol + in-memory + JSON-file implementations.

The Hive backend wires its own JsonStore-backed implementation against
`stores.projects`; this module provides the contract + a reference
in-memory impl for maistro-core users and tests.

Per-user cap enforced at the store layer (`MAX_PROJECTS_PER_USER`,
configurable via env).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from .types import (
    Project,
    ProjectAccessDenied,
    ProjectMember,
    ProjectMemberRole,
    ProjectNotFound,
    ProjectQuotaExceeded,
)


def _max_projects_per_user() -> int:
    """Default cap. Override via env so ops can lift for power users."""
    try:
        return int(os.environ.get("MAISTRO_MAX_PROJECTS_PER_USER", "10"))
    except ValueError:
        return 10


@runtime_checkable
class ProjectStore(Protocol):
    """Persist + query Project records."""

    async def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        summary: str = "",
        profile_markdown: str = "",
    ) -> Project: ...

    async def get(self, project_id: str) -> Project | None: ...

    async def update(self, project: Project) -> Project: ...

    async def delete(self, project_id: str) -> None: ...

    async def list_for_user(self, user_id: str) -> list[Project]: ...

    async def add_member(
        self, project_id: str, *, user_id: str, role: ProjectMemberRole
    ) -> Project: ...

    async def remove_member(self, project_id: str, *, user_id: str) -> Project: ...


class InMemoryProjectStore:
    """Reference implementation. Tests + ephemeral dev use this."""

    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}

    async def create(
        self,
        *,
        owner_user_id: str,
        name: str,
        summary: str = "",
        profile_markdown: str = "",
    ) -> Project:
        existing = await self.list_for_user(owner_user_id)
        owned = [p for p in existing if p.owner_user_id == owner_user_id]
        if len(owned) >= _max_projects_per_user():
            raise ProjectQuotaExceeded(
                f"user {owner_user_id!r} already owns {_max_projects_per_user()} projects"
            )
        pid = uuid.uuid4().hex[:12]
        now = datetime.now(UTC)
        project = Project(
            id=pid,
            owner_user_id=owner_user_id,
            name=name,
            summary=summary,
            profile_markdown=profile_markdown,
            members=[],
            created_at=now,
            updated_at=now,
        )
        self._projects[pid] = project
        return project.model_copy(deep=True)

    async def get(self, project_id: str) -> Project | None:
        p = self._projects.get(project_id)
        return p.model_copy(deep=True) if p else None

    async def update(self, project: Project) -> Project:
        if project.id not in self._projects:
            raise ProjectNotFound(project.id)
        updated = project.model_copy(update={"updated_at": datetime.now(UTC)})
        self._projects[project.id] = updated
        return updated.model_copy(deep=True)

    async def delete(self, project_id: str) -> None:
        if project_id not in self._projects:
            raise ProjectNotFound(project_id)
        del self._projects[project_id]

    async def list_for_user(self, user_id: str) -> list[Project]:
        """Return all projects the user owns OR is a member of."""
        out = []
        for p in self._projects.values():
            if p.has_member(user_id):
                out.append(p.model_copy(deep=True))
        out.sort(key=lambda p: p.created_at, reverse=True)
        return out

    async def add_member(
        self, project_id: str, *, user_id: str, role: ProjectMemberRole
    ) -> Project:
        p = self._projects.get(project_id)
        if p is None:
            raise ProjectNotFound(project_id)
        if p.has_member(user_id):
            # Idempotent — update role if member already exists.
            new_members = [
                ProjectMember(user_id=user_id, role=role, added_at=m.added_at)
                if m.user_id == user_id
                else m
                for m in p.members
            ]
        else:
            new_members = list(p.members) + [
                ProjectMember(user_id=user_id, role=role)
            ]
        updated = p.model_copy(update={"members": new_members, "updated_at": datetime.now(UTC)})
        self._projects[project_id] = updated
        return updated.model_copy(deep=True)

    async def remove_member(self, project_id: str, *, user_id: str) -> Project:
        p = self._projects.get(project_id)
        if p is None:
            raise ProjectNotFound(project_id)
        if p.owner_user_id == user_id:
            raise ProjectAccessDenied(
                f"cannot remove owner {user_id!r} from project {project_id!r}"
            )
        new_members = [m for m in p.members if m.user_id != user_id]
        updated = p.model_copy(update={"members": new_members, "updated_at": datetime.now(UTC)})
        self._projects[project_id] = updated
        return updated.model_copy(deep=True)
