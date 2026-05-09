# AgentTuring → maistro-turing Migration Specification

**Date:** 2026-05-08
**Status:** Draft
**Source:** `/vmpool/github/stronghold/research/project-turing/sketches/turing/` (AgentTuring)
**Target:** `/vmpool/github/maistro-engine/packages/maistro-turing/`
**Scope:** Extract AgentTuring from stronghold monorepo into standalone `maistro-turing` package backed by `maistro-core`

---

## 1. Current State

### AgentTuring (source of truth)

- **Location:** Inside stronghold repo under `research/project-turing/sketches/turing/`
- **Size:** ~19,300 lines across 92 Python files
- **Dependencies:** `httpx`, `PyYAML` (2 pip deps total)
- **Stronghold coupling:** ZERO imports. One optional HTTP client (`StrongholdClient`) gated behind 2 env vars.
- **Repo:** Pushed to `BlakeMatthews-dev/AgentTuring` (main branch)
- **Tests:** 370+ tests in `sketches/tests/`, all standalone

### maistro-turing (partial port, exists already)

- **Location:** `packages/maistro-turing/src/maistro_turing/`
- **Size:** 1,290 lines across 5 files
- **What it has:**
  - `self_model.py` — value types (Traits, HEXACO facets, Mood, Skill, etc.) — nearly complete
  - `bridge.py` — 4 bridge adapters to maistro-core (Memory, Security, Provider, Classifier)
  - `runtime.py` — basic config, actor, chat session (skeleton)
  - `producers.py` — 4 simplified producers (Blog, Reflection, Curiosity, Emotional)
- **What it's missing:** ~18,000 lines and 87 files — see gap analysis below

### maistro-core (substrate)

- Shared runtime with: memory (episodic + learnings), security (warden + sentinel), classifier, router, agents, persistence (PostgreSQL), protocols, types
- maistro-turing depends on `maistro-core>=0.1.0`
- Key protocols available: `EpisodicStore`, `LearningStore`, `LLMClient`, `IntentClassifier`, warden, sentinel

---

## 2. Migration Principles

1. **maistro-turing owns the autonoetic self.** Everything that makes AgentTuring unique (episodic memory tiers, dreaming, daydreaming, motivation, self-model, HEXACO personality, drives) lives here.
2. **maistro-core owns the substrate.** Memory persistence, security scanning, LLM calls, classification, routing — maistro-turing delegates via bridge adapters.
3. **No SQLite in production.** AgentTuring uses SQLite for dev/testing. Production uses maistro-core's PostgreSQL persistence layer. Both paths must work.
4. **Bridge-first design.** Every maistro-core dependency goes through a bridge protocol in `bridge.py`. AgentTuring's native protocols become internal implementation detail.
5. **Tests port 1:1.** Every test in AgentTuring's `sketches/tests/` gets ported to `packages/maistro-turing/tests/`. No test left behind.
6. **The agent runs standalone.** After migration, `pip install maistro-turing` + a config file = running Turing agent. No stronghold, no conductor.

---

## 3. Target Package Layout

