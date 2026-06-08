# Phase 7: Production Runtime

**Goal:** Full subsystem wiring, chat server, RealReactor, metrics, and all runtime
support modules. This is the largest and riskiest phase — `main.py` alone is 2,405 lines.

**Depends on:** Phases 2–6 all complete.

---

## 1. Source Inventory

| Source file | Lines | Description |
|------------|-------|-------------|
| `turing/runtime/main.py` | 2,405 | Full wiring of all subsystems |
| `turing/runtime/chat.py` | 1,276 | Production HTTP chat server |
| `turing/runtime/config.py` | 200 | YAML + env config loading |
| `turing/runtime/reactor.py` | 147 | RealReactor with threading |
| `turing/runtime/actor.py` | 139 | Actor with tool dispatch |
| `turing/runtime/embedding_index.py` | 124 | Vector index for semantic retrieval |
| `turing/runtime/indexing_repo.py` | 132 | Auto-indexing repo wrapper |
| `turing/runtime/conversation_summary.py` | 182 | Conversation arc summarization |
| `turing/runtime/voice_section.py` | — | Self-owned voice block (in main.py) |
| `turing/runtime/voice_section_maintenance.py` | 140 | Periodic voice self-edit |
| `turing/runtime/working_memory_maintenance.py` | 182 | Periodic working-memory self-edit |
| `turing/runtime/journal.py` | 207 | Journal writer |
| `turing/runtime/metrics.py` | 132 | Prometheus metrics |
| `turing/runtime/inspect.py` | 259 | Live inspection API |
| `turing/runtime/smoke.py` | 172 | Smoke test runner |
| `turing/runtime/workload.py` | 270 | Scenario-driven testing |
| `turing/runtime/quota.py` | 102 | Token quota tracker |
| `turing/runtime/pools.py` | 81 | Pool config from YAML |
| `turing/runtime/instrumentation.py` | 61 | Logging setup |
| `turing/runtime/style.py` | 14 | Style constants |
| `turing/runtime/rss_fetcher.py` | 71 | RSS periodic fetcher |
| **Total** | **~6,716** | |

| Source test file | Lines | Key ACs covered |
|-----------------|-------|----------------|
| `tests/test_config.py` | 309 | AC-39.* |
| `tests/test_config_env_and_args.py` | 129 | Config env override |
| `tests/test_main_unit.py` | 507 | AC-40.* (unit-level wiring) |
| `tests/test_main_runtime.py` | 594 | AC-40.* (integration) |
| `tests/test_main_coverage.py` | 234 | AC-40 edge cases |
| `tests/test_real_reactor.py` | 151 | AC-41.* |
| `tests/test_chat.py` | 178 | AC-42.* |
| `tests/test_chat_coverage.py` | 315 | AC-42 edge cases |
| `tests/test_embedding_index.py` | 82 | AC-43.* |
| `tests/test_journal.py` | 477 | AC-44.* |
| `tests/test_metrics.py` | 80 | AC-45.* |
| `tests/test_voice_section_maintenance.py` | ~100 | AC-46.* |
| `tests/test_working_memory_maintenance.py` | 136 | AC-47.* |
| `tests/test_instrumentation.py` | 178 | AC-49.* |
| `tests/test_inspect_coverage.py` | 192 | AC-49.* |
| `tests/test_inspect_cli.py` | 133 | AC-49.* |
| `tests/test_workload.py` | 261 | AC-50.* |
| `tests/test_quota_tracker.py` | 115 | AC-40 (quota) |
| `tests/test_pools.py` | 78 | AC-40 (pools) |
| `tests/test_runtime_integration.py` | 79 | Full integration |
| `tests/test_actor_coverage.py` | 192 | AC-40 (actor) |
| `tests/test_activation_surface_actor.py` | 276 | AC-40 (activation→surface) |
| `tests/test_provider_reactor_coverage.py` | 456 | AC-41 + AC-34 |
| **Total** | **~5,227** | |

## 2. Target File Mapping

All files map from `turing/runtime/` → `maistro_turing/runtime/`:

