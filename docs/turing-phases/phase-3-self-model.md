# Phase 3: Self-Model (Core)

**Goal:** Complete self-model identity system with persistence. The `SelfRepo` (1,288 lines)
and 15 core self_* modules that provide personality, mood, activation, nodes, bootstrap,
surface, naming, conversations, memory bridge, sentinel, warden gate, budget, contributors,
coaching, and identity.

**Depends on:** Phase 2 (memory layer — Repo, schema).

---

## 1. Source Inventory

| Source file | Lines | Description |
|------------|-------|-------------|
| `turing/self_repo.py` | 1,288 | SQLite SelfRepo — CRUD for all self-model dataclasses |
| `turing/self_identity.py` | 50 | Self-id bootstrap, archive, mint |
| `turing/self_nodes.py` | 264 | Node CRUD: passions, hobbies, interests, preferences, skills |
| `turing/self_bootstrap.py` | 228 | HEXACO personality bootstrap from seed |
| `turing/self_personality.py` | 203 | Personality scoring, facet diversity floor, retest sampling |
| `turing/self_mood.py` | 118 | Mood computation: decay, event nudges, descriptor |
| `turing/self_activation.py` | 168 | Activation graph: contributor scoring, active_now |
| `turing/self_todos.py` | 159 | Self-todo CRUD with motivated_by tracking |
| `turing/self_surface.py` | 223 | Outward presentation: profile rendering |
| `turing/self_naming.py` | 97 | Self-naming ritual |
| `turing/self_conversations.py` | 131 | Conversation tracking |
| `turing/self_memory_bridge.py` | 199 | Self-model ↔ memory bridge |
| `turing/self_sentinel.py` | 102 | Self-write monitoring |
| `turing/self_warden_gate.py` | 74 | Security gate for self-model writes |
| `turing/self_budget.py` | 79 | Token budget management |
| `turing/self_contributors.py` | 123 | Activation contributors CRUD |
| `turing/self_coaching.py` | 65 | Self-coaching session management |
| **Total** | **~3,572** | |

| Source test file | Lines | Key ACs covered |
|-----------------|-------|----------------|
| `tests/test_self_schema.py` | 512 | Schema validation for self-model tables |
| `tests/test_self_nodes.py` | 194 | AC-24.* (node CRUD) |
| `tests/test_self_nodes_coverage.py` | 227 | AC-24 edge cases |
| `tests/test_self_nodes_extra.py` | 56 | AC-24 additional |
| `tests/test_self_bootstrap.py` | 270 | AC-29.* (bootstrap) |
| `tests/test_self_personality.py` | 336 | AC-23.* (personality scoring) |
| `tests/test_self_personality_coverage.py` | 175 | AC-23 edge cases |
| `tests/test_self_personality_drift.py` | 99 | Personality drift detection |
| `tests/test_self_mood.py` | 261 | AC-27.* (mood computation) |
| `tests/test_self_activation.py` | 478 | AC-25.* (activation graph) |
| `tests/test_self_todos.py` | 184 | AC-15.* (todo CRUD) |
| `tests/test_self_todos_coverage.py` | 231 | AC-15 edge cases |
| `tests/test_self_surface.py` | 228 | AC-28.* (surface rendering) |
| `tests/test_self_naming.py` | 143 | Naming ritual |
| `tests/test_self_conversations.py` | 148 | Conversation tracking |
| `tests/test_self_memory_bridge.py` | 246 | Self-model ↔ memory bridge |
| `tests/test_self_sentinel.py` | 110 | Self-write monitoring |
| `tests/test_self_warden_gate.py` | 300 | Security gate |
| `tests/test_self_budget.py` | 136 | Token budget |
| `tests/test_self_coaching.py` | 115 | Self-coaching |
| **Total** | **~4,173** | |

## 2. Target File Mapping

| Source | Target |
|--------|--------|
| `turing/self_repo.py` | `maistro_turing/self_model/repo.py` |
| `turing/self_identity.py` | `maistro_turing/self_model/identity.py` |
| `turing/self_nodes.py` | `maistro_turing/self_model/nodes.py` |
| `turing/self_bootstrap.py` | `maistro_turing/self_model/bootstrap.py` |
| `turing/self_personality.py` | `maistro_turing/self_model/personality.py` |
| `turing/self_mood.py` | `maistro_turing/self_model/mood.py` |
| `turing/self_activation.py` | `maistro_turing/self_model/activation.py` |
| `turing/self_todos.py` | `maistro_turing/self_model/todos.py` |
| `turing/self_surface.py` | `maistro_turing/self_model/surface.py` |
| `turing/self_naming.py` | `maistro_turing/self_model/naming.py` |
| `turing/self_conversations.py` | `maistro_turing/self_model/conversations.py` |
| `turing/self_memory_bridge.py` | `maistro_turing/self_model/memory_bridge.py` |
| `turing/self_sentinel.py` | `maistro_turing/self_model/sentinel.py` |
| `turing/self_warden_gate.py` | `maistro_turing/self_model/warden_gate.py` |
| `turing/self_budget.py` | `maistro_turing/self_model/budget.py` |
| `turing/self_contributors.py` | `maistro_turing/self_model/contributors.py` |
| `turing/self_coaching.py` | `maistro_turing/self_model/coaching.py` |