```
packages/maistro-turing/
├── pyproject.toml
└── src/maistro_turing/
    ├── __init__.py
    │
    ├── bridge.py                    # Bridge adapters → maistro-core (EXPAND existing)
    │
    ├── types.py                     # EpisodicMemory, MemoryTier, SourceKind (NEW)
    ├── protocols.py                 # MemoryRepo, WorkingMemoryStore protocols (NEW)
    ├── tiers.py                     # Weight bounds, clamp_weight (NEW)
    │
    ├── memory/
    │   ├── __init__.py
    │   ├── repo.py                  # SQLite Repo (dev/test) (NEW)
    │   ├── postgres_repo.py         # PostgreSQL Repo (production) (NEW)
    │   ├── retrieval.py             # Two-phase budget retrieval (NEW)
    │   ├── write_paths.py           # REGRET/ACCOMPLISHMENT/AFFIRMATION (NEW)
    │   └── working_memory.py        # Bounded scratchpad (NEW)
    │
    ├── self_model/
    │   ├── __init__.py              # Re-exports
    │   ├── types.py                 # Port of self_model.py (REPLACE existing)
    │   ├── repo.py                  # Self-model persistence (NEW, 1288 lines)
    │   ├── identity.py              # Self-id bootstrap (NEW)
    │   ├── activation.py            # Activation graph (NEW)
    │   ├── nodes.py                 # Node CRUD (NEW)
    │   ├── bootstrap.py             # HEXACO personality bootstrap (NEW)
    │   ├── interactive_bootstrap.py # Chat-based bootstrap (NEW)
    │   ├── personality.py           # Retest + drift (NEW)
    │   ├── mood.py                  # Mood computation (NEW)
    │   ├── session_mood.py          # Per-session mood (NEW)
    │   ├── todos.py                 # Self-todo management (NEW)
    │   ├── surface.py               # Outward presentation (NEW)
    │   ├── naming.py                # Self-naming ritual (NEW)
    │   ├── coaching.py              # Self-coaching (NEW)
    │   ├── budget.py                # Token budget (NEW)
    │   ├── conversations.py         # Conversation tracking (NEW)
    │   ├── reflection.py            # Self-reflection triggers (NEW)
    │   ├── prospection.py           # Future-thinking (NEW)
    │   ├── contributors.py          # Activation contributors (NEW)
    │   ├── memory_bridge.py         # Self-model ↔ memory bridge (NEW)
    │   ├── sentinel.py              # Self-write monitoring (NEW)
    │   ├── warden_gate.py           # Security gate (NEW)
    │   ├── import_firewall.py       # Import validation (NEW)
    │   ├── signing.py               # Crypto signing (NEW)
    │   ├── operator_review.py       # Operator review gate (NEW)
    │   ├── learning_detector.py     # Learning event detection (NEW)
    │   ├── affirmation_detector.py  # Affirmation detection (NEW)
    │   ├── prospection_detector.py  # Prospection detection (NEW)
    │   ├── conduit.py               # Cross-subsystem conduit (NEW)
    │   ├── outbound.py              # Outbound messaging (NEW)
    │   ├── near_dup.py              # Near-duplicate detection (NEW)
    │   ├── compaction.py            # Self-model compaction (NEW)
    │   ├── forensics.py             # Forensic inspection (NEW)
    │   ├── cross_user.py            # Cross-user isolation (NEW)
    │   ├── retrieval_materialize.py # Materialize retrieval (NEW)
    │   └── tool_registry.py         # Self-model tool dispatch (NEW)
    │
    ├── cognition/
    │   ├── __init__.py
    │   ├── reactor.py               # Reactor protocol + FakeReactor (NEW)
    │   ├── motivation.py            # Priority ladder, pressure, backlog (NEW)
    │   ├── dreaming.py              # 7-phase WISDOM consolidation (NEW)
    │   ├── daydream.py              # DaydreamWriter + DaydreamProducer (NEW)
    │   ├── scheduler.py             # P0 deadline scheduling (NEW)
    │   ├── tuning.py                # CoefficientTable + self-tuning (NEW)
    │   ├── drives.py                # 6-dim drive vector (NEW)
    │   └── contradiction.py         # Contradiction detector (NEW)
    │
    ├── producers/
    │   ├── __init__.py
    │   ├── blog.py                  # Blog post generation (REPLACE simplified)
    │   ├── reflection.py            # Self-reflection producer (REPLACE simplified)
    │   ├── curiosity.py             # Curiosity-driven research (REPLACE simplified)
    │   ├── emotional.py             # Emotional response (REPLACE simplified)
    │   ├── concept_skill.py         # Concept invention + skill coaching (NEW)
    │   ├── outreach.py              # Social outreach (NEW)
    │   ├── opinion.py               # Opinion formation (NEW)
    │   └── hobby.py                 # Hobby exploration (NEW)
    │
    ├── runtime/
    │   ├── __init__.py
    │   ├── config.py                # Full config with pools, voice seed, embedding (REPLACE skeleton)
    │   ├── main.py                  # Full wiring of all subsystems (NEW)
    │   ├── reactor.py               # RealReactor with threading (NEW)
    │   ├── actor.py                 # Full actor with tool dispatch (REPLACE skeleton)
    │   ├── chat.py                  # Production chat server (NEW)
    │   ├── embedding_index.py       # Vector index for semantic retrieval (NEW)
    │   ├── indexing_repo.py         # Auto-indexing repo wrapper (NEW)
    │   ├── pools.py                 # Pool config from YAML (NEW)
    │   ├── quota.py                 # Token quota tracker (NEW)
    │   ├── journal.py               # Journal writer (NEW)
    │   ├── metrics.py               # Prometheus metrics (NEW)
    │   ├── inspect.py               # Live inspection API (NEW)
    │   ├── conversation_summary.py  # Conversation arc summarization (NEW)
    │   ├── voice_section.py         # Self-owned voice block (NEW)
    │   ├── voice_section_maintenance.py  # Periodic voice self-edit (NEW)
    │   ├── working_memory_maintenance.py # Periodic working-memory self-edit (NEW)
    │   ├── workload.py              # Scenario-driven testing (NEW)
    │   ├── smoke.py                 # Smoke test runner (NEW)
    │   ├── instrumentation.py       # Logging setup (NEW)
    │   └── style.py                 # Style constants (NEW)
    │
    ├── providers/
    │   ├── __init__.py
    │   ├── base.py                  # Provider protocols (NEW)
    │   ├── fake.py                  # Deterministic test provider (NEW)
    │   ├── litellm.py               # LiteLLM production provider (NEW)
    │   └── messaging.py             # SignalWire SMS (NEW)
    │
    ├── tools/
    │   ├── __init__.py
    │   ├── base.py                  # Tool protocol + registry (NEW)
    │   ├── code_reader.py           # Sandboxed file reading (NEW)
    │   ├── obsidian.py              # Obsidian vault writer (NEW)
    │   ├── rss.py                   # RSS reader (NEW)
    │   ├── rss_seen_repo.py         # RSS dedup tracker (NEW)
    │   ├── search.py                # Web search (NEW)
    │   ├── wiki.py                  # Wiki writer (NEW)
    │   ├── wordpress.py             # WordPress REST API (NEW)
    │   └── newsletter.py            # Newsletter composition (NEW)
    │
    └── schema/
        ├── sqlite.sql               # SQLite DDL (NEW)
        ├── postgres.sql             # PostgreSQL DDL (NEW)
        └── migrations/              # Schema migrations (NEW)
            └── 001_add_self_id_fk.py
```

