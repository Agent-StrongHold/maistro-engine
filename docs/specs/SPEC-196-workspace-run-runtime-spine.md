---
id: SPEC-196
title: Workspace Run Runtime Spine
repo: maistro-engine
kind: spec
status: Accepted
created: 2026-08-12
accepted: 2026-08-12
substrate:
  - maistro-engine#ADR-039
implements: []
related:
  - maistro-engine#SPEC-177
  - maistro-engine#SPEC-184
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

# SPEC-196: Workspace Run Runtime Spine

## Goal

Thread MAIstro's existing execution features through one ownership and lifecycle model without replacing proven specialized executors.

The target chain is:

`Workspace -> Run -> ExecutionRuntime -> Capabilities`

## Existing substrate to reuse

- `maistro.projects.types.Project`: existing per-user workspace model.
- `maistro.graph.durable_runs.DurableRunRecord`: durable graph execution snapshot.
- `maistro.graph.durable_runs.executor`: graph start/resume/checkpoint mechanics.
- `maistro.events`: event bus and durable event infrastructure.
- `maistro.tasks`: queue, checkpoint, recovery, replay, and task runner primitives.
- `maistro.memory`, `maistro.credentials`, `maistro.security`, `maistro.capabilities`, and `maistro.observability`: capability systems that must receive canonical execution correlation.

## Public runtime contract

### WorkspaceRef

A lightweight boundary representation of an authorized workspace.

Required fields:

- `workspace_id: str`
- `actor_id: str | None`

A `Project` converts losslessly to a `WorkspaceRef` using `Project.id`.

### RunKind

Initial values:

- `graph`
- `agent`
- `team`
- `task`
- `scheduled`
- `manual`
- `evolve`

Unknown future kinds must be introduced additively.

### RunState

Canonical lifecycle values:

- `pending`
- `running`
- `paused`
- `completed`
- `failed`
- `cancelled`

Adapter-specific pause reasons stay in adapter metadata.

### RunContext

Required fields:

- `run_id`
- `workspace_id`
- `kind`
- `state`
- `root_run_id`
- `parent_run_id | None`
- `actor_id | None`
- `correlation_id`
- `metadata`

Rules:

- top-level `root_run_id == run_id`;
- child `root_run_id == parent.root_run_id`;
- child `workspace_id == parent.workspace_id`;
- correlation ID defaults to root run ID unless supplied by an inbound boundary.

### ExecutionContext

Passed to adapters and capabilities. Contains the canonical `RunContext` plus capability/service bindings. This is the object that prevents tools, memory, approvals, credentials, artifacts, and telemetry from inventing their own run correlation.

### ExecutionRuntime

Initial API:

```python
await runtime.run_graph(...)
await runtime.resume_graph(run_id)
runtime.child_context(parent, *, kind, run_id=None)
```

Later adapters add task/agent/team/scheduled/evolve methods behind the same lifecycle contract.

## Graph adapter

`ExecutionRuntime.run_graph` MUST delegate execution mechanics to `run_durable_dag` and pass `workspace_id` through the existing `project_id` compatibility field.

The returned `DurableRunRecord` is projected into canonical runtime semantics:

- `project_id -> workspace_id`
- `paused_wait | paused_hitl -> paused`
- graph run ID is the canonical run ID
- graph errors map to canonical failed state

No duplicate top-level run record may be created merely to wrap a durable graph run.

`resume_graph` MUST recover the durable record first so it can preserve workspace identity before delegation.

## Workspace compatibility

`Project` remains the storage/domain implementation during migration. A compatibility export named `Workspace` may alias `Project`; this is semantic convergence, not a destructive database rename.

All new runtime-facing APIs use `workspace_id` terminology. Existing persistence adapters may continue using `project_id` until schema migration is justified.

## Capability threading

Any capability invoked from an `ExecutionContext` must be able to access:

- `run_id`
- `workspace_id`
- `root_run_id`
- `parent_run_id`
- `correlation_id`
- `actor_id`

Initial implementation provides the context contract and graph threading. Follow-on migrations wire each capability's invocation boundary to consume it.

## Acceptance criteria

### AC-1 Boundary contract

Given valid workspace/run identifiers, `WorkspaceRef`, `RunContext`, and `ExecutionContext` validate. Empty required identifiers fail validation.

### AC-2 Root lineage

Given a top-level run context, `root_run_id == run_id`, `parent_run_id is None`, and `correlation_id` is stable.

### AC-3 Child lineage

Given a parent context, creating a child preserves `workspace_id`, `root_run_id`, actor identity, and correlation ID while assigning a distinct `run_id` and `parent_run_id`.

### AC-4 Graph start threading

When `ExecutionRuntime.run_graph` starts a graph for workspace `W`, the persisted `DurableRunRecord.project_id == W` and the returned canonical projection has `workspace_id == W` with the same `run_id`.

### AC-5 Graph resume threading

When a paused graph run is resumed, workspace identity and canonical run identity remain unchanged.

### AC-6 State mapping

Durable graph states map deterministically to canonical states, including both durable pause states mapping to canonical `paused`.

### AC-7 No double identity

For a graph execution, the durable graph `run_id` is the canonical Run `run_id`. The runtime does not create a second top-level execution identity.

### AC-8 Backward compatibility

Direct callers of `run_durable_dag` remain valid. Existing `project_id` persistence remains readable. The new runtime is additive during migration.

### AC-9 Contract traceability

Tests proving AC-1 through AC-8 are marked with ADR-032's two-axis contract/scope markers or the repository's closest currently-supported equivalent until registry enforcement lands.

## Definition of done

This spec is Implemented when:

1. runtime boundary types and `ExecutionRuntime` exist in `maistro-core`;
2. graph execution start/resume use the canonical context through the runtime adapter;
3. Workspace compatibility is exported without breaking `Project` callers;
4. AC-1 through AC-9 pass in CI;
5. the spec registry lists SPEC-196;
6. remaining bypass paths are explicitly inventoried for migration rather than silently treated as complete.