## 3. Acceptance Criteria

### AC-10: SelfRepo — personality facets (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-10.1 | behavioral | `insert_facet(f)` | `get_facet(f.node_id)` returns `f` | Insert/get round-trip |
| AC-10.2 | boundary | `insert_facet` with score < 1.0 or > 5.0 | `ValueError` | Score in [1, 5] |
| AC-10.3 | behavioral | `update_facet_score(self_id, facet_id, new_score)` | Score updated, `last_revised_at` set | Score update works |
| AC-10.4 | boundary | `update_facet_score` with `acting_self_id != self_id` | `CrossSelfAccess` raised | Cross-self write blocked |
| AC-10.5 | behavioral | `list_facets(self_id)` | Returns all facets for self_id | List is complete |
| AC-10.6 | behavioral | `count_facets(self_id)` after insert | Count incremented | Count is accurate |

### AC-11: SelfRepo — personality items + answers (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-11.1 | behavioral | `insert_item(it)` | `list_items(self_id)` includes `it` | Item round-trip |
| AC-11.2 | boundary | `insert_item` with `item_number` > 200 | `ValueError` | Item number bounded |
| AC-11.3 | behavioral | `insert_answer(a)` | `count_answers(self_id)` incremented | Answer counted |
| AC-11.4 | behavioral | `last_asked_map(self_id)` | Returns dict of item_id → last asked datetime | Asked map accurate |
| AC-11.5 | boundary | `insert_answer` with `answer_1_5 = 6` | `ValueError` | Answer in [1..5] |
| AC-11.6 | boundary | `insert_answer` with `justification_text > 200` chars | `ValueError` | Justification length bounded |

### AC-12: SelfRepo — revisions (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-12.1 | behavioral | `insert_revision(r)` | Revision stored with correct deltas_by_facet | Revision round-trip |
| AC-12.2 | boundary | `insert_revision` with `sampled_item_ids` length != 20 | `ValueError` | Exactly 20 items required |

### AC-13: SelfRepo — passions, hobbies, interests, preferences (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-13.1 | behavioral | `insert_passion(p)` | `get_passion(p.node_id)` returns `p` | Passion round-trip |
| AC-13.2 | boundary | `insert_passion` with `strength > 1.0` | `ValueError` | Strength in [0, 1] |
| AC-13.3 | behavioral | `insert_hobby(h)` | `list_hobbies(self_id)` includes `h` | Hobby round-trip |
| AC-13.4 | behavioral | `insert_interest(i)` | `list_interests(self_id)` includes `i` | Interest round-trip |
| AC-13.5 | behavioral | `insert_preference(p)` | `list_preferences(self_id)` includes `p` | Preference round-trip |
| AC-13.6 | behavioral | `max_passion_rank(self_id)` | Returns highest rank among passions | Rank tracking |
| AC-13.7 | behavioral | `top_passion(self_id)` | Returns passion with highest strength | Top passion correct |

### AC-14: SelfRepo — skills (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-14.1 | behavioral | `insert_skill(s)` | `get_skill(s.node_id)` returns `s` | Skill round-trip |
| AC-14.2 | boundary | `insert_skill` with `stored_level > 1.0` | `ValueError` | Level in [0, 1] |
| AC-14.3 | behavioral | `update_skill(s)` | Skill updated in repo | Update persists |
| AC-14.4 | boundary | `update_skill` with `acting_self_id != s.self_id` | `CrossSelfAccess` | Cross-self blocked |

### AC-15: SelfRepo — todos (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-15.1 | behavioral | `insert_todo(t)` | `get_todo(t.node_id)` returns `t` | Todo round-trip |
| AC-15.2 | boundary | `insert_todo` with `text > 500` chars | `ValueError` | Text length bounded |
| AC-15.3 | boundary | `insert_todo` with `status=COMPLETED`, empty `outcome_text` | `ValueError` | Completed requires outcome |
| AC-15.4 | boundary | `insert_todo` with empty `motivated_by_node_id` | `ValueError` | Motivator required |
| AC-15.5 | behavioral | `update_todo(t)` | Todo updated in repo | Update persists |
| AC-15.6 | behavioral | `list_active_todos(self_id)` | Returns only `ACTIVE` status todos | Active filter |
| AC-15.7 | behavioral | `insert_todo_revision(tr)` | Revision stored, `max_revision_num` incremented | Revision tracking |
| AC-15.8 | boundary | `insert_todo_revision` with `revision_num < 1` | `ValueError` | Revision starts at 1 |

