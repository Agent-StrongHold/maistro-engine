---
id: ADR-082126-c9f4
title: Convergence Migration Discipline
repo: maistro-engine
kind: adr
status: Accepted
created: 2026-08-21
accepted: 2026-08-21
substrate:
  - maistro-engine#ADR-081226-9944
  - maistro-engine#ADR-081226-034b
  - maistro-engine#ADR-081226-a66b
  - maistro-engine#ADR-081426-1f7c
implements: []
related:
  - maistro-engine#ADR-081226-bb3a
  - maistro-engine#ADR-081226-6b46
  - maistro-engine#ADR-081226-7248
  - maistro-engine#ADR-081426-b1d3
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
layer: Governance
owners:
  - '@BlakeMatthews-dev'
history:
  - status: Proposed
    date: 2026-08-21
  - status: Accepted
    date: 2026-08-21
---

# ADR-082126-c9f4: Convergence Migration Discipline

## Context

MAIstro already has Accepted canonical ownership, execution, runtime, capability, event, permission, and template decisions. The remaining risk is no longer primarily absence of architecture. It is migration order.

A convergence program can still regress the architecture if it:

- connects a legacy surface that an already-approved replacement will immediately remove;
- builds a second universal lifecycle while migrating a product island;
- preserves compatibility owners long enough that they become de facto canonical again;
- declares work complete because isolated code exists even though no real product path reaches it; or
- allows optional frontier/product work to preempt the dependency chain needed to make the canonical spine ordinary.

The operational backlog already expresses the intended rule: convergence is highest priority, with one narrow exception when the next convergence step would otherwise wire a disposable predecessor. This ADR makes that rule architectural rather than merely editorial.

## Decision

### 1. Convergence is the default execution priority

Until the convergence definition of done is satisfied, work that moves existing product/runtime behavior onto the Accepted canonical architecture takes priority over unrelated product, frontier, or optional-extension work.

The canonical execution spine remains:

```text
Workspace / Project
    ↓
Persona
    ↓
Graph / Node
    ↓
Run
    ↓
NodeRun
    ↓
Attempt
    ↓
ExecutionRuntime
```

Canonical fulfillment remains:

```text
Capability → Provider → Binding → Invocation
```

Canonical architecture decisions are not reopened merely to avoid migration work.

### 2. Replacement-before-connection is the only queue-jump rule

A non-convergence item may move immediately ahead of a convergence step only when all of the following are true:

1. an Accepted ADR/spec or explicitly approved convergence plan identifies the replacement target;
2. the next convergence step would otherwise create a new runtime dependency on the predecessor;
3. wiring the predecessor would create disposable work or preserve an architecture that is already scheduled for removal; and
4. the queue-jump is limited to the minimum viable replacement seam required by that convergence step.

After that seam lands, execution returns immediately to the convergence queue.

A desirable future replacement, by itself, is not enough to jump the queue.

### 3. Canonical owner first

Migration MUST NOT create a new universal execution, authorization, event, capability, memory, persistence, approval, or recovery lifecycle.

When useful domain semantics exist in a legacy subsystem, migration keeps those semantics but moves universal ownership to the canonical substrate. Specialized packages may own domain state; they do not get a second platform spine.

### 4. Migration sequence

For a replaced architectural owner, the preferred sequence is:

```text
establish canonical owner
→ prove parity for behavior worth keeping
→ move real callers/product paths
→ prove canonical reachability and correlation
→ delete the obsolete owner
```

A compatibility adapter MAY exist during a migration only when it projects into or delegates to the canonical owner. It MUST NOT continue to own durable truth independently.

Permanent compatibility facades for replaced internal architecture are forbidden unless a separate Accepted ADR identifies an external stability requirement and an explicit owner for eventual removal or permanence.

### 5. Reachability is part of completion

For convergence work, implementation in an isolated module is insufficient evidence of completion.

A criterion that claims a product/runtime behavior is implemented MUST have evidence appropriate to the claim, and product-path claims MUST reach the `reachable` rung of the acceptance-state ladder before the migrated surface is treated as complete.

Deleting a predecessor requires parity evidence for behavior intentionally preserved and reachability evidence for the canonical replacement.

### 6. Optional extensions do not become migration owners

Turing remains an optional MAIstro extension. Convergence may preserve extension points required by Turing, RSI, Evolve, collective learning, continual improvement, or other frontier work, but those programs do not replace the canonical MAIstro features they extend and do not preempt convergence absent the replacement-before-connection rule above.

### 7. Plans are subordinate to Accepted architecture

`BACKLOG.md` and `docs/CONVERGENCE-PLAN.md` coordinate execution. When their ordering or wording conflicts, this ADR and the Accepted architecture corpus govern.

The coordinated backlog MAY refine the operational order without a new ADR when it does not change architecture. A change to the rules in this ADR requires an ADR change.

## Consequences

- Migration PRs are judged by whether they reduce duplicate ownership and increase canonical reachability, not by raw feature count.
- A replacement can legitimately move one step ahead of convergence, but only at the exact seam where wiring the predecessor would be throwaway work.
- Product/frontier work can preserve hooks but cannot become an excuse to keep multiple runtimes alive.
- Legacy domain behavior is preserved through parity tests and adapters while legacy universal ownership is removed.
- The architecture can be enforced incrementally through acceptance criteria and fitness tests instead of relying on reviewer memory.

## Rejected alternatives

### Wire everything first, replace later

Rejected because it spends convergence effort making obsolete surfaces more deeply depended on and increases the cost/risk of deleting them.

### Let replacements broadly preempt convergence

Rejected because almost any future feature can be described as a replacement for some current surface. The exception must be tied to an imminent convergence dependency and kept minimal.

### Preserve every old owner behind compatibility layers

Rejected because internal compatibility owners recreate the exact ambiguity convergence is intended to remove.

### Treat test-passing isolated code as done

Rejected because the repository has repeatedly contained complete, tested subsystems that no product path imports or invokes.

## Out of scope

This ADR does not decide the implementation details of Workspace persistence, the backlog repository, collective-learning storage, Turing cognition, or a specific database technology. Those remain owned by their domain ADRs/specs.

## Links

- Spec: `SPEC-082126-c9f4`
- Operational queue: `BACKLOG.md`
- Convergence plan: `docs/CONVERGENCE-PLAN.md`