**Summary:** ~90 files, ~18,000 lines of ported code + ~2,000 lines of bridge adapter extensions.

---

## 4. Bridge Adapter Extensions

Current `bridge.py` has 4 adapters. The migration requires these additions:

| Adapter | Wraps | New Methods | Lines |
|---|---|---|---|
| **TuringMemoryBridge** (expand) | maistro-core `EpisodicStore` | `walk_lineage`, `set_superseded_by`, `increment_contradiction_count`, `decay_weight`, `soft_delete`, `find` with filters | +200 |
| **TuringSelfRepoBridge** | maistro-core persistence or self-contained SQLite | Full self-model CRUD (facets, skills, hobbies, moods, todos, contributors, etc.) | ~150 |
| **TuringWorkingMemoryBridge** | `WorkingMemory` scratchpad | `entries`, `add`, `remove`, `update_priority`, `clear`, `render` | ~50 |
| **TuringRetrievalBridge** | Retrieval engine | Two-phase budget retrieval, semantic retrieve, recency decay | ~100 |
| **TuringReactorBridge** | Tick loop / event dispatch | `tick`, `spawn`, `interval`, `cancel` | ~80 |
| **TuringEmbeddingBridge** | Embedding index / vector search | `index`, `search` | ~60 |

**Total bridge extensions: ~640 lines**

---

## 5. Phased Migration Plan

### Phase 0: Pre-flight (1 day)

- [ ] Create migration branch on maistro-engine: `turing/full-port`
- [ ] Verify maistro-core tests pass green: `pytest packages/maistro-core/tests/ -q`
- [ ] Verify existing maistro-turing tests pass: `pytest packages/maistro-turing/tests/ -q`
- [ ] Snapshot AgentTuring test count baseline: `pytest sketches/tests/ --co -q | tail -1`
- [ ] Add `__pycache__` to `.gitignore` if missing
- [ ] Create target directory structure (empty `__init__.py` files)

