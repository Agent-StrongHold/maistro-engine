# ADR-003: Resolution of OpenClaw gap analysis branch

**Status:** Accepted  
**Date:** 2026-04-26  
**Tranche:** T0  
**Depends on:** ADR-001

---

## Context

An orphaned branch `origin/claude/compare-bot-frameworks-tFPdY` contained a single commit (`76954c1`, 2026-03-17) adding `docs/analysis/openclaw-comparison.md` — a 148-line gap analysis comparing maistro-engine against OpenClaw's five core primitives. It was never merged and had no PR open.

The document identifies five gaps in maistro-engine relative to a full agent runtime:

| # | Primitive | Status at time of analysis |
|---|---|---|
| 1 | **Soul** (identity/personality) | MISSING — static system prompt only |
| 2 | **Memory** | Schema defined (`MemoryEntry`, `KnowledgeNode`), not wired |
| 3 | **Context** (workspace awareness) | MINIMAL — description + constraints only |
| 4 | **Heartbeat** (proactive autonomy) | EMPTY MODULE — `scheduler/` had no code |
| 5 | **Taskmaster** (skill composability) | HARDCODED — no runtime skill discovery |

## Decision

1. Carry `docs/analysis/openclaw-comparison.md` forward into `integration` as a permanent reference document. Do not delete.
2. Delete the orphaned branch once this ADR is committed to `integration`. Its only content (the gap analysis doc) is now canonical on `integration`.
3. Treat the five gaps as the north-star for the porting backlog: each gap is closed by a specific tranche.

**Gap-to-tranche mapping:**
- Gap 1 (Soul) → T8 (`ADR-055` through `ADR-058`)
- Gap 2 (Memory) → T2 (`ADR-011` through `ADR-018`)
- Gap 3 (Context) → T7 (`ADR-049` through `ADR-054`)
- Gap 4 (Heartbeat) → T6 (`ADR-043` through `ADR-048`)
- Gap 5 (Taskmaster/skills) → T5 (`ADR-036` through `ADR-042`)

## Acceptance criteria

- [x] `docs/analysis/openclaw-comparison.md` present on `integration`
- [ ] Orphaned branch `origin/claude/compare-bot-frameworks-tFPdY` deleted after this commit merges (manual step — requires `git push origin --delete claude/compare-bot-frameworks-tFPdY`)

## Out of scope

The document's Phase 3 channel integration recommendations (Slack/Discord). iMessage from approved sources only is the chosen channel; defer to T15+.

## Source references

- `origin/claude/compare-bot-frameworks-tFPdY:docs/analysis/openclaw-comparison.md` (now at `docs/analysis/openclaw-comparison.md`)
