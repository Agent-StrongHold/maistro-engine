"""In-memory session collaboration: co-ownership, presence, and a live event stream.

``SessionCollaboration`` is the core primitive behind "Google Docs for agent work":

- **Co-ownership** — a session has members with graded roles (viewer/editor/owner);
  owners manage membership. The last owner cannot be removed or demoted.
- **Presence** — join / heartbeat / leave; each member's state (active/idle/away)
  is derived from time since last seen.
- **Live stream** — every membership, presence, and message change publishes a
  ``CollabEvent`` that is appended to a bounded per-session history and fanned out
  to live subscribers (drive an SSE/WebSocket "shared view" off ``subscribe``,
  using ``history`` for backlog — the standard Last-Event-ID replay pattern).

Async, single-event-loop (consistent with ``InMemorySessionStore``). Persistence
and multi-tenant hardening are Stronghold concerns; core keeps the session-scope
primitive.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable

from maistro.collaboration.types import (
    Action,
    CollabEvent,
    LastOwnerError,
    Member,
    PermissionDenied,
    Presence,
    PresenceState,
    Role,
    role_permits,
)


class SessionCollaboration:
    def __init__(
        self,
        *,
        idle_after: float = 60.0,
        away_after: float = 300.0,
        history_limit: int = 512,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._idle_after = idle_after
        self._away_after = away_after
        self._history_limit = history_limit
        self._clock = clock
        self._members: dict[str, dict[str, Member]] = {}
        self._last_seen: dict[str, dict[str, float]] = {}
        self._history: dict[str, deque[CollabEvent]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[CollabEvent]]] = {}
        self._seq: dict[str, int] = {}

    # --- membership / co-ownership ---------------------------------------

    async def create(self, session_id: str, owner: str) -> Member:
        """Create the collaboration record for a session with ``owner`` as OWNER."""
        member = Member(user_id=owner, role=Role.OWNER, added_by=owner, added_at=self._clock())
        self._members.setdefault(session_id, {})[owner] = member
        await self._publish(session_id, "created", owner, {"role": Role.OWNER})
        return member

    async def share(self, session_id: str, actor: str, target: str, role: Role) -> Member:
        """Grant ``target`` a role on the session. Requires MANAGE."""
        self.require(session_id, actor, Action.MANAGE)
        member = Member(user_id=target, role=role, added_by=actor, added_at=self._clock())
        self._members.setdefault(session_id, {})[target] = member
        await self._publish(session_id, "shared", actor, {"target": target, "role": role})
        return member

    async def set_role(self, session_id: str, actor: str, target: str, role: Role) -> Member:
        """Change ``target``'s role. Requires MANAGE; keeps at least one owner."""
        self.require(session_id, actor, Action.MANAGE)
        members = self._members.get(session_id, {})
        if target not in members:
            raise PermissionDenied(target, Action.VIEW, session_id)
        if members[target].role is Role.OWNER and role is not Role.OWNER:
            self._guard_last_owner(session_id, target)
        member = Member(
            user_id=target, role=role, added_by=actor, added_at=members[target].added_at
        )
        members[target] = member
        await self._publish(session_id, "role_changed", actor, {"target": target, "role": role})
        return member

    async def revoke(self, session_id: str, actor: str, target: str) -> None:
        """Remove ``target`` from the session. Requires MANAGE; keeps at least one owner."""
        self.require(session_id, actor, Action.MANAGE)
        members = self._members.get(session_id, {})
        if target not in members:
            return
        if members[target].role is Role.OWNER:
            self._guard_last_owner(session_id, target)
        del members[target]
        self._last_seen.get(session_id, {}).pop(target, None)
        await self._publish(session_id, "revoked", actor, {"target": target})

    def members(self, session_id: str) -> list[Member]:
        return list(self._members.get(session_id, {}).values())

    def role_of(self, session_id: str, user_id: str) -> Role | None:
        member = self._members.get(session_id, {}).get(user_id)
        return member.role if member is not None else None

    def can(self, session_id: str, user_id: str, action: Action) -> bool:
        role = self.role_of(session_id, user_id)
        return role is not None and role_permits(role, action)

    def require(self, session_id: str, user_id: str, action: Action) -> None:
        if not self.can(session_id, user_id, action):
            raise PermissionDenied(user_id, action, session_id)

    # --- presence --------------------------------------------------------

    async def join(self, session_id: str, user_id: str) -> None:
        self.require(session_id, user_id, Action.VIEW)
        self._last_seen.setdefault(session_id, {})[user_id] = self._clock()
        await self._publish(session_id, "joined", user_id, {})

    async def heartbeat(self, session_id: str, user_id: str) -> None:
        self.require(session_id, user_id, Action.VIEW)
        self._last_seen.setdefault(session_id, {})[user_id] = self._clock()

    async def leave(self, session_id: str, user_id: str) -> None:
        self._last_seen.get(session_id, {}).pop(user_id, None)
        await self._publish(session_id, "left", user_id, {})

    def presence(self, session_id: str) -> list[Presence]:
        now = self._clock()
        out: list[Presence] = []
        for user_id, last in self._last_seen.get(session_id, {}).items():
            age = now - last
            if age >= self._away_after:
                state = PresenceState.AWAY
            elif age >= self._idle_after:
                state = PresenceState.IDLE
            else:
                state = PresenceState.ACTIVE
            out.append(Presence(user_id=user_id, state=state, last_seen=last))
        return out

    # --- activity feed ---------------------------------------------------

    async def post_message(self, session_id: str, actor: str, content: str) -> CollabEvent:
        """Post a collaborator message to the shared feed. Requires EDIT."""
        self.require(session_id, actor, Action.EDIT)
        return await self._publish(
            session_id, "message", actor, {"content": content, "id": uuid.uuid4().hex}
        )

    def history(self, session_id: str, *, after_seq: int = 0) -> list[CollabEvent]:
        return [e for e in self._history.get(session_id, deque()) if e.seq > after_seq]

    async def subscribe(self, session_id: str, user_id: str) -> AsyncIterator[CollabEvent]:
        """Yield live events for a session. Requires VIEW. Use ``history`` for backlog."""
        self.require(session_id, user_id, Action.VIEW)
        queue: asyncio.Queue[CollabEvent] = asyncio.Queue()
        self._subscribers.setdefault(session_id, set()).add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.get(session_id, set()).discard(queue)

    # --- internals -------------------------------------------------------

    def _guard_last_owner(self, session_id: str, target: str) -> None:
        owners = [m for m in self._members.get(session_id, {}).values() if m.role is Role.OWNER]
        if len(owners) <= 1 and any(m.user_id == target for m in owners):
            raise LastOwnerError(f"cannot remove/demote the last owner of {session_id!r}")

    async def _publish(
        self, session_id: str, kind: str, actor: str, data: dict[str, object]
    ) -> CollabEvent:
        seq = self._seq.get(session_id, 0) + 1
        self._seq[session_id] = seq
        event = CollabEvent(
            session_id=session_id,
            kind=kind,
            actor=actor,
            seq=seq,
            ts=self._clock(),
            data=dict(data),
        )
        history = self._history.setdefault(session_id, deque(maxlen=self._history_limit))
        history.append(event)
        for queue in list(self._subscribers.get(session_id, set())):
            queue.put_nowait(event)
        return event