### Phase 1: Core Types & Protocols (2-3 days)

**Goal:** All value types and protocols in place. Tests compile and pass.

- [ ] Port `types.py` → `maistro_turing/types.py` (EpisodicMemory, MemoryTier, SourceKind)
- [ ] Port `protocols.py` → `maistro_turing/protocols.py` (MemoryRepo, WorkingMemoryStore)
- [ ] Port `tiers.py` → `maistro_turing/tiers.py` (WEIGHT_BOUNDS, clamp_weight)
- [ ] Port `reactor.py` → `maistro_turing/cognition/reactor.py` (Reactor protocol + FakeReactor)
- [ ] Expand `bridge.py` with `TuringMemoryBridge` additions (walk_lineage, find, decay, etc.)
- [ ] Port associated tests: `test_types.py`, `test_protocols.py`, `test_tiers.py`
- [ ] Verify: `ruff check` + `mypy --strict` + `pytest` all green

### Phase 2: Memory Layer (3-4 days)

**Goal:** Full episodic memory with SQLite (dev) and PostgreSQL (prod).

- [ ] Port `repo.py` → `maistro_turing/memory/repo.py` (SQLite Repo, INV-1..8)
- [ ] Port `postgres_repo.py` → `maistro_turing/memory/postgres_repo.py`
- [ ] Port `retrieval.py` → `maistro_turing/memory/retrieval.py` (two-phase budget retrieval)
- [ ] Port `write_paths.py` → `maistro_turing/memory/write_paths.py` (REGRET/ACCOMPLIMENT/AFFIRMATION)
- [ ] Port `working_memory.py` → `maistro_turing/memory/working_memory.py`
- [ ] Add `TuringRetrievalBridge`, `TuringWorkingMemoryBridge` to `bridge.py`
- [ ] Port schema files → `maistro_turing/schema/`
- [ ] Port associated tests
- [ ] Verify: `ruff check` + `mypy --strict` + `pytest` all green

### Phase 3: Self-Model (4-5 days)

**Goal:** Complete self-model identity system with persistence.

- [ ] Port `self_model.py` → `maistro_turing/self_model/types.py` (replace existing `self_model.py`)
- [ ] Port `self_repo.py` → `maistro_turing/self_model/repo.py` (1,288 lines)
- [ ] Port core self-model modules (priority order):
  1. `self_identity.py` → `identity.py`
  2. `self_nodes.py` → `nodes.py`
  3. `self_bootstrap.py` → `bootstrap.py`
  4. `self_personality.py` → `personality.py`
  5. `self_mood.py` → `mood.py`
  6. `self_activation.py` → `activation.py`
  7. `self_todos.py` → `todos.py`
  8. `self_contributors.py` → `contributors.py`
  9. `self_surface.py` → `surface.py`
  10. `self_naming.py` → `naming.py`
  11. `self_conversations.py` → `conversations.py`
  12. `self_memory_bridge.py` → `memory_bridge.py`
  13. `self_sentinel.py` → `sentinel.py`
  14. `self_warden_gate.py` → `warden_gate.py`
  15. `self_budget.py` → `budget.py`
- [ ] Add `TuringSelfRepoBridge` to `bridge.py`
- [ ] Port all self-model tests
- [ ] Verify: `ruff check` + `mypy --strict` + `pytest` all green

### Phase 4: Cognitive Engine (3-4 days)

**Goal:** Autonomous inner life — motivation, dreaming, daydreaming, drives.

- [ ] Port `motivation.py` → `maistro_turing/cognition/motivation.py` (priority ladder, pressure, backlog)
- [ ] Port `dreaming.py` → `maistro_turing/cognition/dreaming.py` (7-phase consolidation)
- [ ] Port `daydream.py` → `maistro_turing/cognition/daydream.py` (DaydreamWriter + Producer)
- [ ] Port `scheduler.py` → `maistro_turing/cognition/scheduler.py` (P0 deadlines)
- [ ] Port `tuning.py` → `maistro_turing/cognition/tuning.py` (CoefficientTable + tuner)
- [ ] Port `drives.py` → `maistro_turing/cognition/drives.py` (6-dim drive vector)
- [ ] Port `detectors/contradiction.py` → `maistro_turing/cognition/contradiction.py`
- [ ] Port all cognition tests
- [ ] Verify: `ruff check` + `mypy --strict` + `pytest` all green