| Source | Target |
|--------|--------|
| `runtime/config.py` | `maistro_turing/runtime/config.py` |
| `runtime/main.py` | `maistro_turing/runtime/main.py` |
| `runtime/reactor.py` | `maistro_turing/runtime/reactor.py` |
| `runtime/actor.py` | `maistro_turing/runtime/actor.py` |
| `runtime/chat.py` | `maistro_turing/runtime/chat.py` |
| `runtime/embedding_index.py` | `maistro_turing/runtime/embedding_index.py` |
| `runtime/indexing_repo.py` | `maistro_turing/runtime/indexing_repo.py` |
| `runtime/conversation_summary.py` | `maistro_turing/runtime/conversation_summary.py` |
| `runtime/voice_section_maintenance.py` | `maistro_turing/runtime/voice_section_maintenance.py` |
| `runtime/working_memory_maintenance.py` | `maistro_turing/runtime/working_memory_maintenance.py` |
| `runtime/journal.py` | `maistro_turing/runtime/journal.py` |
| `runtime/metrics.py` | `maistro_turing/runtime/metrics.py` |
| `runtime/inspect.py` | `maistro_turing/runtime/inspect.py` |
| `runtime/smoke.py` | `maistro_turing/runtime/smoke.py` |
| `runtime/workload.py` | `maistro_turing/runtime/workload.py` |
| `runtime/quota.py` | `maistro_turing/runtime/quota.py` |
| `runtime/pools.py` | `maistro_turing/runtime/pools.py` |
| `runtime/instrumentation.py` | `maistro_turing/runtime/instrumentation.py` |
| `runtime/style.py` | `maistro_turing/runtime/style.py` |
| `runtime/rss_fetcher.py` | `maistro_turing/runtime/rss_fetcher.py` |

## 3. Sub-phases

Given the size, Phase 7 is split into three sub-phases:

### 7a: Config + Wiring Foundation (AC-39, AC-40 partial)
- `config.py`, `pools.py`, `quota.py`, `instrumentation.py`, `style.py`
- Wire config → Repo → SelfRepo → Motivation → FakeProvider mode
- Verify: config loads, subsystems boot, no crashes

### 7b: Chat + Reactor + Actor (AC-40, AC-41, AC-42)
- `reactor.py` (RealReactor), `actor.py`, `chat.py`
- Wire RealReactor → Motivation → Actor → Tool dispatch → Chat HTTP server
- Verify: chat request → response, reactor ticks, actor dispatches tools

### 7c: Maintenance + Metrics + Support (AC-43..50)
- `embedding_index.py`, `indexing_repo.py`, `conversation_summary.py`
- `voice_section_maintenance.py`, `working_memory_maintenance.py`
- `journal.py`, `metrics.py`, `inspect.py`, `smoke.py`, `workload.py`, `rss_fetcher.py`
- Verify: all maintenance loops run, metrics emit, smoke passes

## 4. Acceptance Criteria

### AC-39: Runtime config (boundary)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-39.1 | boundary | `Config.from_yaml(path)` with valid YAML | Returns Config with all fields populated | YAML loading |
| AC-39.2 | boundary | `Config.from_env()` with env vars set | Env vars override YAML defaults | Env override |
| AC-39.3 | boundary | Config with missing required field | `ValueError` with field name | Required fields enforced |
| AC-39.4 | boundary | `Config.pools` | Returns list of `PoolConfig` | Pools parsed |
| AC-39.5 | behavioral | Config with `auth_token` set | `auth_token` is non-empty string | Auth token loaded |

### AC-40: Main wiring (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-40.1 | behavioral | `main()` with FakeProvider config | All subsystems initialized, no crashes | Boots successfully |
| AC-40.2 | behavioral | `main()` creates Repo + SelfRepo | Both connected to same SQLite/Postgres | Shared connection |
| AC-40.3 | behavioral | `main()` registers all producers | All 8 producers in Motivation backlog | Producer registration |
| AC-40.4 | behavioral | `main()` wires Dreamer + Scheduler | Dreamer scheduled, Scheduler active | Cognitive loops wired |
| AC-40.5 | behavioral | `main()` with `--smoke` flag | Runs smoke tests and exits | Smoke test mode |
| AC-40.6 | boundary | `PoolConfig.from_yaml(pool_entry)` | Returns valid PoolConfig | Pool parsing |

### AC-41: RealReactor — threading (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-41.1 | behavioral | `RealReactor.spawn(fn)` | Returns `Future`, fn executes in thread | Threaded spawn |
| AC-41.2 | behavioral | `RealReactor.tick()` | All registered handlers called | Tick dispatches |
| AC-41.3 | behavioral | `RealReactor.interval(1.0, fn)` | Handler called periodically | Interval fires |
| AC-41.4 | behavioral | `RealReactor.cancel(handle)` | Interval stops firing | Cancel works |
| AC-41.5 | behavioral | `RealReactor` shutdown | All threads joined, no hanging | Clean shutdown |

