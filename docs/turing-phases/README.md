# Turing Migration Phase Specs

Per-phase specification documents for the AgentTuring → maistro-turing port.
Companion to [`docs/TURING-MIGRATION-SPEC.md`](../TURING-MIGRATION-SPEC.md).

## Status

| Phase | File | Status | Source lines | Target tests |
|-------|------|--------|-------------|-------------|
| 0–1 | (done) | **Complete** | ~350 | 28 |
| 2 | [phase-2-memory.md](phase-2-memory.md) | Not started | ~1,866 | ~60 |
| 3 | [phase-3-self-model.md](phase-3-self-model.md) | Not started | ~3,600 | ~200 |
| 4 | [phase-4-cognition.md](phase-4-cognition.md) | Not started | ~1,842 | ~80 |
| 5 | [phase-5-producers.md](phase-5-producers.md) | Not started | ~1,922 | ~25 |
| 6 | [phase-6-providers-tools.md](phase-6-providers-tools.md) | Not started | ~1,577 | ~50 |
| 7 | [phase-7-runtime.md](phase-7-runtime.md) | Not started | ~6,700 | ~100 |
| 8 | [phase-8-remaining-self-model.md](phase-8-remaining-self-model.md) | Not started | ~2,100 | ~80 |
| 9 | [phase-9-integration.md](phase-9-integration.md) | Not started | ~200 | ~20 |
| **Total** | | | **~19,300** | **370+** |

## Conventions

### AC numbering

Acceptance criteria are numbered `AC-N.M` where N is the AC block number and M is the
sequential criterion within that block. Blocks are assigned per-phase:

| AC block | Phase | Domain |
|----------|-------|--------|
| AC-1.x | 0–1 | Reactor protocol + FakeReactor |
| AC-2.x | 0–1 | Tier weight bounds |
| AC-3.x | 0–1 | EpisodicMemory construction invariants |
| AC-4.x | 0–1 | Write paths (regret/accomplishment/affirmation) |
| AC-5.x | 2 | Repo INV-1..8 durability invariants |
| AC-6.x | 2 | Two-phase budget retrieval |
| AC-7.x | 2 | Working memory scratchpad |
| AC-8.x | 2 | Persistence (schema, restart, durability) |
| AC-9.x | 2 | Reward tracking |
| AC-10.x | 3 | SelfRepo: personality facets CRUD |
| AC-11.x | 3 | SelfRepo: personality items + answers |
| AC-12.x | 3 | SelfRepo: revisions |
| AC-13.x | 3 | SelfRepo: passions, hobbies, interests, preferences |
| AC-14.x | 3 | SelfRepo: skills |
| AC-15.x | 3 | SelfRepo: todos |
| AC-16.x | 3 | SelfRepo: mood |
| AC-17.x | 3 | SelfRepo: activation contributors |
| AC-18.x | 3 | SelfRepo: bootstrap progress |
| AC-19.x | 4 | Motivation: priority ladder + scoring |
| AC-20.x | 4 | Dreaming: 7-phase consolidation |
| AC-21.x | 4 | Daydream writer + producer |
| AC-22.x | 4 | Scheduler: P0 deadlines |
| AC-23.x | 4 | Drives: 6-dim vector |
| AC-24.x | 4 | Contradiction detector |
| AC-25.x | 4 | Tuning: coefficient table |
| AC-26.x | 5 | BlogProducer |
| AC-27.x | 5 | SelfReflectionProducer |
| AC-28.x | 5 | CuriosityProducer |
| AC-29.x | 5 | EmotionalResponseProducer |
| AC-30.x | 5 | ConceptInventor |
| AC-31.x | 5 | SkillBuilder |
| AC-32.x | 5 | SkillExecutor |
| AC-33.x | 5 | HobbyProducer, OutreachProducer, OpinionProducer |
| AC-34.x | 6 | Provider protocol + FakeProvider |
| AC-35.x | 6 | LiteLLM provider |
| AC-36.x | 6 | Tool registry + base protocol |
| AC-37.x | 6 | Individual tools (code_reader, obsidian, RSS, etc.) |
| AC-38.x | 6 | Messaging (SignalWire) |
| AC-39.x | 7 | Runtime config |
| AC-40.x | 7 | Main wiring (sub-phases 7a/7b/7c) |
| AC-41.x | 7 | RealReactor (threading) |
| AC-42.x | 7 | Chat server |
| AC-43.x | 7 | Embedding index + indexing repo |
| AC-44.x | 7 | Journal writer |
| AC-45.x | 7 | Metrics (Prometheus) |
| AC-46.x | 7 | Voice section + maintenance |
| AC-47.x | 7 | Working memory maintenance |
| AC-48.x | 7 | Conversation summary |
| AC-49.x | 7 | Inspection API |
| AC-50.x | 7 | Smoke test runner + workload |
| AC-51.x | 8 | Self interactive bootstrap |
| AC-52.x | 8 | Self signing + import firewall |
| AC-53.x | 8 | Self tool registry |
| AC-54.x | 8 | Self operator review |
| AC-55.x | 8 | Self detectors (learning, affirmation, prospection) |
| AC-56.x | 8 | Self conduit + outbound |
| AC-57.x | 8 | Self near-dup + compaction + forensics |
| AC-58.x | 8 | Self cross-user isolation |
| AC-59.x | 8 | Self retrieval materialize |
| AC-60.x | 8 | Self activation GC + personality drift + session mood + mood decisions |
| AC-61.x | 9 | Standalone boot (`__main__.py`) |
| AC-62.x | 9 | `pyproject.toml` dependency completeness |
| AC-63.x | 9 | Public API exports |
| AC-64.x | 9 | No stronghold imports |
| AC-65.x | 9 | CLAUDE.md + ADR updates |

