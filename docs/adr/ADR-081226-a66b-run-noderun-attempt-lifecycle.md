# ADR-081226-a66b: Run, NodeRun and Attempt Lifecycle

- **Status:** Accepted
- **Date:** 2026-08-12
- **Deciders:** MAIstro maintainers
- **Technical Area:** Execution lifecycle, persistence, recovery

## Context

MAIstro currently expresses execution lifecycle through several overlapping concepts including Task status, GraphRun, DurableRunRecord, DurableNodeRecord, A2A tasks, Builders results, schedule execution records, RSI/evolution state and app-specific DAG records. They differ in cancellation, retry, pause/resume, recovery and terminalization semantics.

The canonical hierarchy requires three distinct levels:

```text
Run
└── NodeRun[]
    └── Attempt[]
```

This separation is necessary so a logical execution can survive process loss, retries and resume without manufacturing unrelated task/run identities.

## Decision

### Run

`Run` is the single logical execution record. It owns:

- `run_id`
- `workspace_id`
- executable Graph/Node snapshot reference
- optional `parent_run_id`
- canonical status
- NodeRuns
- Events/Artifacts/Checkpoints references
- timestamps
- provenance
- terminal result/error summary

Canonical Run states are:

```text
created
queued
running
waiting
paused
completed
failed
cancelled
timed_out
```

Terminal states are `completed`, `failed`, `cancelled`, `timed_out`.

### NodeRun

`NodeRun` is one logical execution of a Node within a Run. Retries/resume do not create a new NodeRun. A graph node that is never selected by traversal does not require a NodeRun merely to represent "skipped"; graph execution state records routing decisions.

### Attempt

`Attempt` is one physical execution attempt for a NodeRun. It owns:

- `attempt_id`
- attempt/retry ordinal
- runtime/executor selection
- start/finish timestamps
- deadline/cancellation mechanics
- resource/runtime metrics
- terminal outcome/result/error
- optional resume/checkpoint source

A retry or crash-resume creates a new Attempt under the same NodeRun.

### Lifecycle transitions

Legal Run transitions are intentionally constrained:

```text
created  -> queued | cancelled
queued   -> running | cancelled | timed_out
running  -> waiting | paused | completed | failed | cancelled | timed_out
waiting  -> queued | running | paused | cancelled | timed_out
paused   -> queued | cancelled | timed_out
```

Terminal states have no normal outbound transition. Resuming terminal work requires an explicit new Run unless a compatibility migration documents different historical semantics.

NodeRun uses the same logical lifecycle vocabulary where applicable. Attempt tracks physical execution and MUST terminate before a replacement Attempt is admitted for retry/resume.

### Waiting and pause release physical execution

`waiting` and `paused` are logical persisted states. A process/coroutine is not required to remain alive while a Run/NodeRun waits.

When an Attempt reaches a durable wait/pause boundary, it records a terminal/yielded physical outcome and checkpoint as appropriate; a later resume uses a new Attempt under the same NodeRun.

### Cancellation terminalization

ExecutionRuntime performs cancellation mechanics, but the domain lifecycle service owns terminal state.

The required reconciliation path is:

```text
runtime cancellation observed
-> Attempt terminalized as cancelled
-> NodeRun reconciled
-> Run reconciled
-> terminal event emitted from persisted state
```

If all records share a transactional store, this SHOULD be committed atomically where practical. If they do not, persistence MUST be recovery-safe: a crash between steps must be detectable and reconcilable without leaving an indefinitely `running` logical record with no active Attempt.

### Retries

Retry eligibility/backoff is domain policy. ExecutionRuntime performs mechanics only.

An approved retry creates a new Attempt with a new `attempt_id` and incremented ordinal. It does not create a new Run or NodeRun.

### Parent and child Runs

Delegation/subwork is represented by child Runs through `parent_run_id` and explicit relationship metadata. Child Runs retain their own lifecycle and events.

Parent cancellation propagation and child-failure effect are policy/graph semantics, not implicit database behavior.

### Timeouts/deadlines

Runtime enforces physical deadlines on Attempts. Domain reconciliation maps those outcomes to NodeRun/Run states according to policy. A Run may have a logical deadline spanning multiple Attempts.

### Recovery

Recovery operates on persisted Run/NodeRun/Attempt/Checkpoint state. A stale non-terminal record with no valid active Attempt is a reconciliation/recovery condition, not evidence that work is still running.

## Consequences

### Positive

- One execution identity spans manual, scheduled, graph, Builders, RSI, Evolve and delegated work.
- Retry and crash-resume preserve logical identity.
- Cancellation can be made persistence-safe.
- Durable waits do not require live workers.
- Observability and UI can show logical work separately from physical retries.

### Negative

- Existing Task/GraphRun/A2A/Builders lifecycle models need adapters.
- Reconciliation logic becomes an explicit platform responsibility.
- Existing code that equates "retry" with "new task" must migrate.

## Alternatives Considered

- **One record for logical and physical execution:** rejected because retries/resume overwrite history or require new logical identities.
- **GraphRun as universal lifecycle:** rejected because graph traversal is not universal execution lifecycle.
- **Task as universal lifecycle:** rejected because current Task mixes ingress, queueing and execution.

## Compliance

A path complies when it creates one Run per logical execution, one NodeRun per logically executed Node, and one Attempt per physical try; retries/resume preserve Run/NodeRun identity; terminalization is persistence-safe; and no scheduler, delegator or specialized package becomes a competing execution authority.

## References

- `ADR-081226-9944`
- `docs/analysis/EXECUTION-RUNTIME-SEAM-MAP.md`
- `docs/analysis/ARCHITECTURE-CONVERGENCE-MATRIX.md`
