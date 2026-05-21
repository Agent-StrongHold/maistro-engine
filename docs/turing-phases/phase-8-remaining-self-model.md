# Phase 8: Remaining Self-Model + Polish

**Goal:** Port all remaining self_* modules not covered in Phase 3 — interactive bootstrap,
signing, import firewall, tool registry, operator review, detectors, conduit, outbound,
near-dup, compaction, forensics, cross-user, retrieval materialize, activation GC,
personality drift, session mood, mood decisions, conduit mode.

**Depends on:** Phase 2 (Repo), Phase 3 (self-model core).

---

## 1. Source Inventory

| Source file | Lines | Description |
|------------|-------|-------------|
| `turing/self_interactive_bootstrap.py` | 103 | Chat-based personality bootstrap |
| `turing/self_signing.py` | 59 | Crypto signing for self-model writes |
| `turing/self_import_firewall.py` | 105 | Import validation |
| `turing/self_tool_registry.py` | 630 | Self-model tool dispatch (largest module) |
| `turing/self_operator_review.py` | 100 | Operator review gate |
| `turing/self_learning_detector.py` | 115 | Learning event detection |
| `turing/self_affirmation_detector.py` | 81 | Affirmation detection |
| `turing/self_prospection_detector.py` | 100 | Prospection detection |
| `turing/self_conduit.py` | 260 | Cross-subsystem conduit |
| `turing/self_conduit_mode.py` | 39 | Conduit mode enum |
| `turing/self_outbound.py` | 56 | Outbound messaging |
| `turing/self_near_dup.py` | 56 | Near-duplicate detection |
| `turing/self_compaction.py` | 52 | Self-model compaction |
| `turing/self_forensics.py` | 47 | Forensic inspection |
| `turing/self_cross_user.py` | 47 | Cross-user isolation |
| `turing/self_retrieval_materialize.py` | 73 | Materialize retrieval results |
| `turing/self_activation_gc.py` | 32 | Activation contributor garbage collection |
| `turing/self_personality_drift.py` | 41 | Personality drift detection |
| `turing/self_session_mood.py` | 117 | Per-session mood tracking |
| `turing/self_mood_decisions.py` | 62 | Mood decision helpers |
| `turing/self_prospection.py` | 91 | Future-thinking module |
| `turing/self_reflection.py` | 83 | Self-reflection triggers |
| **Total** | **~2,348** | |

| Source test file | Lines | Key ACs covered |
|-----------------|-------|----------------|
| `tests/test_self_interactive_bootstrap.py` | 166 | AC-51.* |
| `tests/test_self_signing.py` | 120 | AC-52.* |
| `tests/test_self_import_firewall.py` | 115 | AC-52.* |
| `tests/test_self_tool_registry.py` | 374 | AC-53.* |
| `tests/test_self_tool_registry_bdd.py` | 644 | AC-53.* (BDD scenarios) |
| `tests/test_self_operator_review.py` | 77 | AC-54.* |
| `tests/test_self_learning_detector.py` | 141 | AC-55.* |
| `tests/test_self_affirmation_detector.py` | 152 | AC-55.* |
| `tests/test_self_prospection_detector.py` | 161 | AC-55.* |
| `tests/test_self_conduit.py` | 101 | AC-56.* |
| `tests/test_self_conduit_mode.py` | 37 | AC-56.* |
| `tests/test_self_outbound.py` | 122 | AC-56.* |
| `tests/test_self_near_dup.py` | 58 | AC-57.* |
| `tests/test_self_compaction.py` | 85 | AC-57.* |
| `tests/test_self_forensics.py` | 65 | AC-57.* |
| `tests/test_self_cross_user.py` | 100 | AC-58.* |
| `tests/test_self_retrieval_materialize.py` | 120 | AC-59.* |
| `tests/test_self_activation_gc.py` | 94 | AC-60.* |
| `tests/test_self_personality_drift.py` | 99 | AC-60.* |
| `tests/test_self_session_mood.py` | 85 | AC-60.* |
| `tests/test_self_mood_decisions.py` | 128 | AC-60.* |
| `tests/test_self_write_preconditions.py` | 1,042 | Tool registry preconditions |
| `tests/test_self_write_preconditions_bdd.py` | 1,195 | Tool registry BDD |
| `tests/test_self_prospection.py` | 156 | Prospection |
| `tests/test_self_reflection.py` | 96 | Reflection |
| `tests/test_conduit_runtime_bdd.py` | 562 | Conduit BDD scenarios |
| `tests/test_memory_mirroring.py` | 559 | Memory mirroring |
| `tests/test_memory_mirroring_bdd.py` | 591 | Memory mirroring BDD |
| `tests/test_warden_self_writes_bdd.py` | 255 | Warden self-writes BDD |
| **Total** | **~7,607** | |

