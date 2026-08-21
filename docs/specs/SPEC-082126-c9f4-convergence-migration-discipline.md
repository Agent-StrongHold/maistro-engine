---
id: SPEC-082126-c9f4
title: Convergence Migration Discipline
repo: maistro-engine
kind: spec
status: AC Defined
created: 2026-08-21
history:
  - status: Proposed
    date: 2026-08-21
  - status: Accepted
    date: 2026-08-21
  - status: AC Defined
    date: 2026-08-21
substrate:
  - maistro-engine#ADR-082126-c9f4
implements:
  - maistro-engine#ADR-082126-c9f4
related:
  - maistro-engine#SPEC-081226-9944
  - maistro-engine#SPEC-081226-034b
  - maistro-engine#SPEC-081226-a66b
  - maistro-engine#SPEC-081426-1f7c
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - behavioral
tests: []
source:
  - BACKLOG.md
  - docs/CONVERGENCE-PLAN.md
  - scripts/check-ac-state.py
  - scripts/check-reachability.py
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-082126-c9f4: Convergence Migration Discipline

## Purpose

Make migration order and architectural convergence reviewable as explicit acceptance criteria instead of relying on backlog prose or reviewer memory.

This spec does not replace the domain criteria in the Workspace, Run, Runtime, Capability, Event, Permission, Persona, Project, or Template specs. It constrains how those decisions are migrated into ordinary production use.

## Requirements

### R1. Convergence priority

Until full convergence is achieved, unrelated product, frontier, and optional-extension work MUST NOT displace the next dependency-valid convergence slice.

Safety, CI, or correctness repairs required to land a convergence slice remain part of that convergence work.

### R2. Replacement-before-connection trigger

A queue-jump MUST identify:

- the predecessor surface that the next convergence step would otherwise wire;
- the replacement target;
- the Accepted ADR/spec or explicitly approved convergence-plan decision establishing that target;
- why wiring the predecessor would create disposable work; and
- the minimum replacement seam required before convergence can continue.

If any of those are absent, the replacement MUST remain in its normal post-convergence/product/frontier order.

### R3. Immediate return to convergence

A replacement queue-jump MUST end when the minimum seam required by the blocked convergence step is available. Additional replacement UI, polish, migration, or product scope MUST NOT remain ahead of convergence merely because the replacement has started.

### R4. No duplicate universal owner

Migration MUST NOT introduce a second universal owner for any of these concerns:

- logical execution lifecycle;
- physical execution lifecycle;
- authorization/permission resolution;
- capability fulfillment/invocation;
- durable event sequencing/correlation;
- recovery/checkpoint authority;
- approval lifecycle;
- Workspace/Project durable ownership; or
- general memory/knowledge identity where a canonical owner already exists.

Domain state MAY remain specialized when it does not compete for universal ownership.

### R5. Canonical migration sequence

A legacy architectural owner MUST migrate through these evidence-bearing stages:

```text
canonical owner exists
→ preserved behavior has parity tests
→ real callers move
→ canonical path is reachable
→ obsolete owner is removed or reduced to a projection/delegating adapter
```

Deletion MAY occur earlier only for behavior explicitly determined to be obsolete and documented as such.

### R6. Adapter constraint

A temporary compatibility adapter MUST project into or delegate to the canonical owner. It MUST NOT maintain a second independent durable truth or mint competing lifecycle identities.

### R7. Completion evidence

A convergence item MUST NOT be marked complete solely because a class/module exists or isolated tests pass.

If the criterion describes product/runtime behavior, the canonical module/path MUST be reachable from a real entry point and the relevant acceptance criterion MUST reach the `reachable` evidence rung before completion is claimed.

### R8. Predecessor deletion safety

Removing a predecessor MUST require both:

1. parity evidence for behavior intentionally retained; and
2. reachable canonical replacement evidence for the migrated product path.

Known intentional behavior loss MUST be named explicitly rather than hidden as migration fallout.

### R9. Optional extension boundary

Turing, continual improvement, collective learning, RSI, Evolve, and other optional/frontier programs MAY depend on the canonical spine and MAY motivate extension points. They MUST NOT become replacement owners for core MAIstro features merely because they add autonomous or specialized behavior.

### R10. Architecture plan consistency

