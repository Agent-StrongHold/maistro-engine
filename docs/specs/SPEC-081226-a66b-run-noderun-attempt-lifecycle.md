---
id: SPEC-081226-a66b
title: Run, NodeRun and Attempt Lifecycle
repo: maistro-engine
kind: spec
status: AC Defined
created: 2026-08-12
history:
  - status: Proposed
    date: 2026-08-12
  - status: Accepted
    date: 2026-08-12
  - status: AC Defined
    date: 2026-08-12
substrate:
  - maistro-engine#ADR-081226-a66b
implements:
  - maistro-engine#ADR-081226-a66b
related:
  - maistro-engine#ADR-081426-b1d3
  - maistro-engine#ADR-081226-69ee
  - maistro-engine#ADR-081426-1f7c
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
source:
  - packages/maistro-core/src/maistro/runs
  - packages/maistro-core/src/maistro/runtime
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-a66b: Run, NodeRun and Attempt Lifecycle

- **Status:** Active
- **Date:** 2026-08-14 revision
- **ADR:** `ADR-081226-a66b`

## Required model

```text
Run(workspace_id, project_id)
└── NodeRun[]
    └── Attempt[]
        └── ExecutionRuntime(execution_id = attempt_id)
```

### Required Run fields

At minimum:

```text
run_id
workspace_id
project_id
status
created_at
updated_at
parent_run_id?
parent_node_run_id?
executable_snapshot/reference
provenance
result/error?
```

### Required NodeRun fields

At minimum:

```text
node_run_id
run_id
node_id/snapshot identity
status
ordinal
created_at
updated_at
result/error?
```

### Required Attempt fields

At minimum:

```text
attempt_id
node_run_id
ordinal
status/outcome
runtime/executor identity
created_at
started_at?
finished_at?
deadline?
resume_checkpoint_id?
result/error?
runtime metrics?
```

## Requirements

### R1. Canonical Run states

Run status MUST be one of `created`, `queued`, `running`, `waiting`, `paused`, `completed`, `failed`, `cancelled`, `timed_out`.

### R2. Scope identity

Run creation MUST copy `workspace_id` and `project_id` from the captured Graph snapshot. Both remain immutable scope identity for that Run. A Run and its Graph snapshot MUST agree on both values.

### R3. Transition validation

Canonical services MUST reject illegal transitions. Terminal Run states MUST NOT transition back to non-terminal states.

### R4. Retry identity

Retrying a NodeRun MUST create a new Attempt while preserving `run_id` and `node_run_id`.

### R5. Resume identity

Resuming a paused/waiting NodeRun from a Checkpoint MUST create a new Attempt under the same NodeRun unless the NodeRun already reached a terminal logical state.

### R6. Physical exclusivity

A NodeRun MUST NOT have more than one active ordinary physical Attempt at a time. Any NodeType that intentionally models parallel speculative Attempts requires an explicit future contract; ordinary retry/resume is sequential.

### R7. Runtime identity

Canonical execution MUST call ExecutionRuntime with `execution_id = Attempt.attempt_id`, never the logical `run_id`.

### R8. Runtime deadline classification

Runtime-owned deadline expiry MUST terminalize the Attempt as `timed_out`. An executor independently raising `TimeoutError` MUST NOT be classified as Runtime deadline expiry merely because its exception type is `TimeoutError`.

### R9. Cancellation persistence

When Runtime cancellation completes, Attempt MUST be persisted terminal before or as part of NodeRun/Run reconciliation. A successful cancellation path MUST NOT leave durable logical records indefinitely `running` with no physical worker.

### R10. Recovery reconciliation

On startup/recovery, a non-terminal Run/NodeRun whose latest Attempt is terminal or stale and has no valid active worker MUST be reconciled according to recovery policy rather than assumed active.

### R11. Waiting/paused semantics

A waiting/paused Run or NodeRun MUST be persistable without a live execution coroutine/process.

### R12. Child Runs

Child Runs MUST store `parent_run_id`; when created for a Node delegation/subgraph they SHOULD also store `parent_node_run_id`.

A child Run defaults to its parent's Project. Explicit cross-Project child creation MAY target another Project only inside the same Workspace and only after authorization approves the destination. Cross-Workspace child creation MUST be rejected.

### R13. Queue separation

A WorkRequest/queue item MAY exist before a Run. Once accepted/admitted, externally authoritative workload lifecycle MUST transition to canonical Run rather than remain solely in TaskStatus.

### R14. Scheduler separation

A Schedule trigger MUST create/resume a Run. Scheduler records MAY reference Run but MUST NOT own a competing post-admission lifecycle.

### R15. Durable convergence

Existing durable Run/Node records MAY remain during migration but MUST become persistence projections/adapters of canonical Run/NodeRun semantics rather than separate authoritative definitions.

### R16. Canonical execution service boundary

Domain and product callers SHOULD enter universal execution through a canonical Run service that creates Run/NodeRun identity and routes physical work through Attempt -> ExecutionRuntime. That service MUST NOT own graph traversal, authorization, Provider selection, retry eligibility, scheduling, or Run-completion policy. Retrying physical work MUST be an explicit operation on the existing NodeRun rather than implicit creation of another logical NodeRun.

## Acceptance Criteria

1. Unit tests cover every allowed Run transition and representative illegal/terminal transitions.
2. Run creation rejects a Graph snapshot whose Workspace or Project differs from declared Run scope.
3. A failed Attempt retried by policy produces Attempt ordinal +1 with the same Run/NodeRun IDs.
4. A resumable stale NodeRun creates a new Attempt referencing its Checkpoint, not a new Run.
5. Runtime is invoked with `attempt_id`; two Attempts under one Run can execute concurrently without execution-ID collision.
6. Runtime deadline expiry records a timed-out Attempt and reconciles logical state according to policy.
7. Executor-raised `TimeoutError` records a failed Attempt unless domain policy explicitly reclassifies it.
8. Cancelling active work ends with Attempt `cancelled` and reconciled NodeRun/Run state; recovery sees no durable phantom `running` worker.
9. A HITL-like wait survives process restart with no live worker and resumes through a new Attempt.
10. A child Run inherits the parent Project by default.
11. Explicit same-Workspace cross-Project child Run creation records the destination `project_id` and passes through destination authorization.
12. Cross-Workspace child Run creation fails.
13. Accepting a WorkRequest produces a Run and task/queue status becomes a projection/reference.
14. Schedule -> Run uses the same lifecycle service as manual execution.
15. GraphRun/durable adapters preserve conditional traversal, fanout/fanin, retries, and pause/resume while using canonical IDs.
16. Persisted Run/NodeRun/Attempt history reloads with identical logical/physical relationships.
17. Migrated execution entry paths cannot complete workload without a canonical Run.
18. The canonical execution service can execute `Graph -> Run -> NodeRun -> Attempt -> ExecutionRuntime` for one Node without importing graph traversal, authorization, Binding/Provider selection, or product-specific lifecycle code.

## Migration order

1. Project-scope identity on Graph/Run.
2. Attempt -> ExecutionRuntime service and terminal reconciliation.
3. Canonical Event + Checkpoint.
4. Graph/durable persistence convergence.
5. Queue/scheduler/delegation/HITL/harness convergence.
6. Builders/RSI/Evolve and remaining product entry paths.
7. Delete competing lifecycle authorities after parity tests.

## Non-goals

This SPEC does not define graph traversal, Project authorization algorithms, Provider selection, Event payload schemas, or retry eligibility policy.