## 2. Target File Mapping

| Source | Target |
|--------|--------|
| `self_interactive_bootstrap.py` | `maistro_turing/self_model/interactive_bootstrap.py` |
| `self_signing.py` | `maistro_turing/self_model/signing.py` |
| `self_import_firewall.py` | `maistro_turing/self_model/import_firewall.py` |
| `self_tool_registry.py` | `maistro_turing/self_model/tool_registry.py` |
| `self_operator_review.py` | `maistro_turing/self_model/operator_review.py` |
| `self_learning_detector.py` | `maistro_turing/self_model/learning_detector.py` |
| `self_affirmation_detector.py` | `maistro_turing/self_model/affirmation_detector.py` |
| `self_prospection_detector.py` | `maistro_turing/self_model/prospection_detector.py` |
| `self_conduit.py` | `maistro_turing/self_model/conduit.py` |
| `self_conduit_mode.py` | `maistro_turing/self_model/conduit_mode.py` |
| `self_outbound.py` | `maistro_turing/self_model/outbound.py` |
| `self_near_dup.py` | `maistro_turing/self_model/near_dup.py` |
| `self_compaction.py` | `maistro_turing/self_model/compaction.py` |
| `self_forensics.py` | `maistro_turing/self_model/forensics.py` |
| `self_cross_user.py` | `maistro_turing/self_model/cross_user.py` |
| `self_retrieval_materialize.py` | `maistro_turing/self_model/retrieval_materialize.py` |
| `self_activation_gc.py` | `maistro_turing/self_model/activation_gc.py` |
| `self_personality_drift.py` | `maistro_turing/self_model/personality_drift.py` |
| `self_session_mood.py` | `maistro_turing/self_model/session_mood.py` |
| `self_mood_decisions.py` | `maistro_turing/self_model/mood_decisions.py` |
| `self_prospection.py` | `maistro_turing/self_model/prospection.py` |
| `self_reflection.py` | `maistro_turing/self_model/reflection.py` |

## 3. Acceptance Criteria

### AC-51: Interactive bootstrap (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-51.1 | behavioral | `InteractiveBootstrap.ask_next_question()` | Returns PersonalityItem or None if complete | Question flow |
| AC-51.2 | behavioral | `InteractiveBootstrap.submit_answer(answer)` | Answer stored, progress updated | Answer recording |
| AC-51.3 | behavioral | All 20 questions answered | Facet scores computed, bootstrap complete | Completion |
| AC-51.4 | boundary | Answer after bootstrap complete | `AlreadyBootstrapped` raised | No double bootstrap |

### AC-52: Signing + import firewall (boundary)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-52.1 | behavioral | `sign(data)` then `verify(signature, data)` | Returns True | Signing round-trip |
| AC-52.2 | behavioral | `verify(bad_sig, data)` | Returns False | Bad signature rejected |
| AC-52.3 | boundary | `ImportFirewall.check("turing.self_model")` | Returns True (allowed) | Internal imports allowed |
| AC-52.4 | boundary | `ImportFirewall.check("os.system")` | Returns False (blocked) | Dangerous imports blocked |

### AC-53: Self-model tool registry (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-53.1 | behavioral | `SelfToolRegistry.dispatch(tool_name, kwargs)` | Returns tool result string | Tool dispatch works |
| AC-53.2 | behavioral | `dispatch("update_facet", ...)` with valid args | Facet updated in SelfRepo | Facet update via tool |
| AC-53.3 | boundary | `dispatch("unknown_tool", ...)` | Returns error string | Unknown tool safe |
| AC-53.4 | behavioral | `dispatch("create_todo", ...)` | Todo created with motivated_by | Todo creation via tool |
| AC-53.5 | behavioral | Write precondition check | Blocked if precondition fails | Precondition enforcement |
| AC-53.6 | behavioral | Operator review required for destructive operations | Review gate consulted | Operator review gate |

