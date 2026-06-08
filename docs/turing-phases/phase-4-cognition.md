# Phase 4: Cognition Engine

**Goal:** Autonomous inner life — motivation, dreaming, daydreaming, drives, scheduling,
tuning, contradiction detection.

**Depends on:** Phase 2 (memory layer) — Repo, retrieval, write_paths.

---

## 1. Source Inventory

| Source file | Lines | Description |
|------------|-------|-------------|
| `turing/motivation.py` | 256 | Priority ladder, pressure vector, scoring, backlog, dispatch |
| `turing/dreaming.py` | 504 | 7-phase WISDOM consolidation (Dreamer) |
| `turing/daydream.py` | 396 | DaydreamWriter + DaydreamProducer |
| `turing/scheduler.py` | 161 | P0 deadline scheduling (Scheduler, ScheduledItem) |
| `turing/drives.py` | 143 | 6-dim drive vector from HEXACO facets + mood |
| `turing/tuning.py` | 344 | CoefficientTable + CoefficientTuner (AFFIRMATION-backed coefficients) |
| `turing/detectors/contradiction.py` | 292 | Contradiction detector (LLM-backed claim opposition) |
| `turing/reactor.py` | 91 | Reactor protocol + FakeReactor (already ported) |
| **Total** | **~2,187** | |

| Source test file | Lines | Key ACs covered |
|-----------------|-------|----------------|
| `tests/test_motivation.py` | 300 | AC-9.1..9.18 (priority ladder, scoring, backlog) |
| `tests/test_dreaming.py` | 275 | Dreamer 7-phase sessions |
| `tests/test_dreaming_coverage.py` | 315 | Dreamer edge cases |
| `tests/test_daydreaming.py` | 245 | AC-7.1..7.15 (daydream writer/producer) |
| `tests/test_daydream_coverage.py` | 196 | Daydream edge cases |
| `tests/test_scheduler.py` | 150 | AC-10.1..10.10 |
| `tests/test_contradiction.py` | 212 | AC-D1.1..D1.10 |
| `tests/test_contradiction_coverage.py` | 318 | Contradiction edge cases |
| `tests/test_tuning.py` | 221 | AC-11.1..11.11 |
| **Total** | **~2,232** | |

## 2. Target File Mapping

| Source | Target |
|--------|--------|
| `turing/motivation.py` | `maistro_turing/cognition/motivation.py` |
| `turing/dreaming.py` | `maistro_turing/cognition/dreaming.py` |
| `turing/daydream.py` | `maistro_turing/cognition/daydream.py` |
| `turing/scheduler.py` | `maistro_turing/cognition/scheduler.py` |
| `turing/drives.py` | `maistro_turing/cognition/drives.py` |
| `turing/tuning.py` | `maistro_turing/cognition/tuning.py` |
| `turing/detectors/contradiction.py` | `maistro_turing/cognition/contradiction.py` |

## 3. Acceptance Criteria

### AC-19: Motivation — priority ladder + scoring (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-19.1 | boundary | `priority_base(0)` | Returns `1_000_000.0` | P0 is highest priority |
| AC-19.2 | boundary | `priority_base(70)` | Returns `0.01` | P70 is lowest priority |
| AC-19.3 | behavioral | `priority_base(p)` for any int p | Returns float > 0 | Monotonically decreasing with p |
| AC-19.4 | behavioral | `score(item, pressure, fit)` | Returns float based on `priority_base(class) + max(pressure ⊙ fit)` | Scoring formula is deterministic |
| AC-19.5 | behavioral | `Motivation.tick()` with pending backlog items | Top-X items selected, at most MAX_CONCURRENT dispatched | Cadence respected |
| AC-19.6 | behavioral | Dispatch produces `DispatchObservation` with chosen_pool | Observation has correct pool name | Dispatch records model choice |
| AC-19.7 | boundary | `PipelineState.EMPTY` | No dispatch happens | Empty state is stable |
| AC-19.8 | behavioral | Two items with same priority, different pressure | Higher pressure wins | Pressure breaks ties |

### AC-20: Dreaming — 7-phase consolidation (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-20.1 | behavioral | `Dreamer.run_session()` with >= `DREAM_MIN_NEW_DURABLE` new durable memories | Session completes 7 phases | Minimum durable threshold respected |
| AC-20.2 | behavioral | Dream session completes | Pending WISDOM candidates committed | WISDOM gated by review |
| AC-20.3 | behavioral | Dream session with no new durable memories | Session skips (no-op) | Below threshold skips |
| AC-20.4 | behavioral | Phase 5 (pruning) | Non-durable memories below `DREAM_MIN_RETAIN_WEIGHT` deleted | Pruning respects weight threshold |
| AC-20.5 | behavioral | Session marker written | Marker memory has `origin_episode_id` pointing to session | Session marker is traceable |
| AC-20.6 | behavioral | `DREAM_MAX_DURATION` exceeded | Partial session marker written, committed candidates remain | Timeout is safe |
| AC-20.7 | boundary | `DREAM_MAX_WISDOM_CANDIDATES = 3` | At most 3 WISDOM candidates per session | Wisdom candidate cap |
| AC-20.8 | behavioral | AFFIRMATION proposal in phase 3 | AFFIRMATION written via `handle_affirmation` | Affirmation is revocable |

