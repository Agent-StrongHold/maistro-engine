---
id: ADR-039
title: Workspace Run Runtime Spine
repo: maistro-engine
kind: adr
status: Accepted
created: 2026-08-12
accepted: 2026-08-12
substrate:
  - maistro-engine#ADR-032
  - maistro-engine#ADR-037
  - maistro-engine#ADR-038
implements:
  - maistro-engine#SPEC-196
related:
  - maistro-engine#ADR-010
  - maistro-engine#ADR-011
  - maistro-engine#ADR-018
  - maistro-engine#SPEC-177
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests:
  - packages/maistro-core/tests/runtime/test_execution_runtime.py
  - packages/maistro-core/tests/runtime/test_runtime_contracts.py
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
history:
  - status: Accepted
    date: 2026-08-12
---

# ADR-039: Workspace Run Runtime Spine

## Context

MAIstro already contains durable graph runs, task records, projects, sessions, events, approvals, memory, credentials, observability, scheduling, recovery, agent orchestration, and capability registries. The problem is not absence of primitives. The problem is that several execution paths own overlapping lifecycle state and do not consistently carry the same ownership and provenance context.

`Project` is already documented in code as a per-user workspace, and durable graph runs already carry `project_id`, checkpoints, status, timestamps, node records, errors, and blackboard state. We should converge those existing primitives instead of building a parallel execution system.

## Decision

MAIstro adopts one canonical product/runtime spine:

`Workspace -> Run -> ExecutionRuntime -> Capabilities`

### Workspace

The existing `Project` domain model is the current workspace implementation. `Workspace` is the product term and architectural role; `Project` remains a compatibility name until callers migrate. A workspace owns or scopes executable definitions, runs, integrations, enabled skills/MCP servers, dashboards, memory scope, credentials, and policy.

### Run

A Run is the canonical unit of execution provenance. Existing `DurableRunRecord` becomes the durable graph adapter for the canonical Run contract. Every execution path that can produce side effects or durable output must either create a Run or explicitly attach itself as a child operation of an existing Run.

A Run must carry at minimum:

- `run_id`
- `workspace_id`
- `kind`
- lifecycle `status`
- parent/root lineage
- actor/user identity when available
- input/output or durable references
- timestamps
- error state
- event/provenance correlation

Graph-specific details such as DAG snapshots and node checkpoints remain graph adapter state, not universal Run fields.

### ExecutionRuntime

`ExecutionRuntime` is the single orchestration contract for starting, resuming, cancelling, and observing work. It does not replace specialized executors. It owns cross-cutting lifecycle semantics and delegates mechanics to adapters such as the durable DAG executor.

The runtime must:

1. require workspace ownership for newly started product work;
2. create or bind the canonical Run context before execution begins;
3. preserve run/workspace/root/parent identity through child execution;
4. expose one event correlation context to capabilities;
5. delegate graph mechanics to the existing durable executor;
6. provide extension points for tasks, agents/teams, scheduler/recovery, and evolve/RSI without giving those systems independent top-level lifecycle models.

### Capabilities

Tools, approvals/security, memory, credentials, artifacts, scheduling/recovery, and observability consume `ExecutionContext`. They may persist their own domain records, but those records must be attributable to a canonical Run when invoked during execution.

### Compatibility

This is an incremental convergence, not a flag-day rewrite.

- `Project` stays valid and is aliased as `Workspace` at the runtime boundary.
- `project_id` in durable run persistence remains readable; the runtime exposes it as `workspace_id` and writes the same identifier during migration.
- existing durable DAG functions remain usable internally; product entry points should migrate to `ExecutionRuntime`.
- specialized task/session/event records remain until their callers are migrated and proven redundant.

## Behavioral contracts

### Pre-conditions

- A new product Run has a non-empty workspace identifier.
- The referenced workspace is available to the caller or has already been authorized by the product boundary.
- A child Run has a valid parent/root lineage supplied by the invoking runtime context.

### Post-conditions

- Starting work returns a canonical Run projection with stable run/workspace identity.
- Durable graph execution persists the same workspace identifier on its `DurableRunRecord`.
- Resume preserves run/workspace/root/parent identity.
- Terminal state is represented consistently as completed, failed, or cancelled.

### Invariants

- `root_run_id` never changes after creation.
- a child run's `workspace_id` equals its parent's `workspace_id` unless an explicit cross-workspace delegation contract is introduced by a later ADR.
- capability operations invoked under a runtime context never lose `run_id` and `workspace_id` correlation.
- compatibility adapters do not create a second top-level run identity for the same execution.

## Consequences

- MAIstro gains one place to thread ownership, provenance, lifecycle, recovery, and capability context.
- Existing graph durability work is reused rather than replaced.
- `Project` naming remains temporarily visible in persistence and older APIs, but the architectural meaning is Workspace.
- Callers that bypass `ExecutionRuntime` become migration debt and should be enumerated and burned down.

## Out of scope

- renaming every `project_id` column in one migration;
- replacing specialized executor internals with a generic interpreter;
- Rust optimization before profiling identifies stable hot paths;
- cross-workspace delegation semantics.