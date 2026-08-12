---
id: SPEC-081226-ed22
title: Workspace Run Runtime Spine
repo: maistro-engine
kind: spec
status: Accepted
created: 2026-08-12
accepted: 2026-08-12
substrate:
  - maistro-engine#ADR-081226-0a5a
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

# SPEC-081226-ed22: Workspace Run Runtime Spine

## Goal

Thread MAIstro's existing execution features through one ownership and lifecycle model without replacing proven specialized executors.

Target chain:

`Workspace -> Run -> ExecutionRuntime -> Capabilities`

## Existing substrate

- `maistro.projects.types.Project`: current workspace model.
- `maistro.graph.durable_runs.DurableRunRecord`: durable graph execution snapshot.
- `maistro.graph.durable_runs.executor`: graph start/resume/checkpoint mechanics.
- event, task/recovery, memory, credential, security, capability, artifact, and observability subsystems: consumers of canonical execution correlation.

## Runtime boundary

### WorkspaceRef

Required: `workspace_id`. Optional: `actor_id`. A Project converts losslessly using `Project.id`.

### RunKind

Initial kinds: `graph`, `agent`, `team`, `task`, `scheduled`, `manual`, `evolve`.

### RunState

Canonical states: `pending`, `running`, `paused`, `completed`, `failed`, `cancelled`. Adapter-specific pause reasons remain adapter metadata.

### RunContext

Required identity/provenance fields:
- `run_id`
- `workspace_id`
- `kind`
- `state`
- `root_run_id`
- `parent_run_id | None`
- `actor_id | None`
- `correlation_id`
- `metadata`

Top-level runs use `root_run_id == run_id`. Child runs inherit workspace, root, actor, and correlation identity from their parent.

### ExecutionContext

Carries RunContext plus capability/service bindings. Adapters and capabilities consume this rather than inventing independent run correlation.

### ExecutionRuntime

Initial graph API:

```python
await runtime.run_graph(...)
await runtime.resume_graph(run_id, ...)
runtime.child_context(parent, *, kind, run_id=None)
```

Task, agent/team, scheduled/recovery, and evolve adapters converge on the same lifecycle contract.

## Graph adapter

`run_graph` delegates mechanics to `run_durable_dag`, writes `workspace_id` through the existing `project_id` compatibility field, and uses the durable graph `run_id` as the canonical run ID.

State projection:
- `pending -> pending`
- `running -> running`
- `paused_wait | paused_hitl -> paused`
- `completed -> completed`
- `failed -> failed`
- `cancelled -> cancelled`

`resume_graph` recovers persisted ownership before delegation and preserves the same canonical identity. The adapter must not create a duplicate top-level run record.

## Capability threading

Any capability invoked during execution must be able to receive `run_id`, `workspace_id`, `root_run_id`, `parent_run_id`, `correlation_id`, and actor identity. Individual capability migrations may remain separate commits, but bypasses must be inventoried and cannot be silently counted as complete.

## Acceptance criteria

**AC-1 Boundary validation:** valid runtime boundary models validate; empty required identifiers fail.

**AC-2 Root lineage:** top-level context has `root_run_id == run_id`, no parent, and stable correlation.

**AC-3 Child lineage:** child context preserves workspace/root/actor/correlation while receiving its own run ID and parent ID.

**AC-4 Graph start:** starting graph work for workspace W persists `DurableRunRecord.project_id == W`; returned canonical and durable run IDs are identical.

**AC-5 Graph resume:** resume does not change canonical run or workspace identity.

**AC-6 State projection:** all durable states map deterministically, including both pause states to canonical `paused`.

**AC-7 No double identity:** graph adapter uses the durable run ID as canonical Run ID.

**AC-8 Backward compatibility:** direct durable graph executor callers and persisted `project_id` remain valid during migration.

**AC-9 Capability correlation:** capability invocation from ExecutionContext retains run/workspace/root/parent/correlation identity.

**AC-10 Bypass inventory:** graph, agent/team, task, scheduler/recovery, manual, and evolve execution entry points are enumerated and either routed through ExecutionRuntime or recorded as explicit migration work with tests preventing new untracked bypasses.

**AC-11 Contract traceability:** tests use ADR-032 contract and scope markers and front-matter test paths resolve.

## Definition of done

Implemented means the runtime contracts exist, Workspace compatibility is exported, graph start/resume use canonical context, cross-cutting capability correlation is available, execution bypasses are inventoried/migrated, AC tests pass, registry lint passes, and no new execution path creates an independent top-level lifecycle model.