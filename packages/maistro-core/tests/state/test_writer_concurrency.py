"""Writer-thread concurrency and shutdown ordering (review findings H6, H7).

`State` shares one `check_same_thread=False` SQLite connection between the
background writer thread and any caller of `run_migration`/`backup`. It created
a `_writer_lock` for that and then never acquired it anywhere in the file, and
`close()` signalled shutdown before draining.

The existing 52 tests in this directory are functional, not concurrent — they
exercise one thread at a time, which is why both defects survived them.
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path

import pytest

from maistro.state import MigrationFailedError, State


@pytest.fixture
def state(tmp_path: Path):
    st = State(str(tmp_path / "state.db"))
    st.open_writer()
    yield st
    with contextlib.suppress(Exception):
        st.close()


@pytest.mark.contract("durability")
@pytest.mark.scope("unit")
def test_close_drains_queued_writes(state: State) -> None:
    """H7: `close()` must not discard work that was already accepted.

    Fails without the fix: `_shutdown` was set before the sentinel was
    enqueued, so `_writer_loop` exited at its next guard check and the queued
    inserts were dropped. `PersistedStore.put` is fire-and-forget, so nothing
    told the caller.
    """
    state.run_migration("kv", "CREATE TABLE IF NOT EXISTS t (k TEXT PRIMARY KEY, v TEXT NOT NULL)")

    expected = 200
    for i in range(expected):
        state.submit(
            lambda conn, i=i: conn.execute("INSERT INTO t (k, v) VALUES (?, ?)", (str(i), "x"))
        )

    state.close()

    # Re-open and count. Anything missing was accepted and then thrown away.
    reopened = State(str(state._db_path))
    conn = reopened.open_reader()
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM t").fetchone()
    finally:
        conn.close()
        reopened.close()

    assert count == expected, f"close() dropped {expected - count} of {expected} accepted writes"


# H6 is a race, and a race is a bad assertion: a "hammer a background writer
# while a migration fails" test passes against the *unfixed* code most runs,
# because it only detects the bug when the interleaving happens to land inside
# the savepoint. That is precisely the shape of test that reports green while
# asserting nothing. So the two tests below assert the *mutual exclusion* that
# makes the race impossible, deterministically, by holding `_writer_lock` and
# observing that the other party blocks.


@pytest.mark.contract("durability")
@pytest.mark.scope("unit")
def test_writer_loop_respects_the_lock(state: State) -> None:
    """H6, half one: the writer thread must not commit while the lock is held.

    Fails without the fix: `_writer_loop` never acquired `_writer_lock`, so the
    transaction lands immediately and `done` is set well inside the window.
    That commit is what escapes a migration's SAVEPOINT.
    """
    state.run_migration("base", "CREATE TABLE base (k TEXT PRIMARY KEY)")

    done = threading.Event()
    with state._writer_lock:
        state.submit(lambda conn: conn.execute("INSERT INTO base (k) VALUES ('a')"))
        state.submit(lambda conn: done.set())
        landed_while_locked = done.wait(timeout=1.0)

    assert not landed_while_locked, (
        "the writer thread committed while _writer_lock was held — it is not "
        "taking the lock, so a background commit can land inside a migration's "
        "savepoint"
    )
    assert done.wait(timeout=5.0), "the writer thread did not resume once the lock was released"


@pytest.mark.contract("durability")
@pytest.mark.scope("unit")
def test_run_migration_takes_the_lock(state: State) -> None:
    """H6, half two: the migration must hold the lock for its whole savepoint.

    Fails without the fix: `run_migration` touched the shared connection with no
    lock at all, so it completes immediately here.
    """
    state.run_migration("base", "CREATE TABLE base (k TEXT PRIMARY KEY)")

    finished = threading.Event()

    def migrate() -> None:
        state.run_migration("later", "CREATE TABLE later_table (k TEXT)")
        finished.set()

    with state._writer_lock:
        t = threading.Thread(target=migrate, daemon=True)
        t.start()
        ran_while_locked = finished.wait(timeout=1.0)

    assert not ran_while_locked, (
        "run_migration proceeded while _writer_lock was held — it is not taking "
        "the lock, so the writer thread can commit inside its savepoint"
    )
    assert finished.wait(timeout=5.0), "the migration did not proceed once the lock was released"
    t.join(timeout=5.0)


@pytest.mark.contract("durability")
@pytest.mark.scope("unit")
def test_failed_migration_leaves_schema_unchanged(state: State) -> None:
    """`MigrationFailedError` promises the database is unchanged. Verify it."""
    state.run_migration("base", "CREATE TABLE base (k TEXT PRIMARY KEY)")

    with pytest.raises(MigrationFailedError):
        state.run_migration(
            "half_bad",
            "CREATE TABLE survivor (k TEXT); THIS IS NOT VALID SQL",
        )

    conn = state.open_reader()
    try:
        found = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='survivor'"
        ).fetchone()
    finally:
        conn.close()

    assert found is None, "a failed migration left the `survivor` table behind"


@pytest.mark.contract("durability")
@pytest.mark.scope("unit")
def test_migration_is_applied_once_under_concurrent_callers(state: State) -> None:
    """The existence check must be inside the lock, or two racers both pass it."""
    state.run_migration("base", "CREATE TABLE base (k TEXT PRIMARY KEY)")

    errors: list[Exception] = []
    barrier = threading.Barrier(4)

    def run() -> None:
        barrier.wait()
        try:
            state.run_migration("once", "CREATE TABLE once_only (k TEXT)")
        except Exception as exc:  # a second CREATE would raise "already exists"
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not errors, f"concurrent callers double-applied the migration: {errors}"


@pytest.mark.contract("durability")
@pytest.mark.scope("unit")
def test_close_is_idempotent(state: State) -> None:
    """`close()` is called from finalizers and shutdown hooks alike."""
    state.close()
    state.close()
