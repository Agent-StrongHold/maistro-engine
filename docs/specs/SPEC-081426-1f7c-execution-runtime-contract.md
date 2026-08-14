---
id: SPEC-081426-1f7c
title: ExecutionRuntime Contract
repo: maistro-engine
kind: spec
status: AC Defined
created: 2026-08-14
history:
  - status: Proposed
    date: 2026-08-14
  - status: Accepted
    date: 2026-08-14
  - status: AC Defined
    date: 2026-08-14
substrate:
  - maistro-engine#ADR-081426-1f7c
implements:
  - maistro-engine#ADR-081426-1f7c
related:
  - maistro-engine#ADR-081226-a66b
  - maistro-engine#ADR-081226-69ee
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
source:
  - packages/maistro-core/src/maistro/runtime
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081426-1f7c: ExecutionRuntime Contract

- **Status:** Active
- **Date:** 2026-08-14
- **ADR:** `ADR-081426-1f7c`

## Public contract

The Runtime implementation MUST expose mechanics equivalent to:

```text
execute(work_item, execution_context, execution_id, executor, timeout?)
cancel(execution_id)
acquire_slot(execution_id)
release_slot(execution_id)
emit(opaque_event)
metrics()
health()
```

`execution_id` identifies one physical Attempt.

## Requirements

### R1. Opaque domain inputs

Runtime MUST NOT import or interpret Graph predicates, Run/NodeRun lifecycle state, Permission/Policy meaning, Binding/Provider selection, scheduling rules, delegation rules, or durable persistence semantics.

### R2. Attempt identity

Canonical callers MUST pass `Attempt.attempt_id` as Runtime `execution_id`. Concurrent Attempts in one logical Run MUST be independently addressable and cancellable.

### R3. Bounded concurrency

Runtime MUST enforce configured bounded concurrency. Capacity waiting MUST be cancellable and deadline-bound. Slot acquisition/release MUST remain balanced through success, failure, cancellation, and deadline expiry.

### R4. Duplicate execution IDs

An `execution_id` already active, waiting for a slot, or holding a public slot MUST NOT begin a duplicate physical execution or acquire a second slot.

### R5. Deadline scope

When `timeout_s` or equivalent Runtime deadline is configured, the deadline MUST include time waiting for execution capacity and time executing the workload.

### R6. Deadline classification

Runtime-owned deadline expiry MUST surface a distinct Runtime deadline signal, preferably `RuntimeDeadlineExceeded`, that remains a `TimeoutError` subtype. Only that signal increments Runtime timeout metrics.

If the executor independently raises `TimeoutError`, Runtime MUST propagate it as an executor failure and MUST NOT classify it as Runtime deadline expiry.

### R7. Cancellation

`cancel(execution_id)` MUST cancel both slot-waiting and actively executing work when it remains cancellable. Cancellation MUST not leak capacity. Runtime records mechanics cancellation only; persisted Attempt/NodeRun/Run terminalization belongs to the domain service.

### R8. Public slot metrics

`acquire_slot()` itself MUST record scheduling wait and peak-concurrency metrics. A caller using `acquire_slot`/`release_slot` directly MUST receive correct mechanics metrics without needing to call `execute()`.

### R9. Event lock safety

Runtime sequence allocation MUST be monotonic for successful allocations. Runtime MUST release the sequencing lock before awaiting arbitrary event-sink code. A sink that recursively calls `emit()` MUST not deadlock.

### R10. Event sink failure

An event-sink exception MAY propagate to the emitter, but MUST NOT leave the sequence lock held or corrupt Runtime capacity state. Durable event delivery guarantees are outside this Runtime contract.

### R11. Benchmark lifetime

Runtime benchmark `wall_seconds` MUST measure execution workload completion, excluding any optional sampler shutdown that occurs afterward. Throughput MUST use that workload lifetime.

### R12. Health and metrics

Runtime health/metrics MAY expose mechanics such as active executions, active slots, peak concurrency, scheduling wait, cancellation/failure/timeout counts, event sequence, loop lag, CPU, and RSS. These are telemetry and MUST NOT become authoritative Run lifecycle state.

## Acceptance Criteria

1. Two Attempts under one Run can execute concurrently with distinct execution IDs.
2. Configured concurrency is never exceeded.
3. A request that times out while waiting for the only slot raises the Runtime deadline signal and leaks no slot.
4. An executor-raised `TimeoutError` increments failure, not Runtime-timeout, metrics.
5. Cancellation while waiting for a slot leaves holder/waiter state and semaphore capacity consistent.
6. Duplicate waiter/holder execution IDs are rejected without consuming capacity.
7. Direct public slot acquisition records scheduling-wait and peak-concurrency metrics.
8. Recursive event emission from the sink completes without deadlock and receives increasing sequence numbers.
9. A sink exception does not permanently block later `emit()` calls.
10. Runtime source has no dependency on Graph traversal or canonical Run persistence modules.
11. The benchmark stops workload timing at execution completion even when lag sampling would otherwise continue.
12. Runtime `execution_id` is wired from `Attempt.attempt_id` in the canonical Attempt execution service.

## Non-goals

This SPEC does not define Run state transitions, retry eligibility, Graph traversal, Event durability, Provider fallback, or policy evaluation.