### AC-42: Chat server (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-42.1 | behavioral | POST `/chat` with message | Returns 200 with response body | Chat responds |
| AC-42.2 | behavioral | POST `/chat` with session_id | Session maintained, history tracked | Session continuity |
| AC-42.3 | behavioral | POST `/chat/feedback` with thumbs_up | RewardTracker.award called | Feedback recorded |
| AC-42.4 | behavioral | GET `/health` | Returns 200 with health status | Health endpoint |
| AC-42.5 | boundary | POST `/chat` without auth token | Returns 401 | Auth enforced |

### AC-43: Embedding index + indexing repo (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-43.1 | behavioral | `EmbeddingIndex.index(text, id)` | Vector stored | Indexing works |
| AC-43.2 | behavioral | `EmbeddingIndex.search(query, top_k=5)` | Returns ranked results | Search works |
| AC-43.3 | behavioral | `IndexingRepo.insert(m)` | Memory indexed automatically | Auto-indexing |

### AC-44: Journal writer (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-44.1 | behavioral | `Journal.write_entry(topic, content)` | Journal file created/appended | Write works |
| AC-44.2 | boundary | Journal with empty topic | Skipped, no crash | Empty topic safe |
| AC-44.3 | behavioral | Multiple journal entries | Entries ordered by timestamp | Chronological order |

### AC-45: Prometheus metrics (boundary)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-45.1 | boundary | Metrics emitted with correct labels | Counter/gauge/histogram with defined label sets | Label correctness |
| AC-45.2 | boundary | GET `/metrics` | Returns Prometheus-format text | Metrics endpoint |

### AC-46: Voice section + maintenance (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-46.1 | behavioral | `VoiceSectionMaintenance.on_tick()` | Voice section edited within max_chars | Periodic self-edit |
| AC-46.2 | boundary | Voice content truncated to `max_chars` | `len(content) <= max_chars` | Size bounded |

### AC-47: Working memory maintenance (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-47.1 | behavioral | `WorkingMemoryMaintenance.on_tick()` | Stale entries removed, priorities adjusted | Periodic cleanup |
| AC-47.2 | behavioral | Maintenance with expired entries | Expired entries removed | TTL enforcement |

### AC-48: Conversation summary (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-48.1 | behavioral | `summarize(turns)` with >= 10 turns | Returns summary string | Summarization works |
| AC-48.2 | behavioral | `summarize(turns)` with < 3 turns | Returns None (too short) | Minimum threshold |

### AC-49: Inspection API (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-49.1 | behavioral | `inspect_memory(repo)` | Returns structured memory stats | Memory inspection |
| AC-49.2 | behavioral | `inspect_self_model(self_repo)` | Returns self-model snapshot | Self-model inspection |
| AC-49.3 | behavioral | CLI `inspect --format json` | Returns valid JSON output | CLI works |

### AC-50: Smoke test + workload (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-50.1 | behavioral | `run_smoke(config)` with FakeProvider | All checks pass, returns 0 | Smoke passes |
| AC-50.2 | behavioral | `Workload.run(scenario)` | Scenario completes, metrics collected | Workload runs |
| AC-50.3 | behavioral | Workload with failure injection | Errors logged, no crash | Failure resilient |

## 5. Unit Test Plan

| Test file | ACs covered | Marks |
|-----------|-------------|-------|
| `tests/test_config.py` | AC-39.1..39.5 | `contract("boundary")` `scope("unit")` |
| `tests/test_config_env_and_args.py` | AC-39.2 | `contract("boundary")` `scope("unit")` |
| `tests/test_main_unit.py` | AC-40.1..40.6 | `contract("behavioral")` `scope("unit")` |
| `tests/test_main_runtime.py` | AC-40 (full boot) | `contract("behavioral")` `scope("integration")` |
| `tests/test_main_coverage.py` | AC-40 edge cases | `contract("behavioral")` `scope("unit")` |
| `tests/test_real_reactor.py` | AC-41.1..41.5 | `contract("behavioral")` `scope("unit")` |
| `tests/test_chat.py` | AC-42.1..42.5 | `contract("behavioral")` `scope("integration")` |
| `tests/test_chat_coverage.py` | AC-42 edge cases | `contract("behavioral")` `scope("unit")` |
| `tests/test_embedding_index.py` | AC-43.1..43.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_journal.py` | AC-44.1..44.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_metrics.py` | AC-45.1..45.2 | `contract("boundary")` `scope("unit")` |
| `tests/test_voice_section_maintenance.py` | AC-46.1..46.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_working_memory_maintenance.py` | AC-47.1..47.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_instrumentation.py` | AC-49 | `contract("boundary")` `scope("unit")` |
| `tests/test_inspect_coverage.py` | AC-49.1..49.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_inspect_cli.py` | AC-49.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_workload.py` | AC-50.2..50.3 | `contract("behavioral")` `scope("integration")` |
| `tests/test_quota_tracker.py` | AC-40 (quota) | `contract("behavioral")` `scope("unit")` |
| `tests/test_pools.py` | AC-40 (pools) | `contract("boundary")` `scope("unit")` |
| `tests/test_runtime_integration.py` | Full integration | `contract("cross-service")` `scope("integration")` |
| `tests/test_actor_coverage.py` | AC-40 (actor) | `contract("behavioral")` `scope("unit")` |
| `tests/test_activation_surface_actor.py` | AC-40 (activation→surface) | `contract("cross-service")` `scope("integration")` |
| `tests/test_provider_reactor_coverage.py` | AC-41 + AC-34 | `contract("behavioral")` `scope("unit")` |

