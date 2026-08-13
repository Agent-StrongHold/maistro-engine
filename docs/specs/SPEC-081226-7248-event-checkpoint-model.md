# SPEC-081226-7248: Event and Checkpoint Model

- **Status:** Active
- **Date:** 2026-08-12
- **ADR:** `ADR-081226-7248`

## Event requirements

1. Canonical Event MUST contain `event_id`, `sequence`, `timestamp`, `workspace_id`, `type`, `payload` and actor/provenance; execution/session correlation IDs are included when applicable.
2. `event_id` MUST be unique and suitable for idempotent consumer processing.
3. `sequence` MUST be monotonic within the Workspace durable event stream and assigned by one canonical sequencing authority.
4. Canonical lifecycle events MUST be durably recoverable; an in-memory bus alone is insufficient.
5. Run/NodeRun/Attempt/Invocation transitions MUST emit correlated events after/with durable state commitment using transaction/outbox/reconciliation semantics.
6. A reconnecting UI/consumer MUST be able to resume from a known sequence/event position.
7. Domain payloads MAY vary but envelope correlation MUST remain stable.
8. Existing GraphEvent/StageEvent/package events MAY be projections during migration but MUST preserve canonical IDs on migrated paths.
9. Logs/traces/metrics MUST reference canonical correlation IDs but need not be duplicated as durable Events unless they represent product/domain facts.
10. Consumers MUST tolerate unknown event types/payload versions according to compatibility policy rather than corrupt ordering.

## Checkpoint requirements

1. Checkpoint MUST be immutable after creation.
2. Checkpoint MUST resolve Workspace and Run ownership and SHOULD identify NodeRun/Attempt where applicable.
3. Checkpoint MUST record state/schema compatibility metadata sufficient to reject unsafe resume.
4. Resume MUST create a new Attempt referencing `resume_checkpoint_id` while preserving non-terminal Run/NodeRun identity.
5. Durable graph checkpoint MUST be able to include/reference GraphExecutionState and graph snapshot identity.
6. Recovery MUST detect stale `running` state with no valid active Attempt.
7. Recovery MUST enforce crash-loop/retry policy before creating a replacement Attempt.
8. Checkpoint creation MUST emit a correlated canonical Event.
9. Large state MAY be stored as Artifact/storage locator; the Checkpoint record retains hash/version/provenance.

## Acceptance Criteria

1. Two concurrent event producers in one Workspace receive a deterministic monotonic sequence ordering from the event store.
2. Disconnect/reconnect of SSE/WebSocket can replay events after a supplied sequence without losing durable history.
3. A committed Run transition has a corresponding durable canonical event after reconciliation even if the process crashes between state write and fanout.
4. Duplicate event delivery does not duplicate idempotent consumer effects when keyed by `event_id`.
5. Builders StageEvent or GraphEvent adapter test preserves canonical `workspace_id/run_id/node_run_id` correlation.
6. A waiting NodeRun creates a Checkpoint, releases the worker, survives restart, and resumes via a new Attempt referencing that checkpoint.
7. Resume is rejected when checkpoint/executable compatibility metadata is invalid.
8. Stale `running` state with a dead/missing worker is detected and reconciled rather than displayed indefinitely as active.
9. Crash-loop policy prevents unlimited automatic recovery Attempts.
10. UI history and audit query can reconstruct Run chronology from the same canonical events.
11. Metrics/traces for an Invocation can be joined to its canonical Event/Run via correlation IDs without requiring them to be Event payloads.
12. Architecture fitness checks reject migrated package event publishers that invent a second canonical sequence for the same Workspace stream.

## Non-goals

This SPEC does not require event sourcing as the sole state persistence model, force every telemetry record into the event log, or prescribe one message broker.