### Phase 5: Producers (2 days)

**Goal:** All 8 producers ported, upgraded from simplified versions.

- [ ] Refactor `producers.py` into `producers/` package
- [ ] Port full `blog_producer.py` → `producers/blog.py` (replace simplified)
- [ ] Port full `self_reflection_producer.py` → `producers/reflection.py` (replace simplified)
- [ ] Port full `curiosity_producer.py` → `producers/curiosity.py` (replace simplified)
- [ ] Port full `emotional_producer.py` → `producers/emotional.py` (replace simplified)
- [ ] Port `concept_skill_producers.py` → `producers/concept_skill.py` (NEW)
- [ ] Port `outreach_producer.py` → `producers/outreach.py` (NEW)
- [ ] Port `opinion_producer.py` → `producers/opinion.py` (NEW)
- [ ] Port `hobby_producer.py` → `producers/hobby.py` (NEW)
- [ ] Port all producer tests
- [ ] Verify: `ruff check` + `mypy --strict` + `pytest` all green

### Phase 6: Providers & Tools (2 days)

**Goal:** LLM providers and tool registry.

- [ ] Port `providers/base.py` → `providers/base.py`
- [ ] Port `providers/fake.py` → `providers/fake.py`
- [ ] Port `providers/litellm.py` → `providers/litellm.py`
- [ ] Port `providers/messaging.py` → `providers/messaging.py`
- [ ] Port `tools/base.py` → `tools/base.py` (Tool protocol + registry)
- [ ] Port tools: `code_reader`, `obsidian`, `rss`, `rss_seen_repo`, `search`, `wiki`, `wordpress`, `newsletter`
- [ ] **Drop** `code_modification.py` (StrongholdClient) — replaced by maistro-core
- [ ] Port all provider + tool tests
- [ ] Verify: `ruff check` + `mypy --strict` + `pytest` all green

### Phase 7: Production Runtime (3-4 days)

**Goal:** Full wiring, chat server, metrics, long-running process.

- [ ] Port `runtime/config.py` → replace existing `runtime.py` config
- [ ] Port `runtime/main.py` → `runtime/main.py` (2,405 lines — adapt wiring to use bridges)
- [ ] Port `runtime/reactor.py` → `runtime/reactor.py` (RealReactor with threading)
- [ ] Port `runtime/actor.py` → replace existing actor
- [ ] Port `runtime/chat.py` → `runtime/chat.py` (production chat server)
- [ ] Port `runtime/embedding_index.py` + `indexing_repo.py`
- [ ] Port `runtime/pools.py`, `quota.py`
- [ ] Port `runtime/journal.py`, `metrics.py`, `inspect.py`
- [ ] Port `runtime/conversation_summary.py`
- [ ] Port `runtime/voice_section.py` + `voice_section_maintenance.py`
- [ ] Port `runtime/working_memory_maintenance.py`
- [ ] Port `runtime/workload.py`, `smoke.py`, `instrumentation.py`, `style.py`
- [ ] Port remaining self-model modules (24 files: `self_interactive_bootstrap`, `self_import_firewall`, `self_tool_registry`, etc.)
- [ ] Wire everything together in `runtime/main.py`
- [ ] Port all runtime tests
- [ ] Verify: `ruff check` + `mypy --strict` + `pytest` all green

### Phase 8: Remaining Self-Model + Polish (2 days)

**Goal:** Complete all self-model modules, final integration.

- [ ] Port remaining 24 `self_*` modules not covered in Phase 3
- [ ] Port `bootstrap_cli.py` → CLI entry point
- [ ] Port `__main__.py`
- [ ] Port schema migrations
- [ ] Update `pyproject.toml` dependencies (verify all deps listed)
- [ ] Full test suite pass with coverage check
- [ ] Update `__init__.py` with all public exports
- [ ] Smoke test: `python -m maistro_turing` boots and responds to chat
- [ ] Verify: `ruff check` + `mypy --strict` + `pytest` all green

