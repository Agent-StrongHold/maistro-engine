# Phase 2: Memory Layer

**Goal:** Full episodic memory with SQLite (dev/test) and PostgreSQL (prod).
Two-phase budget retrieval, write paths, working memory, rewards.

**Depends on:** Phase 1 (types, protocols, tiers, reactor) — complete.

---

## 1. Source Inventory

| Source file | Lines | Description |
|------------|-------|-------------|
| `turing/repo.py` | 529 | SQLite-backed `Repo` class; INV-1..8 invariants |
| `turing/postgres_repo.py` | 434 | PostgreSQL-backed `PostgresRepo` |
| `turing/retrieval.py` | 235 | Two-phase budget retrieval + `retrieve_head`/`retrieve_history` |
| `turing/rewards.py` | 126 | `RewardTracker` — human feedback reward system |
| `turing/write_paths.py` | 189 | REGRET/ACCOMPLISHMENT/AFFIRMATION write handlers |
| `turing/working_memory.py` | 143 | `WorkingMemory` — bounded priority scratchpad |
| `turing/schema.sql` | 558 | SQLite DDL (episodic_memory, durable_memory, self-model tables) |
| `turing/postgres_schema.sql` | 150 | PostgreSQL DDL (triggers, CHECKs) |
| **Total** | **~2,364** | |

| Source test file | Lines | Key ACs covered |
|-----------------|-------|----------------|
| `tests/test_invariants.py` | 148 | AC-3.1..3.8 (durability invariants — already partially ported in Phase 1) |
| `tests/test_retrieval.py` | 156 | AC-6.1..6.5 |
| `tests/test_write_paths.py` | 165 | AC-4.1..4.6 |
| `tests/test_working_memory.py` | 134 | Working memory CRUD + eviction |
| `tests/test_persistence.py` | 151 | AC-8.1..8.7 (restart, schema, durability) |
| `tests/test_rewards.py` | 113 | Reward tracking |
| `tests/test_postgres_repo.py` | 249 | PostgreSQL round-trips |
| `tests/test_schema.py` | 121 | Schema validation |
| **Total** | **~1,237** | |

## 2. Target File Mapping

| Source | Target |
|--------|--------|
| `turing/repo.py` | `maistro_turing/memory/repo.py` |
| `turing/postgres_repo.py` | `maistro_turing/memory/postgres_repo.py` |
| `turing/retrieval.py` | `maistro_turing/memory/retrieval.py` |
| `turing/rewards.py` | `maistro_turing/memory/rewards.py` |
| `turing/write_paths.py` | `maistro_turing/memory/write_paths.py` |
| `turing/working_memory.py` | `maistro_turing/memory/working_memory.py` |
| `turing/schema.sql` | `maistro_turing/schema/sqlite.sql` |
| `turing/postgres_schema.sql` | `maistro_turing/schema/postgres.sql` |

## 3. Acceptance Criteria

### AC-5: Repo INV-1..8 durability invariants (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-5.1 | behavioral | Memory inserted with tier in `DURABLE_TIERS` | `decay_weight` returns value >= tier floor | Weight never drops below `WEIGHT_BOUNDS[tier][0]` |
| AC-5.2 | behavioral | Memory with `immutable=True` | `soft_delete` raises `ImmutableViolation` | Durable memories are never soft-deleted |
| AC-5.3 | behavioral | Memory with `immutable=True` | SQL DELETE on `durable_memory` raises `IntegrityError` | Durable table is append-only |
| AC-5.4 | behavioral | Memory with tier in `DURABLE_TIERS` | Constructor rejects `source != I_DID` | Durable memories require `source=i_did` |
| AC-5.5 | behavioral | Two memories, second supersedes first | First has `superseded_by` set, `contradiction_count` incremented | Contradiction tracking is atomic |
| AC-5.6 | boundary | `EpisodicMemory` with `immutable=True` | `AttributeError` on field mutation | Frozen fields cannot be mutated |
| AC-5.7 | boundary | `self_id=""` on construction | `ValueError("self_id is required")` | self_id is non-empty |
| AC-5.8 | behavioral | `insert(m)` then `get(m.memory_id)` | Returned memory equals `m` on all identity fields | Insert/get round-trip preserves data |

