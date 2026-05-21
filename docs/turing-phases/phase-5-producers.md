# Phase 5: Producers

**Goal:** All 8 producers ported, upgraded from simplified versions. Each producer
follows the `on_tick` → `_build_candidate` → `_on_dispatch` pattern, submitting
`BacklogItem`s to `Motivation` and writing results via `Repo`.

**Depends on:** Phase 2 (Repo), Phase 3 (self-model), Phase 4 (cognition: motivation, drives).

---

## 1. Source Inventory

| Source file | Lines | Description |
|------------|-------|-------------|
| `turing/producers/blog_producer.py` | 199 | Blog post generation from mood + passions |
| `turing/producers/self_reflection_producer.py` | 286 | Code-aware self-reflection |
| `turing/producers/curiosity_producer.py` | 181 | Curiosity-driven web research |
| `turing/producers/emotional_producer.py` | 165 | Emotional response based on drives |
| `turing/producers/concept_skill_producers.py` | 643 | ConceptInventor + SkillBuilder + SkillExecutor (3 classes) |
| `turing/producers/outreach_producer.py` | 177 | Social outreach |
| `turing/producers/opinion_producer.py` | 131 | Opinion formation |
| `turing/producers/hobby_producer.py` | 115 | Hobby exploration |
| `turing/producers/__init__.py` | 25 | Registry |
| **Total** | **~1,922** | |

| Source test file | Lines | Key ACs covered |
|-----------------|-------|----------------|
| `tests/test_blog_producer.py` | ~180 | AC-26.* |
| `tests/test_self_reflection_producer.py` | ~190 | AC-27.* |
| `tests/test_curiosity_producer.py` | ~160 | AC-28.* |
| `tests/test_emotional_producer.py` | ~140 | AC-29.* |
| `tests/test_concept_skill_producers.py` | ~350 | AC-30..32.* |
| `tests/test_hobby_producer.py` | ~80 | AC-33.* (hobby) |
| `tests/test_outreach_producer.py` | ~100 | AC-33.* (outreach) |
| `tests/test_opinion_producer.py` | ~90 | AC-33.* (opinion) |
| `tests/test_skill_artifacts.py` | 188 | Skill artifact rendering |
| **Total** | **~1,478** | |

## 2. Target File Mapping

| Source | Target |
|--------|--------|
| `producers/blog_producer.py` | `maistro_turing/producers/blog.py` |
| `producers/self_reflection_producer.py` | `maistro_turing/producers/reflection.py` |
| `producers/curiosity_producer.py` | `maistro_turing/producers/curiosity.py` |
| `producers/emotional_producer.py` | `maistro_turing/producers/emotional.py` |
| `producers/concept_skill_producers.py` | `maistro_turing/producers/concept_skill.py` |
| `producers/outreach_producer.py` | `maistro_turing/producers/outreach.py` |
| `producers/opinion_producer.py` | `maistro_turing/producers/opinion.py` |
| `producers/hobby_producer.py` | `maistro_turing/producers/hobby.py` |
| `producers/__init__.py` | `maistro_turing/producers/__init__.py` (update) |

Note: The existing simplified `maistro_turing/producers.py` gets refactored into the
`producers/` package. The old file is replaced.

## 3. Acceptance Criteria

### AC-26: BlogProducer (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-26.1 | behavioral | `on_tick(tick)` at cadence interval | BacklogItem submitted to motivation | Producer fires on cadence |
| AC-26.2 | behavioral | `_on_dispatch(item, pool)` with FakeProvider | Blog content written to Repo as episodic memory | Dispatch writes memory |
| AC-26.3 | behavioral | `_build_prompt(mood)` with negative valence | Prompt reflects mood state | Mood influences content |
| AC-26.4 | boundary | `_extract_title("## My Title\n...")` | Returns `"My Title"` | Title extraction |
| AC-26.5 | boundary | `_extract_body("## Title\nBody text")` | Returns `"Body text"` | Body extraction |
| AC-26.6 | behavioral | Reward awarded after dispatch | RewardTracker.award("blog", ...) called | Dispatch earns points |

### AC-27: SelfReflectionProducer (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-27.1 | behavioral | `on_tick(tick)` with code files available | BacklogItem submitted | Fires on cadence |
| AC-27.2 | behavioral | `_on_dispatch` | Reflection memory written to Repo | Dispatch writes memory |
| AC-27.3 | behavioral | `_pick_file()` with multiple code files | Returns a file path | File selection works |
| AC-27.4 | behavioral | `_content_hash(text)` | Returns stable hash string | Hash is deterministic |
| AC-27.5 | behavioral | Same file not reflected twice in a row | Content hash checked against history | Dedup by hash |

### AC-28: CuriosityProducer (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-28.1 | behavioral | `on_tick(tick)` with high curiosity drive | BacklogItem submitted | Drive-gated firing |
| AC-28.2 | behavioral | `on_tick(tick)` with low curiosity drive | No backlog item submitted | Low drive suppresses |
| AC-28.3 | behavioral | `_pick_topic()` | Returns a non-empty topic string | Topic selection |
| AC-28.4 | behavioral | `_on_dispatch` | Research memory written, curiosity sated | Curiosity sated after dispatch |

### AC-29: EmotionalResponseProducer (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-29.1 | behavioral | `on_tick(tick)` | May submit backlog item (probabilistic) | Probabilistic firing |
| AC-29.2 | behavioral | `_weighted_sample(drives)` | Returns drive name weighted by value | Weighted sampling |
| AC-29.3 | behavioral | `_on_dispatch` | Emotional memory written to Repo | Dispatch writes memory |