### AC-16: SelfRepo — mood (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-16.1 | behavioral | `insert_mood(m)` | `get_mood(m.self_id)` returns `m` | Mood round-trip |
| AC-16.2 | boundary | Mood with `valence > 1.0` | `ValueError` | Valence in [-1, 1] |
| AC-16.3 | boundary | Mood with `arousal > 1.0` | `ValueError` | Arousal in [0, 1] |
| AC-16.4 | boundary | Mood with `focus > 1.0` | `ValueError` | Focus in [0, 1] |
| AC-16.5 | behavioral | `update_mood(m)` | Mood updated in repo | Update persists |
| AC-16.6 | behavioral | `has_mood(self_id)` | Returns bool | Mood existence check |

### AC-17: SelfRepo — activation contributors (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-17.1 | behavioral | `insert_contributor(c)` | `get_contributor(c.node_id)` returns `c` | Contributor round-trip |
| AC-17.2 | boundary | Contributor with `target_node_id == source_id` | `ValueError` | Cannot target self |
| AC-17.3 | boundary | Contributor with `weight > 1.0` | `ValueError` | Weight in [-1, 1] |
| AC-17.4 | boundary | `RETRIEVAL` origin without `expires_at` | `ValueError` | Retrieval requires expiry |
| AC-17.5 | boundary | `SELF` origin with `expires_at` set | `ValueError` | Non-retrieval must not have expiry |
| AC-17.6 | behavioral | `mark_contributor_retracted(id, retracted_by)` | Contributor has `retracted_by` set | Retraction works |
| AC-17.7 | behavioral | `active_contributors_for(self_id, target)` | Excludes retracted contributors | Retracted excluded |

### AC-18: SelfRepo — bootstrap progress (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-18.1 | behavioral | `start_bootstrap_progress(self_id, seed=42)` | `get_bootstrap_progress(self_id)` returns 0 | Progress starts at 0 |
| AC-18.2 | behavioral | `update_bootstrap_progress(self_id, 10)` | `get_bootstrap_progress(self_id)` returns 10 | Progress updates |
| AC-18.3 | behavioral | `delete_bootstrap_progress(self_id)` | `get_bootstrap_progress` returns `None` | Delete clears progress |

## 4. Unit Test Plan

| Test file | ACs covered | Marks |
|-----------|-------------|-------|
| `tests/test_self_repo.py` | AC-10..18 (SelfRepo CRUD) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_schema.py` | Schema validation | `contract("boundary")` `scope("unit")` |
| `tests/test_self_nodes.py` | AC-24.* (passion, hobby, interest, preference, skill CRUD) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_nodes_coverage.py` | AC-24 edge cases | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_bootstrap.py` | AC-29.* (bootstrap) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_personality.py` | AC-23.* (personality scoring) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_personality_coverage.py` | AC-23 edge cases | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_personality_drift.py` | Drift detection | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_mood.py` | AC-27.* (mood computation) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_activation.py` | AC-25.* (activation graph) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_todos.py` | AC-15.* (todo CRUD) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_todos_coverage.py` | AC-15 edge cases | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_surface.py` | AC-28.* (surface rendering) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_naming.py` | Naming ritual | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_conversations.py` | Conversation tracking | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_memory_bridge.py` | Self-model ↔ memory bridge | `contract("cross-service")` `scope("integration")` |
| `tests/test_self_sentinel.py` | Self-write monitoring | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_warden_gate.py` | Security gate | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_budget.py` | Token budget | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_coaching.py` | Self-coaching | `contract("behavioral")` `scope("unit")` |

**Key fixtures:**

```python
@pytest.fixture
def self_repo(repo: Repo) -> SelfRepo:
    return SelfRepo(repo.conn)

@pytest.fixture
def self_id(repo: Repo) -> str:
    from maistro_turing.self_model.identity import bootstrap_self_id
    return bootstrap_self_id(repo.conn)

@pytest.fixture
def bootstrapped_self(self_repo: SelfRepo, self_id: str) -> str:
    """Self with 24 personality facets bootstrapped."""
    from maistro_turing.self_model.bootstrap import run_bootstrap
    run_bootstrap(self_repo, self_id, seed=42)
    return self_id