### AC-21: Daydream writer + producer (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-21.1 | boundary | `DaydreamWriter` produces content | Content has `source=I_IMAGINED`, never `I_DID` | Cannot emit I_DID |
| AC-21.2 | boundary | `DaydreamWriter` API | No method can write to durable tiers | No durable writes from daydream |
| AC-21.3 | behavioral | `DaydreamProducer.on_tick()` with sufficient drive | BacklogItem submitted to motivation | Producer fires when drive is high |
| AC-21.4 | behavioral | `DaydreamProducer.on_dispatch()` | Writes episodic memory via Repo | Dispatch writes to repo |
| AC-21.5 | boundary | Daydream tokens limited by `daydream_tokens_per_pass` | Provider call respects limit | Token budget respected |
| AC-21.6 | behavioral | Multiple daydream passes per tick | At most `daydream_writes_per_pass` writes | Write cap respected |

### AC-22: Scheduler — P0 deadlines (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-22.1 | behavioral | `Scheduler.schedule(item)` with early time | Item appears in `upcoming()` | Schedule stores items |
| AC-22.2 | behavioral | Time passes past delivery time | `due_now()` returns the item | Due detection works |
| AC-22.3 | behavioral | Item delivered | `due_now()` no longer returns it | Delivered items cleared |
| AC-22.4 | behavioral | Overlapping items with same callback | Both fire independently | No collision |
| AC-22.5 | boundary | `ScheduledItem` with duration | Duration respected in scheduling | Duration bounds delivery window |

### AC-23: Drives — 6-dim vector (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-23.1 | boundary | `compute_drives(facets, mood)` | Returns dict with exactly 6 keys: curiosity, creativity, social, achievement, wellbeing, autonomy | 6 drive dimensions |
| AC-23.2 | boundary | `compute_drives(facets, mood)` | All values in [0.0, 1.0] | Drives bounded |
| AC-23.3 | behavioral | `sate_curiosity()` called | Curiosity drive drops to 0.0 | Sating resets curiosity |
| AC-23.4 | behavioral | Time passes after `sate_curiosity()` | Curiosity grows (approaches 1.0 over time) | Curiosity is a hunger that refills |
| AC-23.5 | behavioral | High `inquisitiveness` facet | Curiosity grows faster | Personality modulates growth |

### AC-24: Contradiction detector (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-24.1 | behavioral | Two memories with opposed claims on same topic | Detector flags contradiction | Opposed claims detected |
| AC-24.2 | behavioral | Two memories supporting same side | No contradiction flagged | Same-side not contradictory |
| AC-24.3 | behavioral | Memory with empty content | Skipped, no crash | Empty content is safe |
| AC-24.4 | behavioral | Provider returns unparseable response | Returns `None` (no contradiction) | Malformed LLM output is safe |
| AC-24.5 | boundary | `_claims_opposed("X is good", "X is bad")` | Returns bool | Binary opposition check |

### AC-25: Tuning — coefficient table (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-25.1 | boundary | `CoefficientTable()` default construction | All fields have seed values | Default seeds exist |
| AC-25.2 | behavioral | `apply_update(table, update)` | Updated field matches `update.new_value` | Apply update changes target field |
| AC-25.3 | boundary | `apply_update` with unknown field name | No error, table unchanged | Unknown fields ignored |
| AC-25.4 | behavioral | `parse_coefficient_commitment("coefficient_commitment:pressure_max=6000")` | Returns `CoefficientUpdate(field="pressure_max", new_value=6000.0)` | Parsing round-trips |
| AC-25.5 | behavioral | `validate_table(table)` on default seeds | Returns list of warnings (seed values) | Seeds generate warnings |
| AC-25.6 | behavioral | `CoefficientTuner.on_tick()` with sufficient observations | Submits P15 backlog item to motivation | Tuner fires periodically |
| AC-25.7 | behavioral | `CoefficientTuner._on_dispatch()` | Writes AFFIRMATION via `handle_affirmation` | Updates stored as AFFIRMATIONs |

## 4. Unit Test Plan

