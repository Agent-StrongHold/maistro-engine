---
id: SPEC-080126-9e42
title: "Periodic memory-decay driver — making 'memory must forget' true at runtime"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-08-01
substrate:
  - maistro-engine#ADR-046
  - maistro-engine#ADR-080
implements:
  - maistro-engine#ADR-080
related:
  - maistro-engine#SPEC-240
  - maistro-engine#SPEC-241
  - maistro-engine#ADR-037
supersedes: []
blocks: []
blocked-by:
  - maistro-engine#SPEC-080126-3a7c
contracts:
  - behavioral
tests:
  - packages/maistro-core/tests/memory/episodic/test_tiers.py
layer: Memory
owners:
  - '@BlakeMatthews-dev'
history:
  - status: Proposed
    date: 2026-08-01
---

# SPEC-080126-9e42: Periodic memory-decay driver

## Context

`README.md:95` tells users the memory subsystem *"decays without reinforcement."*
`CLAUDE.md:180` lists **"Memory must forget"** as key design decision #5.

Neither is true at runtime. `packages/maistro-core/src/maistro/memory/episodic/tiers.py`
defines `decay()` (`:44`) and `tick_decay()` (`:84`), both correct and tested — and **neither
has a single production caller**. Only the test suite invokes them. In a running system,
memory never decays. See **#344**.

[SPEC-240](SPEC-240-memory-decay-reinforcement.md) is not at fault and its `Implemented`
status is correct: it explicitly declared the periodic caller a Non-goal (`:65-66`), shipping
the pure functions it promised and deferring the driver *"once a scheduler subsystem exists
(ADR-046)."* The follow-up simply never happened, and no artifact tracked it — which is how a
documented product behavior came to silently not exist.

## Problem

The decay primitives are inert. Consequences:

- The README makes a claim the product does not deliver — a truth-in-advertising defect
  (workstream D), not merely a missing feature.
- Episodic memory grows without bound in weight terms; nothing reclaims salience from stale
  entries, so retrieval ranking drifts toward whatever was written most, forever.
- The weight floors for wisdom/regrets that decision #5 promises are never exercised, so
  their behavior under real decay is unverified in production conditions.

## Goals

- `tick_decay` runs on a cadence in a deployed system.
- The cadence is configurable and can be disabled.
- Decay activity is observable — an operator can answer "did decay run, and what did it
  touch?"

## Non-goals

- Tuning decay-rate/boost/drop constants. ADR-080 puts curve constants out of scope and
  SPEC-240 defers tuning to a follow-up; this SPEC drives the existing curve, it does not
  reshape it.
- Decay for learnings/outcome stores. Episodic only, matching SPEC-240's scope.
- Backfilling decay for the period during which it never ran (see below).

## Decision

### Blocked on the scheduler, deliberately

This depends on [SPEC-080126-3a7c](SPEC-080126-3a7c-durable-scheduler.md), and the
`blocked-by` is real rather than bookkeeping. Driving decay from the *current* scheduler
would inherit its in-memory store (#343): the decay schedule itself would vanish on restart,
so the fix would silently stop working at the first deploy — reproducing the exact failure
mode this SPEC exists to end. **Do not implement this on top of the shipped scheduler.**

### The first run is the dangerous one

Decay has never run. On a system with existing memories, the first tick applies accumulated
decay to entries whose `last_reinforced` timestamps may be months old. Depending on the
curve, that could collapse a large fraction of episodic salience in a single pass.

This must be handled explicitly, not discovered in production. The implementer must
determine, with real data shapes, whether the first tick is safe, and if not, specify the
mitigation — a clamp on per-tick decay magnitude, a staged rollout, or a one-time
`last_reinforced` rebase. **A migration that silently guts a user's memory on upgrade is
strictly worse than the current gap**, which merely does nothing.

### Loud when disabled

Following the F3 precedent (#302): if decay is configured off, that is a degraded mode and
must be visible, not a silent no-op that looks identical to today's bug.

## Acceptance criteria

- [ ] With the driver enabled, `tick_decay` demonstrably runs on its cadence against a real
      store, and affected entries' weights change.
- [ ] Weight floors for wisdom/regrets hold across repeated ticks — an entry at the floor
      does not decay below it no matter how many cycles run.
- [ ] Reinforcement between ticks measurably offsets decay (the "without reinforcement"
      qualifier in the README is load-bearing and must be true).
- [ ] The cadence is configurable and can be disabled; disabling is surfaced as degraded,
      not silent.
- [ ] First-run behavior on a store with stale timestamps is characterized and safe, with
      the reasoning recorded here.
- [ ] Decay activity is observable — at minimum a count of entries touched per tick.
- [ ] `README.md:95` and `CLAUDE.md:180` are true once this ships. **If this SPEC does not
      ship for v1, those lines must be corrected instead** and a `KNOWN-GAPS.md` entry added
      — the claim cannot stand unbacked either way.

## Testing

- Unit: floors hold across N ticks; reinforcement offsets decay; disabled driver performs no
  mutation.
- Integration: driver scheduled → tick fires → store reflects decayed weights. Must exercise
  the real scheduling path, not call `tick_decay` directly — calling it directly is what the
  existing tests already do, and it is exactly the coverage that let this gap survive.
- Migration/first-run: fixture store with months-old `last_reinforced` values → first tick →
  assert the outcome matches whatever mitigation was chosen.

## References

- #344 — the gap this SPEC closes
- #343 — the scheduler drift that kept it invisible
- [SPEC-240](SPEC-240-memory-decay-reinforcement.md) — ships the primitives; this drives them
- [SPEC-080126-3a7c](SPEC-080126-3a7c-durable-scheduler.md) — the blocking dependency
