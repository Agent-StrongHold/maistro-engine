# ADR-015: Learning type + InMemoryLearningStore

**Status:** Accepted  
**Date:** 2026-04-26  
**Tranche:** T2  
**Depends on:** ADR-013, ADR-014

---

## Context

No self-improving memory. Every agent call starts from zero — no accumulated corrections from past failures, no promoted patterns to inject into prompts.

## Decision

Port `InMemoryLearningStore` into `src/maistro/memory/learnings/store.py`. Key features: dedup via trigger-key Jaccard overlap (≥50% overlap → overwrite), org-scope isolation (strict — learnings from org-A invisible to org-B), FIFO eviction cap at 10,000, auto-promotion when hit_count ≥ threshold.

## Acceptance criteria

- [ ] `store()` deduplicates: same tool + same org + ≥50% key overlap → overwrites, does not add
- [ ] `store()` does NOT dedup across different orgs
- [ ] `store()` evicts oldest when at capacity
- [ ] `find_relevant()` returns learnings with matching trigger keys, org-filtered
- [ ] `find_relevant()` excludes learnings from other orgs
- [ ] `mark_used()` increments `hit_count` for all provided IDs
- [ ] `check_auto_promotions()` changes status to "promoted" at threshold
- [ ] `get_promoted()` only returns status="promoted" entries

## Test plan

| Test | Covers |
|---|---|
| `test_store_dedup_same_org` | Jaccard ≥50% overwrites |
| `test_store_no_dedup_different_org` | cross-org isolation |
| `test_store_eviction_at_cap` | FIFO cap |
| `test_find_relevant_keyword_match` | trigger key scoring |
| `test_find_relevant_org_isolation` | org filter |
| `test_mark_used_increments` | hit_count |
| `test_auto_promotion` | threshold promotion |
| `test_get_promoted_only_promoted` | status filter |

## Source references

- `/vmpool/github/stronghold/src/stronghold/memory/learnings/store.py`