| Test file | ACs covered | Marks |
|-----------|-------------|-------|
| `tests/test_motivation.py` | AC-19.1..19.8 | `contract("behavioral")` `scope("unit")` |
| `tests/test_dreaming.py` | AC-20.1..20.6 | `contract("behavioral")` `scope("unit")` |
| `tests/test_dreaming_coverage.py` | AC-20 edge cases | `contract("behavioral")` `scope("unit")` |
| `tests/test_daydreaming.py` | AC-21.1..21.6 | `contract("behavioral")` `scope("unit")` |
| `tests/test_daydream_coverage.py` | AC-21 edge cases | `contract("behavioral")` `scope("unit")` |
| `tests/test_scheduler.py` | AC-22.1..22.5 | `contract("behavioral")` `scope("unit")` |
| `tests/test_contradiction.py` | AC-24.1..24.5 | `contract("behavioral")` `scope("unit")` |
| `tests/test_contradiction_coverage.py` | AC-24 edge cases | `contract("behavioral")` `scope("unit")` |
| `tests/test_tuning.py` | AC-25.1..25.7 | `contract("behavioral")` `scope("unit")` |

**Key fixtures:**

```python
@pytest.fixture
def motivation() -> Motivation:
    return Motivation(reactor=FakeReactor())

@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()
```

## 5. Property Tests (Hypothesis)

### P-19.1: Priority base is monotonically decreasing

```python
from hypothesis import given, settings
from hypothesis import strategies as st
from maistro_turing.cognition.motivation import priority_base

@given(p1=st.integers(min_value=0, max_value=69), p2=st.integers(min_value=0, max_value=69))
@settings(max_examples=200)
def test_priority_base_monotonic(p1, p2):
    if p1 < p2:
        assert priority_base(p1) >= priority_base(p2)
    elif p1 == p2:
        assert priority_base(p1) == priority_base(p2)
```

### P-23.1: Drive vector always in [0, 1]

```python
from hypothesis import given, settings
from hypothesis import strategies as st
from maistro_turing.cognition.drives import compute_drives
from maistro_turing.self_model import Mood

@given(
    facets=st.dictionaries(
        st.text(min_size=3, max_size=20),
        st.floats(min_value=1.0, max_value=5.0),
        min_size=6, max_size=24,
    ),
    valence=st.floats(min_value=-1.0, max_value=1.0),
    arousal=st.floats(min_value=0.0, max_value=1.0),
    focus=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=100)
def test_drives_bounded(facets, valence, arousal, focus):
    from datetime import UTC, datetime
    mood = Mood(self_id="s", valence=valence, arousal=arousal, focus=focus,
                last_tick_at=datetime.now(UTC))
    drives = compute_drives(facets, mood)
    for name, value in drives.items():
        assert 0.0 <= value <= 1.0, f"{name}={value} out of [0,1]"
```

### P-25.1: CoefficientTable apply_update is total

```python
from hypothesis import given, settings
from hypothesis import strategies as st
from maistro_turing.cognition.tuning import CoefficientTable, apply_update, CoefficientUpdate

@given(
    field_name=st.sampled_from([f.name for f in fields(CoefficientTable)]),
    new_value=st.floats(min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_apply_update_total(field_name, new_value):
    table = CoefficientTable()
    update = CoefficientUpdate(field=field_name, new_value=new_value)
    result = apply_update(table, update)
    assert getattr(result, field_name) == new_value
```

## 6. Integration Test Plan

| Test | What it wires | AC | Marks |
|-------|--------------|-----|-------|
| `test_dreamer_uses_retrieval` | Dreamer → Repo + retrieval → WISDOM write | AC-20 + AC-6 | `contract("cross-service")` `scope("integration")` |
| `test_motivation_dispatches_producer` | Motivation → FakeReactor → DaydreamProducer → Repo write | AC-19 + AC-21 | `contract("cross-service")` `scope("integration")` |
| `test_contradiction_triggers_regret` | Contradiction → write_paths.handle_regret_candidate → Repo | AC-24 + AC-4 | `contract("cross-service")` `scope("integration")` |
| `test_tuner_writes_affirmation` | Tuner → handle_affirmation → Repo → parse_coefficient_commitment | AC-25 + AC-4 | `contract("cross-service")` `scope("integration")` |
| `test_scheduler_fires_callback` | Scheduler → Motivation → dispatch | AC-22 + AC-19 | `contract("cross-service")` `scope("integration")` |

## 7. Bridge Adapter Specs

### New bridge: TuringReactorBridge

```python
class TuringReactorBridge:
    """Wraps FakeReactor for dev/test, RealReactor for production."""

    def __init__(self, reactor: Reactor) -> None:
        self._reactor = reactor

    def tick(self) -> None: ...
    def spawn(self, fn: Callable) -> Future: ...
    def interval(self, seconds: float, fn: Callable) -> str: ...
    def cancel(self, handle: str) -> None: ...
```

No new maistro-core bridges needed — cognition modules depend on Repo (Phase 2),
Reactor (Phase 1), and Provider (Phase 6, but FakeProvider works for dev).

## 8. Phase Gate

- [ ] All AC-19..25 tests pass
- [ ] `ruff check packages/maistro-turing/` clean
- [ ] `mypy packages/maistro-turing/ --strict` clean
- [ ] Test count >= 80
- [ ] No `stronghold` imports
- [ ] Dreamer completes a 7-phase session against SQLite Repo
- [ ] Motivation dispatches and records observations
