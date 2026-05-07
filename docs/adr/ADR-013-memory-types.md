# ADR-013: Memory types — Learning, EpisodicMemory, Outcome, scopes, tiers

**Status:** Accepted  
**Date:** 2026-04-26  
**Tranche:** T2  
**Depends on:** ADR-002

---

## Context

maistro-engine has no multi-tier memory types. Stronghold defines `Learning` (self-improving correction), `EpisodicMemory` (7-tier weighted memory), `Outcome` (request outcome), plus `MemoryTier`, `MemoryScope`, and `WEIGHT_BOUNDS`.

## Decision

Port into `src/maistro/memory/types.py`. Adaptation: replace `@dataclass` with plain `@dataclass` (keeping stdlib — no Pydantic; these are internal data types, not API schemas). Remove all `stronghold.*` imports.

Port scope filter logic into `src/maistro/memory/scopes.py`.

## Interface

```python
# memory/types.py
class MemoryTier(StrEnum): OBSERVATION|HYPOTHESIS|OPINION|LESSON|REGRET|AFFIRMATION|WISDOM
class MemoryScope(StrEnum): GLOBAL|ORGANIZATION|TEAM|USER|AGENT|SESSION

WEIGHT_BOUNDS: dict[MemoryTier, tuple[float, float]]
REINFORCE_DELTA: float = 0.05
CONTRADICT_DELTA: float = 0.05

@dataclass class Learning: category, trigger_keys, learning, tool_name, source_query, org_id, team_id, agent_id, user_id, scope, hit_count, status, id
@dataclass class EpisodicMemory: memory_id, tier, content, weight, org_id, team_id, agent_id, user_id, scope, source, context, reinforcement_count, contradiction_count, created_at, last_accessed_at, deleted
@dataclass class Outcome: request_id, task_type, model_used, provider, tool_calls, success, error_type, response_time_ms, org_id, team_id, user_id, agent_id, input_tokens, output_tokens, created_at, id

# memory/scopes.py
def build_scope_filter(agent_id, user_id, team_id, org_id) -> list[tuple[str, str | None]]: ...
def matches_scope(mem: EpisodicMemory, filters) -> bool: ...  # cross-tenant leakage prevention
```

## Acceptance criteria

- [ ] `WEIGHT_BOUNDS[MemoryTier.REGRET] == (0.6, 1.0)` — structurally unforgettable
- [ ] `WEIGHT_BOUNDS[MemoryTier.WISDOM] == (0.9, 1.0)` — survives across versions
- [ ] `WEIGHT_BOUNDS[MemoryTier.OBSERVATION] == (0.1, 0.5)`
- [ ] `build_scope_filter()` always includes `(GLOBAL, None)` entry
- [ ] `matches_scope()` — TEAM scope requires BOTH team_id AND org_id match
- [ ] `matches_scope()` — GLOBAL memory with org_id skips different-org callers
- [ ] `Learning` dataclass round-trips through field access

## Test plan

| Test | Covers |
|---|---|
| `test_weight_bounds_regret` | floor ≥ 0.6 |
| `test_weight_bounds_wisdom` | floor ≥ 0.9 |
| `test_build_scope_filter_always_global` | global always present |
| `test_matches_scope_team_requires_org` | cross-tenant leakage prevention |
| `test_matches_scope_global_org_isolation` | different-org global blocked |
| `test_learning_dataclass_fields` | field defaults |

## Source references

- `/vmpool/github/stronghold/src/stronghold/types/memory.py`
- `/vmpool/github/stronghold/src/stronghold/memory/scopes.py`
- `/vmpool/github/stronghold/src/stronghold/memory/episodic/store.py` (`_matches_scope`)
