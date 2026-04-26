# ADR-XXX: Title

**Status:** Proposed | Accepted | Implemented | Superseded  
**Date:** YYYY-MM-DD  
**Tranche:** TX  
**Depends on:** ADR-YYY, ADR-ZZZ

---

## Context

Why this port, what gap it fills, what currently exists in maistro-engine that relates.

## Decision

What we are porting, from which source repo/path, and what we are explicitly **not** porting.

## Interface (spec)

Public types, classes, functions, FastAPI routes (if any), error semantics.

```python
# Example type signatures
```

## Acceptance criteria

- [ ] Happy path: ...
- [ ] Edge case: ...
- [ ] Observable signal (metric / log / trace): ...

## Test plan

| Test | Type | Covers |
|---|---|---|
| `test_foo_happy` | unit | happy path description |
| `test_foo_edge_X` | unit | edge case description |

## Dependencies

- ADR-YYY must be merged first because ...

## Out of scope

List of things the source module has that we deliberately leave behind.

## Source references

- `/vmpool/github/stronghold/src/stronghold/...` — description
- `/vmpool/github/Project_mAIstro/conductor/...` — description

## Links

- PR: #
- Issue: #
- Follow-up ADRs: ADR-XXX