### AC-30: ConceptInventor (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-30.1 | behavioral | `on_tick(tick)` with high creativity drive | BacklogItem submitted | Drive-gated |
| AC-30.2 | behavioral | `_on_dispatch` | Concept description written to Repo | Dispatch writes memory |
| AC-30.3 | behavioral | `_try_promote_concepts()` | Concepts with enough reinforcement promoted to skills | Promotion pipeline |
| AC-30.4 | behavioral | `_parse_concept_reply(valid_json)` | Returns parsed dict | Reply parsing |
| AC-30.5 | boundary | `_parse_concept_reply("gibberish")` | Returns `None` | Invalid reply safe |

### AC-31: SkillBuilder (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-31.1 | behavioral | `on_tick(tick)` with available skills needing coaching | BacklogItem submitted | Skills need coaching |
| AC-31.2 | behavioral | `_on_dispatch` | Coaching plan written to Repo | Dispatch writes memory |

### AC-32: SkillExecutor (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-32.1 | behavioral | `on_tick(tick)` with active coaching | BacklogItem submitted | Active coaching fires |
| AC-32.2 | behavioral | `_on_dispatch` | Attempt result written, skill level updated | Dispatch updates skill |
| AC-32.3 | behavioral | `_judge(attempt, criteria)` | Returns pass/fail verdict | Judging works |
| AC-32.4 | boundary | `_parse_attempt_reply("gibberish")` | Returns `None` | Invalid reply safe |

### AC-33: HobbyProducer, OutreachProducer, OpinionProducer (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-33.1 | behavioral | HobbyProducer.on_tick() | BacklogItem with hobby topic | Hobby exploration fires |
| AC-33.2 | behavioral | HobbyProducer._on_dispatch | Hobby memory written, reward awarded | Dispatch earns points |
| AC-33.3 | behavioral | OutreachProducer.on_tick() | BacklogItem with outreach topic | Outreach fires |
| AC-33.4 | behavioral | OpinionProducer.on_tick() | BacklogItem with opinion topic | Opinion fires |
| AC-33.5 | behavioral | OpinionProducer._on_dispatch | Opinion memory written to Repo | Dispatch writes memory |

## 4. Unit Test Plan

| Test file | ACs covered | Marks |
|-----------|-------------|-------|
| `tests/test_blog_producer.py` | AC-26.1..26.6 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_reflection_producer.py` | AC-27.1..27.5 | `contract("behavioral")` `scope("unit")` |
| `tests/test_curiosity_producer.py` | AC-28.1..28.4 | `contract("behavioral")` `scope("unit")` |
| `tests/test_emotional_producer.py` | AC-29.1..29.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_concept_skill_producers.py` | AC-30..32.* | `contract("behavioral")` `scope("unit")` |
| `tests/test_hobby_producer.py` | AC-33.1..33.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_outreach_producer.py` | AC-33.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_opinion_producer.py` | AC-33.4..33.5 | `contract("behavioral")` `scope("unit")` |
| `tests/test_skill_artifacts.py` | Skill rendering | `contract("boundary")` `scope("unit")` |

## 5. Property Tests (Hypothesis)

### P-26.1: Title extraction is total on non-empty strings

```python
from maistro_turing.producers.blog import BlogProducer

@given(text=st.text(min_size=1, max_size=500))
@settings(max_examples=100)
def test_extract_title_never_crashes(text):
    title = BlogProducer._extract_title(text)
    assert isinstance(title, str)
```

### P-29.1: Weighted sampling is fair

```python
from maistro_turing.producers.emotional import EmotionalResponseProducer

@given(
    drives=st.dictionaries(
        st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"),
        st.floats(min_value=0.01, max_value=1.0),
        min_size=2, max_size=6,
    )
)
@settings(max_examples=50)
def test_weighted_sample_always_returns_key(drives):
    producer = EmotionalResponseProvider.__new__(EmotionalResponseProducer)
    result = producer._weighted_sample(drives)
    assert result in drives
```

## 6. Integration Test Plan

| Test | What it wires | AC | Marks |
|-------|--------------|-----|-------|
| `test_blog_full_cycle` | BlogProducer → Motivation dispatch → FakeProvider → Repo write → RewardTracker | AC-26 | `contract("cross-service")` `scope("integration")` |
| `test_curiosity_sates_drive` | CuriosityProducer → dispatch → `sate_curiosity()` called → drive drops | AC-28 + AC-23 | `contract("cross-service")` `scope("integration")` |
| `test_concept_to_skill_pipeline` | ConceptInventor → dispatch → reinforce → SkillBuilder picks up → coaching | AC-30 + AC-31 | `contract("cross-service")` `scope("integration")` |
| `test_all_producers_register` | All 8 producers registered with Motivation → each fires on tick | AC-26..33 | `contract("cross-service")` `scope("integration")` |

## 7. Bridge Adapter Specs

No new bridges. Producers depend on:
- `Repo` (Phase 2)
- `SelfRepo` (Phase 3)
- `Motivation` (Phase 4)
- `Reactor` (Phase 1)
- `Provider` (Phase 6 — `FakeProvider` for testing)

## 8. Phase Gate

- [ ] All AC-26..33 tests pass
- [ ] `ruff check packages/maistro-turing/` clean
- [ ] `mypy packages/maistro-turing/ --strict` clean
- [ ] Test count >= 25
- [ ] No `stronghold` imports
- [ ] Old `producers.py` (simplified) fully replaced by `producers/` package
- [ ] All 8 producers register with `Motivation` and fire during tick cycle