`docs/CONVERGENCE-PLAN.md` MUST identify ADR-082126-c9f4 as the governing migration-order decision. `BACKLOG.md` MAY restate the operational queue, but neither document may assert a sequencing or queue-jump rule that contradicts this ADR.

### R11. Pull-request evidence

A PR that changes a canonical ownership/migration boundary MUST state one of:

- it is ordinary convergence and names the owning ADR/spec; or
- it is a replacement-before-connection queue-jump and names the predecessor, replacement, trigger, minimum seam, and convergence step that resumes afterward.

This declaration is review evidence, not a substitute for tests.

## Acceptance Criteria

```gherkin
Feature: Convergence migration discipline

  @AC-1
  Scenario: The next ordinary slice remains convergence work
    Given full convergence has not been achieved
    And a dependency-valid convergence slice is ready
    When unrelated product or frontier work is proposed ahead of it
    Then the convergence slice retains priority

  @AC-2
  Scenario: A replacement may jump only at an imminent disposable connection
    Given the next convergence slice would wire predecessor P
    And an approved target R replaces P
    When wiring P would create a runtime dependency removed by R
    Then only the minimum R seam required by that convergence slice may run first

  @AC-3
  Scenario: A future replacement alone cannot jump the queue
    Given a desirable future replacement exists
    But the next convergence slice does not need its predecessor
    When priority is evaluated
    Then the replacement does not preempt convergence

  @AC-4
  Scenario: Convergence resumes after the replacement seam
    Given a replacement-before-connection seam has landed
    And the blocked convergence slice can now use it
    When the next work item is selected
    Then that convergence slice is selected before additional replacement scope

  @AC-5
  Scenario: A second universal lifecycle is rejected
    Given architecture fitness enforcement
    When a migration introduces a competing universal Run, Attempt, event-sequence, authorization, approval, or fulfillment owner
    Then the architecture check reports a violation

  @AC-6
  Scenario: A compatibility adapter cannot become an independent authority
    Given a temporary adapter for a replaced subsystem
    When it persists or mints lifecycle truth independently of the canonical owner
    Then the architecture check reports a violation

  @AC-7
  Scenario: Isolated passing code is not convergence completion
    Given a convergence criterion whose implementation tests pass
    But no real product entry point reaches its canonical path
    When completion evidence is evaluated
    Then the criterion is not considered complete

  @AC-8
  Scenario: A predecessor is deleted only after safe migration
    Given behavior from a legacy architectural owner is intentionally retained
    When deletion of that owner is proposed
    Then parity evidence exists for the retained behavior
    And the canonical replacement is reachable from the migrated product path

  @AC-9
  Scenario: Optional Turing behavior remains an extension
    Given an optional Turing capability
    When it participates in execution or improvement
    Then it uses canonical MAIstro Run and Binding boundaries
    And disabling Turing does not remove the corresponding core MAIstro feature

  @AC-10
  Scenario: Execution plans cannot override the architecture decision
    Given BACKLOG.md and docs/CONVERGENCE-PLAN.md
    When migration ordering is read from either plan
    Then docs/CONVERGENCE-PLAN.md identifies ADR-082126-c9f4 as governing
    And BACKLOG.md states no conflicting queue-jump rule
    And docs/CONVERGENCE-PLAN.md states no conflicting queue-jump rule

  @AC-11
  Scenario: A migration PR explains its architectural disposition
    Given a PR changing a canonical ownership boundary
    When its review evidence is inspected
    Then it names the owning ADR/spec
    And if it jumps the queue it names the predecessor, replacement, trigger, minimum seam, and convergence step that resumes
```

## Planned enforcement

The criteria are intentionally split between process evidence and machine fitness rules.

Near-term enforcement belongs in the existing convergence work rather than a new parallel governance subsystem:

1. extend architecture-fitness CI for AC-5 and AC-6;
2. use the acceptance-state/reachability gate for AC-7 and AC-8;
3. keep plan consistency covered by documentation/registry tests for AC-10;
4. add PR-template wording for AC-11 when the next governance-template change is already in scope.

No separate migration registry or second status system should be created for this spec.

## Non-goals

This spec does not prescribe branch protection configuration, database technology, product UI, exact backlog-service schema, or the internal algorithms of Turing/RSI/Evolve.
