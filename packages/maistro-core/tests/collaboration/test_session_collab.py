"""Tests for session co-ownership, presence, and the live event stream."""

from __future__ import annotations

import asyncio

import pytest

from maistro.collaboration import (
    Action,
    LastOwnerError,
    PermissionDenied,
    PresenceState,
    Role,
    SessionCollaboration,
)


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


async def test_owner_can_share_and_grades_permissions():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")

    assert collab.role_of("s", "alice") is Role.OWNER
    await collab.share("s", actor="alice", target="bob", role=Role.EDITOR)
    await collab.share("s", actor="alice", target="carol", role=Role.VIEWER)

    assert collab.can("s", "bob", Action.EDIT) is True
    assert collab.can("s", "bob", Action.MANAGE) is False
    assert collab.can("s", "carol", Action.EDIT) is False
    assert collab.can("s", "carol", Action.VIEW) is True


async def test_non_owner_cannot_manage():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")
    await collab.share("s", actor="alice", target="bob", role=Role.EDITOR)

    with pytest.raises(PermissionDenied):
        await collab.share("s", actor="bob", target="mallory", role=Role.OWNER)


async def test_non_member_has_no_access():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")
    assert collab.role_of("s", "stranger") is None
    assert collab.can("s", "stranger", Action.VIEW) is False
    with pytest.raises(PermissionDenied):
        collab.require("s", "stranger", Action.VIEW)


async def test_last_owner_cannot_be_revoked_or_demoted():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")

    with pytest.raises(LastOwnerError):
        await collab.revoke("s", actor="alice", target="alice")
    with pytest.raises(LastOwnerError):
        await collab.set_role("s", actor="alice", target="alice", role=Role.EDITOR)

    # With a second owner, the first can step down.
    await collab.share("s", actor="alice", target="bob", role=Role.OWNER)
    await collab.set_role("s", actor="alice", target="alice", role=Role.EDITOR)
    assert collab.role_of("s", "alice") is Role.EDITOR


async def test_presence_states_derive_from_last_seen():
    clock = _Clock()
    collab = SessionCollaboration(idle_after=60, away_after=300, clock=clock)
    await collab.create("s", owner="alice")
    await collab.join("s", "alice")

    assert collab.presence("s")[0].state is PresenceState.ACTIVE
    clock.t += 120  # past idle threshold
    assert collab.presence("s")[0].state is PresenceState.IDLE
    clock.t += 300  # past away threshold
    assert collab.presence("s")[0].state is PresenceState.AWAY

    await collab.heartbeat("s", "alice")  # refreshes
    assert collab.presence("s")[0].state is PresenceState.ACTIVE


async def test_history_and_message_feed_require_edit():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")
    await collab.share("s", actor="alice", target="carol", role=Role.VIEWER)

    with pytest.raises(PermissionDenied):
        await collab.post_message("s", actor="carol", content="hi")

    await collab.post_message("s", actor="alice", content="hello team")
    kinds = [e.kind for e in collab.history("s")]
    assert kinds[0] == "created" and "shared" in kinds and kinds[-1] == "message"
    # after_seq filters the backlog
    tail = collab.history("s", after_seq=1)
    assert all(e.seq > 1 for e in tail)


async def test_live_subscribe_receives_published_events():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")
    agen = collab.subscribe("s", "alice")

    async def first_event():
        return await agen.__anext__()

    task = asyncio.ensure_future(first_event())
    await asyncio.sleep(0)  # let the subscriber register
    await collab.post_message("s", actor="alice", content="live!")

    event = await asyncio.wait_for(task, timeout=1.0)
    assert event.kind == "message" and event.data["content"] == "live!"
    await agen.aclose()


async def test_subscribe_requires_view():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")
    with pytest.raises(PermissionDenied):
        agen = collab.subscribe("s", "stranger")
        await agen.__anext__()


async def test_revoke_editor_and_noop_on_non_member():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")
    await collab.share("s", actor="alice", target="bob", role=Role.EDITOR)

    await collab.revoke("s", actor="alice", target="bob")
    assert collab.role_of("s", "bob") is None
    # revoking someone who isn't a member is a no-op (no raise, no event).
    before = len(collab.history("s"))
    await collab.revoke("s", actor="alice", target="ghost")
    assert len(collab.history("s")) == before


async def test_set_role_on_non_member_denied():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")
    with pytest.raises(PermissionDenied):
        await collab.set_role("s", actor="alice", target="ghost", role=Role.EDITOR)


async def test_revoke_non_last_owner_and_change_non_owner_role():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")
    await collab.share("s", actor="alice", target="bob", role=Role.OWNER)
    await collab.share("s", actor="alice", target="carol", role=Role.EDITOR)

    # Revoking an owner that isn't the last owner is allowed.
    await collab.revoke("s", actor="alice", target="bob")
    assert collab.role_of("s", "bob") is None

    # Changing a non-owner's role skips the last-owner guard entirely.
    await collab.set_role("s", actor="alice", target="carol", role=Role.VIEWER)
    assert collab.role_of("s", "carol") is Role.VIEWER


async def test_leave_updates_presence_and_publishes():
    collab = SessionCollaboration()
    await collab.create("s", owner="alice")
    await collab.join("s", "alice")
    assert collab.presence("s")

    await collab.leave("s", "alice")
    assert collab.presence("s") == []
    assert collab.history("s")[-1].kind == "left"