### AC-54: Operator review (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-54.1 | behavioral | `OperatorReviewGate.approve(operation)` | Operation allowed | Approval flow |
| AC-54.2 | behavioral | `OperatorReviewGate.deny(operation)` | Operation blocked | Denial flow |
| AC-54.3 | behavioral | `OperatorReviewGate.pending(operation)` | Operation queued | Pending state |

### AC-55: Detectors — learning, affirmation, prospection (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-55.1 | behavioral | `LearningDetector.scan(memory)` with novel pattern | Returns learning event | Learning detected |
| AC-55.2 | behavioral | `LearningDetector.scan(memory)` with known pattern | Returns None | No duplicate learning |
| AC-55.3 | behavioral | `AffirmationDetector.check(content)` with affirmation pattern | Returns affirmation | Affirmation detected |
| AC-55.4 | behavioral | `ProspectionDetector.check(content)` with future-oriented content | Returns prospection event | Prospection detected |

### AC-56: Conduit + outbound (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-56.1 | behavioral | `SelfConduit.send(message)` in `outbound` mode | Message delivered to outbound handler | Message delivery |
| AC-56.2 | behavioral | `SelfConduit.send(message)` in `internal` mode | Message processed internally | Internal routing |
| AC-56.3 | boundary | `ConduitMode` enum | Has `internal`, `outbound`, `review` values | Mode values |
| AC-56.4 | behavioral | `Outbound.send(message)` | Message dispatched to configured channel | Outbound dispatch |

### AC-57: Near-dup + compaction + forensics (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-57.1 | behavioral | `near_dup.is_similar("hello world", "hello world!")` | Returns True (similar) | Similarity detection |
| AC-57.2 | behavioral | `near_dup.is_similar("cats", "quantum physics")` | Returns False (different) | Dissimilar detection |
| AC-57.3 | behavioral | `compaction.run(self_repo)` | Redundant nodes compacted | Compaction works |
| AC-57.4 | behavioral | `forensics.inspect(self_repo, node_id)` | Returns forensic report | Forensic inspection |

### AC-58: Cross-user isolation (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-58.1 | behavioral | Write with `self_id=A` and `acting_self_id=B` | `CrossSelfAccess` raised | Cross-user write blocked |
| AC-58.2 | behavioral | Read with `self_id=A` | Only sees A's data | Read isolation |

### AC-59: Retrieval materialize (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-59.1 | behavioral | `materialize(retrieval_results)` | Returns list of materialized dicts | Materialization works |
| AC-59.2 | behavioral | Materialize with embedding data | Embedding vector included | Embedding preserved |

### AC-60: Activation GC + personality drift + session mood + mood decisions (behavioral)

| AC | Contract | Pre | Post | Invariant |
|----|----------|-----|------|-----------|
| AC-60.1 | behavioral | `gc.run(self_repo)` | Expired contributors retracted | GC retracts expired |
| AC-60.2 | behavioral | `PersonalityDrift.check(self_repo)` | Returns drift report or None | Drift detection |
| AC-60.3 | behavioral | `SessionMood.get(session_id)` | Returns per-session mood | Session mood tracking |
| AC-60.4 | behavioral | `SessionMood.update(session_id, event)` | Mood updated for session | Session mood update |
| AC-60.5 | behavioral | `mood_decision.should_act(mood)` | Returns True/False based on mood state | Mood-gated decisions |

## 4. Unit Test Plan