### AC-6: Two-phase budget retrieval (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-6.1 | behavioral | Mix of durable + non-durable memories, tiny budget | At least one durable survives | Reserved quota favors durable |
| AC-6.2 | behavioral | One small durable, many non-durable, large budget | `len(results) > 1` | Unused durable quota released to non-durable |
| AC-6.3 | behavioral | Memories with mixed `SourceKind` values, `source_filter=(I_DID,)` | All results have `source=I_DID` | Source filter excludes others |
| AC-6.4 | behavioral | No explicit `source_filter` | Default is `(I_DID,)` | Default source is I_DID only |
| AC-6.5 | behavioral | Chain A→B→C (supersedes links) | `retrieve_head(A)` returns C, `retrieve_history(C)` returns [A,B,C] | Lineage walk is correct |

### AC-7: Working memory scratchpad (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-7.1 | behavioral | `add(self_id, content)` | `entries(self_id)` includes entry with correct content and default priority 0.5 | Add/entries round-trip |
| AC-7.2 | behavioral | `entries(self_id)` with multiple entries | Sorted by priority descending | Entries always sorted |
| AC-7.3 | boundary | `add(self_id, content)` with `len(content) > MAX_CONTENT_LEN` | Stored content truncated to `MAX_CONTENT_LEN` | Content length bounded |
| AC-7.4 | boundary | `add(self_id, "   ")` | `ValueError("empty")` | Whitespace-only content rejected |
| AC-7.5 | boundary | `add(self_id, "x", priority=1.5)` | `ValueError("priority")` | Priority must be in [0, 1] |
| AC-7.6 | behavioral | Add more than `MAX_ENTRIES` entries | `len(entries) <= MAX_ENTRIES`, lowest priority evicted | Capacity eviction preserves highest priority |
| AC-7.7 | behavioral | `remove(self_id, entry_id)` on existing | Returns `True`, entry gone | Remove works |
| AC-7.8 | behavioral | `remove(self_id, "nonexistent")` | Returns `False` | Remove unknown is idempotent |
| AC-7.9 | behavioral | `update_priority(self_id, entry_id, priority=0.8)` | Returns `True`, entry has new priority | Priority update works |
| AC-7.10 | behavioral | `clear(self_id)` with N entries | Returns N, `entries()` is empty | Clear removes all |
| AC-7.11 | behavioral | `render(self_id)` when empty | Contains "empty" | Render signals emptiness |
| AC-7.12 | behavioral | `render(self_id)` with high-priority entry | High priority marked with "★" | Render marks priority |
| AC-7.13 | behavioral | Two different `self_id` values | Each sees only its own entries | Self-id isolation |

### AC-8: Persistence (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-8.1 | boundary | `PRAGMA table_info(durable_memory)` | No `deleted` column in schema | Durable table has no soft-delete column |
| AC-8.2 | behavioral | Durable memory inserted | SQL DELETE raises `IntegrityError` | Durable is append-only |
| AC-8.3 | behavioral | Insert durable, close repo, reopen | Memory still present | Restart preserves durable data |
| AC-8.4 | behavioral | `close()` called twice | No error | Close is idempotent |
| AC-8.5 | behavioral | `find()` with no filters | Returns all non-deleted memories | Default find returns everything |
| AC-8.6 | behavioral | `find(tier=X)` | Returns only memories with tier X | Tier filter works |
| AC-8.7 | behavioral | `count_by_tier(X)` | Returns exact count of tier X memories | Count is accurate |

### AC-9: Reward tracking (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-9.1 | behavioral | `award("chat", "m1", "creation")` | Returns 5, `total_points() == 5` | Chat creation = 5 points |
| AC-9.2 | behavioral | `award("chat", "m1", "thumbs_up")` | Returns 10 | Chat thumbs_up = 10 points |
| AC-9.3 | behavioral | `award("chat", "m1", "thumbs_down")` | Returns -20 | Chat thumbs_down = -20 points |
| AC-9.4 | behavioral | `award("blog", "p1", "thumbs_up")` | Returns 100 | Blog thumbs_up = 100 points |
| AC-9.5 | behavioral | `award("blog", "p1", "thumbs_down")` | Returns -200 | Blog thumbs_down = -200 points |
| AC-9.6 | behavioral | Multiple awards across interfaces | `total_points()` equals sum | Points accumulate correctly |
| AC-9.7 | behavioral | Multiple awards | `points_by_interface()` returns per-interface totals | Per-interface breakdown correct |
| AC-9.8 | boundary | `award("chat", "m1", "thumbs_up")` twice with same item+event | Second call returns 0, no duplicate row | Duplicate events are idempotent |