```

## 5. Property Tests (Hypothesis)

### P-10.1: Facet score always in [1, 5]

```python
from hypothesis import given, settings
from hypothesis import strategies as st
from maistro_turing.self_model import PersonalityFacet, Trait, FACET_TO_TRAIT
from maistro_turing.self_model.repo import SelfRepo

@given(
    score=st.floats(min_value=1.0, max_value=5.0, allow_nan=False),
    facet_id=st.sampled_from(list(FACET_TO_TRAIT.keys())),
)
@settings(max_examples=100)
def test_facet_score_valid_range(score, facet_id):
    trait = FACET_TO_TRAIT[facet_id]
    f = PersonalityFacet(
        node_id=f"facet:{trait.value}.{facet_id}",
        self_id="self",
        trait=trait,
        facet_id=facet_id,
        score=score,
        last_revised_at=datetime.now(UTC),
    )
    assert 1.0 <= f.score <= 5.0
```

### P-16.1: Mood dimensions always bounded

```python
from maistro_turing.self_model import Mood

@given(
    valence=st.floats(min_value=-1.0, max_value=1.0),
    arousal=st.floats(min_value=0.0, max_value=1.0),
    focus=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=200)
def test_mood_bounded(valence, arousal, focus):
    m = Mood(self_id="s", valence=valence, arousal=arousal, focus=focus,
             last_tick_at=datetime.now(UTC))
    assert -1.0 <= m.valence <= 1.0
    assert 0.0 <= m.arousal <= 1.0
    assert 0.0 <= m.focus <= 1.0
```

### P-17.1: Contributor cannot target self

```python
from maistro_turing.self_model import ActivationContributor, NodeKind, ContributorOrigin

@given(
    node_id=st.text(min_size=1, max_size=50),
    origin=st.sampled_from([ContributorOrigin.SELF, ContributorOrigin.RULE]),
)
@settings(max_examples=50)
def test_contributor_no_self_target(node_id, origin):
    with pytest.raises(ValueError, match="cannot target itself"):
        ActivationContributor(
            node_id="c1", self_id="s", target_node_id=node_id,
            target_kind=NodeKind.SKILL, source_id=node_id,
            source_kind="test", weight=0.5, origin=origin,
            rationale="test",
        )
```

## 6. Integration Test Plan

| Test | What it wires | AC | Marks |
|-------|--------------|-----|-------|
| `test_bootstrap_to_surface` | bootstrap → personality → mood → surface render | AC-10 + AC-23 + AC-27 + AC-28 | `contract("cross-service")` `scope("integration")` |
| `test_nodes_to_activation` | insert passion/skill → compute activation → active_now | AC-13 + AC-14 + AC-17 | `contract("cross-service")` `scope("integration")` |
| `test_todo_from_motivator` | insert passion → create todo motivated_by passion → list_active | AC-13 + AC-15 | `contract("cross-service")` `scope("integration")` |
| `test_memory_bridge_round_trip` | self-model change → memory_bridge → episodic memory written | AC-10 + memory layer | `contract("cross-service")` `scope("integration")` |
| `test_sentinel_blocks_dangerous_write` | sentinel + warden_gate → dangerous self-write blocked | AC-10 + security | `contract("cross-service")` `scope("integration")` |
| `test_coaching_updates_skill` | coaching session → skill level updated | AC-14 + coaching | `contract("cross-service")` `scope("integration")` |

## 7. Bridge Adapter Specs

### New bridge: TuringSelfRepoBridge

```python
class TuringSelfRepoBridge:
    """Wraps SelfRepo for consumers that need self-model data
    without direct SQLite dependency."""

    def __init__(self, self_repo: SelfRepo) -> None:
        self._repo = self_repo

    def get_facet_score(self, self_id: str, facet_id: str) -> float: ...
    def list_facets(self, self_id: str) -> list[PersonalityFacet]: ...
    def get_mood(self, self_id: str) -> Mood: ...
    def list_active_todos(self, self_id: str) -> list[SelfTodo]: ...
    def list_passions(self, self_id: str) -> list[Passion]: ...
    def list_skills(self, self_id: str) -> list[Skill]: ...
    def active_contributors_for(self, self_id: str, target: str) -> list[ActivationContributor]: ...
```

## 8. Phase Gate

- [ ] All AC-10..18 tests pass
- [ ] `ruff check packages/maistro-turing/` clean
- [ ] `mypy packages/maistro-turing/ --strict` clean
- [ ] Test count >= 200
- [ ] No `stronghold` imports
- [ ] `SelfRepo` round-trips all 12 dataclass types (facets, items, answers, revisions, passions, hobbies, interests, preferences, skills, todos, moods, contributors)
- [ ] Bootstrap creates 24 personality facets with valid scores