| Test file | ACs covered | Marks |
|-----------|-------------|-------|
| `tests/test_self_interactive_bootstrap.py` | AC-51.1..51.4 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_signing.py` | AC-52.1..52.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_import_firewall.py` | AC-52.3..52.4 | `contract("boundary")` `scope("unit")` |
| `tests/test_self_tool_registry.py` | AC-53.1..53.6 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_tool_registry_bdd.py` | AC-53 (BDD) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_operator_review.py` | AC-54.1..54.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_learning_detector.py` | AC-55.1..55.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_affirmation_detector.py` | AC-55.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_prospection_detector.py` | AC-55.4 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_conduit.py` | AC-56.1..56.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_conduit_mode.py` | AC-56.3 | `contract("boundary")` `scope("unit")` |
| `tests/test_self_outbound.py` | AC-56.4 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_near_dup.py` | AC-57.1..57.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_compaction.py` | AC-57.3 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_forensics.py` | AC-57.4 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_cross_user.py` | AC-58.1..58.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_retrieval_materialize.py` | AC-59.1..59.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_activation_gc.py` | AC-60.1 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_personality_drift.py` | AC-60.2 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_session_mood.py` | AC-60.3..60.4 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_mood_decisions.py` | AC-60.5 | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_write_preconditions.py` | AC-53 (preconditions) | `contract("behavioral")` `scope("unit")` |
| `tests/test_self_write_preconditions_bdd.py` | AC-53 (BDD) | `contract("behavioral")` `scope("unit")` |
| `tests/test_conduit_runtime_bdd.py` | AC-56 (BDD) | `contract("cross-service")` `scope("integration")` |
| `tests/test_memory_mirroring.py` | Memory bridge | `contract("cross-service")` `scope("integration")` |
| `tests/test_memory_mirroring_bdd.py` | Memory bridge (BDD) | `contract("cross-service")` `scope("integration")` |
| `tests/test_warden_self_writes_bdd.py` | Warden + security | `contract("cross-service")` `scope("integration")` |

## 5. Property Tests (Hypothesis)

### P-52.1: Signing is collision-resistant (basic)

```python
from maistro_turing.self_model.signing import sign, verify

@given(data=st.binary(min_size=1, max_size=1000))
@settings(max_examples=100)
def test_sign_verify_round_trip(data):
    signature = sign(data)
    assert verify(signature, data) is True

@given(
    data=st.binary(min_size=1, max_size=1000),
    tampered=st.binary(min_size=1, max_size=1000),
)
@settings(max_examples=100)
def test_tampered_data_rejected(data, tampered):
    from hashlib import sha256
    if sha256(data).digest() == sha256(tampered).digest():
        return  # skip identical
    signature = sign(data)
    assert verify(signature, tampered) is False
```

### P-57.1: Near-dup is reflexive and symmetric

```python
from maistro_turing.self_model.near_dup import is_similar

@given(text=st.text(min_size=1, max_size=200))
@settings(max_examples=100)
def test_near_dup_reflexive(text):
    assert is_similar(text, text) is True

@given(
    a=st.text(min_size=10, max_size=100),
    b=st.text(min_size=10, max_size=100),
)
@settings(max_examples=100)
def test_near_dup_symmetric(a, b):
    assert is_similar(a, b) == is_similar(b, a)
```

## 6. Integration Test Plan

| Test | What it wires | AC | Marks |
|-------|--------------|-----|-------|
| `test_tool_registry_with_self_repo` | ToolRegistry → SelfRepo facet update → verify via SelfRepo | AC-53 + AC-10 | `contract("cross-service")` `scope("integration")` |
| `test_conduit_to_outbound` | Conduit → outbound mode → message dispatched | AC-56 | `contract("cross-service")` `scope("integration")` |
| `test_detectors_to_write_paths` | Learning detector → memory write → affirmation detector | AC-55 + memory | `contract("cross-service")` `scope("integration")` |
| `test_gc_after_retrieval` | Retrieval → contributor created → GC → expired retracted | AC-60.1 + AC-59 | `contract("cross-service")` `scope("integration")` |
| `test_warden_blocks_dangerous_self_write` | Warden gate → import firewall → dangerous write blocked | AC-52 + AC-58 | `contract("cross-service")` `scope("integration")` |

## 7. Bridge Adapter Specs

No new bridges. Phase 8 modules are internal self-model machinery that uses
SelfRepo and Repo directly (already bridged in Phase 3).

## 8. Phase Gate

- [ ] All AC-51..60 tests pass
- [ ] `ruff check packages/maistro-turing/` clean
- [ ] `mypy packages/maistro-turing/ --strict` clean
- [ ] Test count >= 80
- [ ] No `stronghold` imports
- [ ] Tool registry dispatches all registered self-model tools
- [ ] Cross-user isolation enforced on all write paths
- [ ] Signing/verification round-trips on self-model data