## 6. Property Tests (Hypothesis)

### P-40.1: Config round-trip through YAML

```python
@given(
    db_path=st.text(min_size=1, max_size=100, alphabet="abcdefghijklmnopqrstuvwxyz/_"),
    tick_interval=st.floats(min_value=0.1, max_value=60.0),
    max_entries=st.integers(min_value=1, max_value=1000),
)
@settings(max_examples=50)
def test_config_yaml_round_trip(db_path, tick_interval, max_entries):
    import yaml, tempfile
    from maistro_turing.runtime.config import Config
    cfg = Config(db_path=db_path, tick_interval=tick_interval,
                 working_memory_max_entries=max_entries)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml') as f:
        yaml.dump(cfg.to_dict(), f)
        f.flush()
        loaded = Config.from_yaml(f.name)
    assert loaded.db_path == db_path
    assert loaded.tick_interval == tick_interval
```

### P-43.1: Embedding search returns top-k

```python
@given(
    n_docs=st.integers(min_value=5, max_value=50),
    top_k=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=30)
def test_embedding_search_returns_top_k(n_docs, top_k):
    from maistro_turing.runtime.embedding_index import EmbeddingIndex
    from maistro_turing.providers.fake import FakeProvider
    idx = EmbeddingIndex(FakeProvider())
    for i in range(n_docs):
        idx.index(f"document {i} about topic {i % 5}", f"doc-{i}")
    results = idx.search("topic 2", top_k=top_k)
    assert len(results) <= top_k
```

## 7. Integration Test Plan

| Test | What it wires | AC | Marks |
|-------|--------------|-----|-------|
| `test_full_boot_fake_provider` | Config → main() → all subsystems up → tick → shutdown | AC-40 | `contract("cross-service")` `scope("integration")` |
| `test_chat_round_trip` | HTTP POST /chat → Actor → Repo → response | AC-42 | `contract("cross-service")` `scope("integration")` |
| `test_smoke_with_fake` | main() --smoke → all smoke checks pass | AC-50 | `contract("cross-service")` `scope("e2e")` |
| `test_workload_scenario` | Workload.run("basic") → metrics collected | AC-50 | `contract("cross-service")` `scope("integration")` |
| `test_maintenance_cycle` | tick → voice_maintenance + wm_maintenance → content updated | AC-46 + AC-47 | `contract("cross-service")` `scope("integration")` |

## 8. Bridge Adapter Specs

### New bridge: TuringEmbeddingBridge

(Defined in Phase 6 spec. Consumed here by `EmbeddingIndex` and `IndexingRepo`.)

### Existing bridges used:

| Bridge | Where used |
|--------|-----------|
| `TuringMemoryBridge` | main.py wiring |
| `TuringProviderBridge` | Actor, Chat, Producers |
| `TuringSecurityBridge` | Warden gate on self-writes |
| `TuringClassifierBridge` | Chat message classification |
| `TuringReactorBridge` | RealReactor → FakeReactor switching |
| `TuringSelfRepoBridge` | Surface, Bootstrap, Mood |
| `TuringRetrievalBridge` | Chat context retrieval |
| `TuringWorkingMemoryBridge` | Chat context, maintenance |
| `TuringEmbeddingBridge` | EmbeddingIndex |

## 9. Phase Gate

- [ ] All AC-39..50 tests pass
- [ ] `ruff check packages/maistro-turing/` clean
- [ ] `mypy packages/maistro-turing/ --strict` clean
- [ ] Test count >= 100
- [ ] No `stronghold` imports
- [ ] `main()` boots with FakeProvider config, ticks 10 times, shuts down cleanly
- [ ] Chat server responds to POST /chat with FakeProvider
- [ ] Smoke test passes with exit code 0