## 4. Unit Test Plan

| Test file | ACs covered | Marks |
|-----------|-------------|-------|
| `tests/test_repo.py` | AC-5.1..5.8 | `@pytest.mark.contract("behavioral")` `@pytest.mark.scope("unit")` |
| `tests/test_retrieval.py` | AC-6.1..6.5 | `@pytest.mark.contract("behavioral")` `@pytest.mark.scope("unit")` |
| `tests/test_working_memory.py` | AC-7.1..7.13 | `@pytest.mark.contract("behavioral")` `@pytest.mark.scope("unit")` |
| `tests/test_persistence.py` | AC-8.1..8.7 | `@pytest.mark.contract("behavioral")` `@pytest.mark.scope("unit")` |
| `tests/test_write_paths.py` | AC-4.1..4.6 | `@pytest.mark.contract("behavioral")` `@pytest.mark.scope("unit")` |
| `tests/test_rewards.py` | AC-9.1..9.8 | `@pytest.mark.contract("behavioral")` `@pytest.mark.scope("unit")` |
| `tests/test_schema.py` | AC-8.1 (boundary) | `@pytest.mark.contract("boundary")` `@pytest.mark.scope("unit")` |
| `tests/test_postgres_repo.py` | AC-5 (PostgreSQL variant) | `@pytest.mark.contract("behavioral")` `@pytest.mark.scope("integration")` |

**Conftest fixtures needed:**

```python
# tests/conftest.py additions
import pytest
from maistro_turing.memory.repo import Repo

@pytest.fixture
def repo() -> Repo:
    r = Repo(":memory:")
    yield r
    r.close()

@pytest.fixture
def self_id(repo: Repo) -> str:
    from maistro_turing.self_model.identity import bootstrap_self_id
    return bootstrap_self_id(repo.conn)
```

## 5. Property Tests (Hypothesis)

### P-5.1: Weight decay never violates tier floor

```python
from hypothesis import given, settings
from hypothesis import strategies as st
from maistro_turing.types import EpisodicMemory, MemoryTier, SourceKind
from maistro_turing.tiers import WEIGHT_BOUNDS

@given(
    tier=st.sampled_from(list(MemoryTier)),
    weight=st.floats(min_value=0.01, max_value=1.0),
    delta=st.floats(min_value=0.001, max_value=0.5),
    iterations=st.integers(min_value=1, max_value=200),
)
@settings(max_examples=100)
def test_weight_decay_never_below_floor(tier, weight, delta, iterations):
    """After any number of decay_weight calls, weight >= tier floor."""
    from maistro_turing.memory.repo import Repo
    repo = Repo(":memory:")
    try:
        m = EpisodicMemory(
            memory_id="test",
            self_id="self",
            tier=tier,
            source=SourceKind.I_DID if tier in DURABLE_TIERS else SourceKind.I_DID,
            content="x",
            weight=weight,
            intent_at_time="test" if tier == MemoryTier.ACCOMPLISHMENT else "",
        )
        repo.insert(m)
        floor = WEIGHT_BOUNDS[tier][0]
        for _ in range(iterations):
            new_w = repo.decay_weight(m.memory_id, delta=delta)
            assert new_w >= floor, f"{new_w} < {floor} for tier {tier}"
    finally:
        repo.close()
```

### P-6.1: Retrieval budget never exceeds total_budget_tokens

```python
from maistro_turing.memory.retrieval import retrieve, estimate_tokens

@given(
    n_observations=st.integers(min_value=0, max_value=50),
    n_durables=st.integers(min_value=0, max_value=10),
    budget=st.integers(min_value=100, max_value=5000),
)
@settings(max_examples=50)
def test_retrieval_respects_budget(n_observations, n_durables, budget):
    """Total estimated tokens of retrieved memories <= total_budget_tokens."""
    from maistro_turing.memory.repo import Repo
    repo = Repo(":memory:")
    self_id = "self"
    for _ in range(n_observations):
        m = EpisodicMemory(
            memory_id=str(uuid4()), self_id=self_id,
            tier=MemoryTier.OBSERVATION, source=SourceKind.I_DID,
            content="x" * 40, weight=0.5, intent_at_time="",
        )
        repo.insert(m)
    for i in range(n_durables):
        m = EpisodicMemory(
            memory_id=str(uuid4()), self_id=self_id,
            tier=MemoryTier.REGRET, source=SourceKind.I_DID,
            content="d" * 40, weight=0.8, intent_at_time=f"durable-{i}",
            immutable=True,
        )
        repo.insert(m)
    results = retrieve(repo, self_id, total_budget_tokens=budget)
    total = sum(estimate_tokens(m) for m in results)
    assert total <= budget + 50  # small margin for rounding
    repo.close()
```

