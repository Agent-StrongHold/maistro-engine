# SPEC-081226-a66b: Run, NodeRun and Attempt Lifecycle

- **Status:** Active
- **Date:** 2026-08-12
- **ADR:** `ADR-081226-a66b`

## Required model

```text
Run
└── NodeRun[]
    └── Attempt[]
```

### Required Run fields

At minimum:

```text
run_id
workspace_id
status
created_at
updated_at
parent_run_id?
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

Run status MUST be one of:

`created`, `queued`, `running`, `waiting`, `paused`, `completed`, `failed`, `cancelled`, `timed_out`.

### R2. Transition validation

Canonical services MUST reject illegal transitions. Terminal Run states MUST NOT transition back to non-terminal states.

### R3. Retry identity

Retrying a NodeRun MUST create a new Attempt while preserving `run_id` and `node_run_id`.

### R4. Resume identity

Resuming a paused/waiting NodeRun from a Checkpoint MUST create a new Attempt under the same NodeRun unless the NodeRun had already reached a terminal logical state.

### R5. Physical exclusivity

A NodeRun MUST NOT have more than one active physical Attempt unless a NodeType explicitly defines parallel physical attempts as domain behavior and the lifecycle model records that behavior unambiguously. Ordinary retry/resume is sequential.

### R6. Cancellation persistence

When runtime cancellation completes, the Attempt MUST be persisted terminal before or as part of reconciliation of NodeRun/Run state.

A successful cancellation path MUST NOT leave the latest Attempt terminal while the owning logical records remain indefinitely `running`.

### R7. Recovery reconciliation

On startup/recovery, a non-terminal Run/NodeRun whose latest Attempt is terminal or stale and has no valid active worker MUST be reconciled according to recovery policy rather than assumed active.

### R8. Waiting/paused semantics

A waiting/paused Run or NodeRun MUST be persistable without a live execution coroutine/process.

### R9. Child Runs

Child Runs MUST store `parent_run_id`. Parent/child cancellation and failure propagation MUST be driven by explicit policy/graph semantics.

### R10. Queue separation

A WorkRequest/queue item MAY exist before a Run. Once accepted/admitted, externally authoritative workload lifecycle MUST transition to the canonical Run rather than remain solely in TaskStatus.

### R11. Scheduler separation

A schedule trigger MUST create/resume a Run. Scheduler records MAY reference the Run but MUST NOT own a competing post-admission lifecycle.

### R12. Durable compatibility

Existing DurableRunRecord/DurableNodeRecord persistence MAY remain during migration but MUST become adapters/storage projections of canonical Run/NodeRun semantics rather than separate authoritative definitions.

## Acceptance Criteria

1. **Legal transitions:** unit tests cover every allowed Run transition and reject representative illegal/terminal transitions.
2. **Retry:** a failed Attempt retried by policy produces Attempt ordinal +1 with the same Run/NodeRun IDs.
3. **Crash resume:** a resumable stale NodeRun creates a new Attempt referencing the checkpoint, not a new Run.
4. **Cancellation:** cancelling active work ends with Attempt `cancelled` and reconciled NodeRun/Run state; no durable `running` residue remains after recovery.
5. **Wait/resume:** a HITL-like wait survives process restart with no live worker, then resumes through a new Attempt.
6. **Timeout:** runtime deadline expiry records a timed-out Attempt and reconciles logical status according to policy.
7. **Child Run:** delegation creates a child Run with parent correlation and independent lifecycle.
8. **Queue admission:** accepting a WorkRequest produces a Run and queue/task status becomes a projection/reference.
9. **Schedule path:** schedule -> Run uses the same lifecycle service as manual execution.
10. **Durable graph parity:** GraphRun/durable adapters preserve conditional traversal, fanout/fanin, retries and pause/resume while using canonical IDs.
11. **Restart:** persisted Run/NodeRun/Attempt history reloads with identical logical/physical relationships.
12. **No competing lifecycle:** new execution entry paths cannot complete work without a canonical Run once their migration flag/adapter is enabled.

## Migration order

1. Implement canonical lifecycle models/state validation.
2. Fix cancellation terminalization/reconciliation.
3. Route ExecutionRuntime Attempt mechanics through lifecycle service.
4. Adapt graph/durable persistence.
5. Adapt TaskRunner/queue admission.
6. Adapt scheduler.
7. Adapt delegation/HITL/harness.
8. Adapt Builders/RSI/Evolve.
9. Remove duplicate lifecycle authorities after parity tests.

## Non-goals

This SPEC does not define graph traversal, provider selection, permission evaluation, event payload schemas or retry eligibility algorithms.