### Contract types (per ADR-032)

Every AC declares a contract type:

| Type | Meaning | Typical assertion |
|------|---------|------------------|
| **boundary** | Shape + validation of inputs/outputs | `ValueError` on invalid, type checks, range checks |
| **behavioral** | Pre/post/invariant on stateful operations | Round-trip consistency, monotonicity, ordering guarantees |
| **cross-service** | Inter-subsystem or inter-package contracts | Bridge adapter returns correct type, A2A message shape |

### Test marks (per ADR-032)

Every test uses both marks:

```python
@pytest.mark.contract("boundary")     # boundary | behavioral | cross-service
@pytest.mark.scope("unit")            # unit | property | integration | e2e
def test_ac_N_M_description():
    ...
```

### Phase gate (every phase)

A phase is complete when:

- [ ] All AC tests pass (`pytest packages/maistro-turing/tests/ -q`)
- [ ] `ruff check packages/maistro-turing/` clean
- [ ] `mypy packages/maistro-turing/ --strict` clean
- [ ] Test count >= phase minimum (from "Target tests" column above)
- [ ] No `stronghold` imports (`grep -r "stronghold" packages/maistro-turing/` returns nothing)
- [ ] No new `TODO` or `FIXME` comments without a tracking issue

### Source repo

AgentTuring source of truth: `/vmpool/github/stronghold/research/project-turing/sketches/`

```
turing/              # 109 Python files, ~19,300 lines
tests/               # 104 test files, ~22,854 lines
```

Target: `packages/maistro-turing/src/maistro_turing/`

### Per-phase document structure

Each phase spec contains:

1. **Source inventory** — exact file list with line counts from AgentTuring
2. **Target file mapping** — source → maistro_turing destination
3. **Acceptance criteria** — numbered AC-N.M with contract type, pre/post/invariant
4. **Unit test plan** — test file → AC mapping with marks
5. **Property test plan** — Hypothesis strategy code for behavioral ACs
6. **Integration test plan** — cross-subsystem wiring tests
7. **Bridge adapter specs** — new/expanded bridges needed
8. **Phase gate** — completion checklist