### P-7.1: Working memory eviction preserves capacity invariant

```python
@given(
    n_items=st.integers(min_value=1, max_value=100),
    priorities=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=100),
)
@settings(max_examples=50)
def test_working_memory_capacity_invariant(n_items, priorities):
    """After any number of adds, len(entries) <= MAX_ENTRIES."""
    from maistro_turing.memory.working_memory import WorkingMemory, WORKING_MEMORY_MAX_ENTRIES
    repo = Repo(":memory:")
    wm = WorkingMemory(repo.conn)
    self_id = "self"
    for i, p in enumerate(priorities[:n_items]):
        wm.add(self_id, f"entry-{i}", priority=p)
    entries = wm.entries(self_id)
    assert len(entries) <= WORKING_MEMORY_MAX_ENTRIES
    repo.close()
```

## 6. Integration Test Plan

| Test | What it wires | AC | Marks |
|-------|--------------|-----|-------|
| `test_write_path_round_trip` | `write_paths.handle_regret_candidate` → `repo.insert` → `retrieval.retrieve` confirms durable | AC-5 + AC-6 | `contract("cross-service")` `scope("integration")` |
| `test_rewards_feed_motivation` | `rewards.RewardTracker` → `motivation.Motivation` pressure update | AC-9 + AC-19 | `contract("cross-service")` `scope("integration")` |
| `test_working_memory_render_in_prompt` | `working_memory.render()` output usable as chat context string | AC-7 | `contract("behavioral")` `scope("integration")` |
| `test_postgres_repo_matches_sqlite` | Same operations on both backends produce identical results | AC-5 | `contract("behavioral")` `scope("integration")` |

## 7. Bridge Adapter Specs

### TuringMemoryBridge expansion (existing → add methods)

The current `TuringMemoryBridge` (in `bridge.py`) wraps maistro-core's `EpisodicStore` with async `store_episode` / `retrieve_episodes`. Phase 2 adds these methods:

| Method | Wraps | Returns |
|--------|-------|---------|
| `walk_lineage(memory_id)` | `EpisodicStore` + local lineage walk | `list[EpisodicMemory]` |
| `set_superseded_by(mid, successor)` | Direct repo call | `None` |
| `increment_contradiction_count(mid)` | Direct repo call | `None` |
| `decay_weight(mid, delta)` | Direct repo call | `float` |
| `soft_delete(mid)` | Direct repo call | `None` |
| `find(**filters)` | `EpisodicStore.retrieve` with filter translation | `list[EpisodicMemory]` |

### New bridge: TuringRetrievalBridge

```python
class TuringRetrievalBridge:
    """Wraps maistro_turing.memory.retrieval for consumers that don't
    want a direct Repo dependency."""

    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    def retrieve(self, self_id: str, *, total_budget_tokens: int,
                 source_filter=..., durable_min_tokens: int = ...,
                 tiers=..., intent_at_time: str | None = ...) -> list[EpisodicMemory]:
        from maistro_turing.memory.retrieval import retrieve
        return retrieve(self._repo, self_id, total_budget_tokens=total_budget_tokens, ...)
```

### New bridge: TuringWorkingMemoryBridge

```python
class TuringWorkingMemoryBridge:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._wm = WorkingMemory(conn)

    def entries(self, self_id: str) -> list[Entry]: ...
    def add(self, self_id: str, content: str, *, priority: float = 0.5) -> str: ...
    def remove(self, self_id: str, entry_id: str) -> bool: ...
    def clear(self, self_id: str) -> int: ...
    def render(self, self_id: str) -> str: ...
```

## 8. Phase Gate

- [ ] All AC-5..9 tests pass
- [ ] `ruff check packages/maistro-turing/` clean
- [ ] `mypy packages/maistro-turing/ --strict` clean
- [ ] Test count >= 60
- [ ] No `stronghold` imports
- [ ] SQLite repo passes all INV-1..8 invariant tests
- [ ] PostgreSQL repo passes at least AC-5.1..5.5
- [ ] `python -c "from maistro_turing.memory.repo import Repo; print('OK')"` succeeds