### Phase 9: Integration & Cleanup (1-2 days)

- [ ] Update `maistro-engine/CLAUDE.md` with new commands
- [ ] Update `maistro-engine/CONSOLIDATION-PLAN.md` — mark Turing tasks complete
- [ ] Write ADR for Turing migration decisions
- [ ] Remove `code_modification.py` (StrongholdClient) from AgentTuring — now in maistro-core
- [ ] Update `BlakeMatthews-dev/AgentTuring` README to point to maistro-turing
- [ ] Verify standalone: `pip install -e packages/maistro-turing` + config = running agent
- [ ] Verify with maistro-core: `pip install -e packages/maistro-core packages/maistro-turing` + full stack works

---

## 6. Effort Estimate

| Phase | Days | Lines Ported | Files |
|---|---|---|---|
| Phase 0: Pre-flight | 1 | 0 | 0 |
| Phase 1: Core Types & Protocols | 2-3 | ~350 | 5 |
| Phase 2: Memory Layer | 3-4 | ~1,600 | 7 |
| Phase 3: Self-Model | 4-5 | ~3,500 | 18 |
| Phase 4: Cognitive Engine | 3-4 | ~2,500 | 8 |
| Phase 5: Producers | 2 | ~1,300 | 9 |
| Phase 6: Providers & Tools | 2 | ~1,500 | 12 |
| Phase 7: Production Runtime | 3-4 | ~6,500 | 20 |
| Phase 8: Remaining Self-Model + Polish | 2 | ~2,400 | 26 |
| Phase 9: Integration & Cleanup | 1-2 | ~200 | 5 |
| **Total** | **23-34 days** | **~19,350** | **~110** |

**Realistic estimate with testing, debugging, and bridge adaptation: 4-5 weeks of focused work.**

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Bridge protocol mismatches (AgentTuring's protocols don't map cleanly to maistro-core) | Medium | High | Phase 1 establishes all bridge contracts first; break early |
| Self-model repo is 1,288 lines of SQLite-specific code | High | Medium | Keep SQLite for dev/test, add PostgreSQL bridge for production |
| runtime/main.py wiring is 2,405 lines with many inter-dependencies | High | Medium | Port incrementally; start with FakeProvider mode, add providers one at a time |
| Test gaps — some AgentTuring tests may depend on SQLite-specific behavior | Medium | Low | Run AgentTuring tests against bridges; fix discrepancies immediately |
| Circular imports between self-model modules | Low | High | `__init__.py` re-exports carefully; lazy imports where needed |

---

## 8. Acceptance Criteria

The migration is complete when:

1. **All 370+ AgentTuring tests pass** under `packages/maistro-turing/tests/`
2. **`ruff check` + `mypy --strict`** pass clean on all `maistro-turing` code
3. **`python -m maistro_turing`** boots with a config file and enters the reactor loop
4. **Chat works:** send a message, get a response, memory is stored
5. **Dreaming works:** after enough memories, consolidation runs and produces WISDOM-tier memories
6. **No stronghold imports:** `grep -r "stronghold" packages/maistro-turing/` returns nothing
7. **`pip install maistro-turing`** works standalone (with maistro-core)
8. **Coverage ≥ 80%** on all ported modules

---

## 9. What Gets Dropped

| Module | Reason |
|---|---|
| `runtime/tools/code_modification.py` (StrongholdClient) | Replaced by maistro-core tool dispatch. HTTP client for stronghold is not part of the autonoetic self. |
| `=7.1` (artifact in sketches/) | Build artifact, not code |

Everything else ports. No functionality loss.

---

## 10. Post-Migration: AgentTuring Repo

After the migration, `BlakeMatthews-dev/AgentTuring` becomes:

- **Archive / reference implementation** — README points to `maistro-turing`
- **Research playground** — future experiments that aren't ready for the shared package
- **Not a dependency** — nothing imports from it

The canonical source of truth for the Turing autonoetic agent becomes `maistro-turing` inside `maistro-engine`.
