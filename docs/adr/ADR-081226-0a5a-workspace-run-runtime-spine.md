---
id: ADR-081226-0a5a
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
  - maistro-engine#SPEC-081226-ed22
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

# ADR-081226-0a5a: Workspace Run Runtime Spine

## Context

MAIstro already contains durable graph runs, task records, projects, sessions, events, approvals, memory, credentials, observability, scheduling, recovery, agent orchestration, and capability registries. Several execution paths still own overlapping lifecycle state and do not consistently carry the same ownership and provenance context.

`Project` is already the engine's per-user workspace model. Durable graph runs already carry `project_id`, checkpoints, status, timestamps, node records, errors, and blackboard state. Convergence should reuse these primitives rather than create a parallel execution system.

## Decision

MAIstro adopts one canonical execution spine:

`Workspace -> Run -> ExecutionRuntime -> Capabilities`

`Workspace` is the architectural/product role currently implemented by `Project`. A workspace scopes executable definitions, runs, integrations, skills/MCP allowlists, dashboards, memory, credentials, and policy.

A `Run` is the canonical unit of execution provenance. Every execution path that produces side effects or durable output must create a Run or execute as a child of an existing Run. Graph-specific state remains in the durable graph adapter rather than bloating the universal Run contract.

`ExecutionRuntime` owns cross-cutting lifecycle semantics and delegates execution mechanics to specialized adapters. It must establish workspace/run context before execution, preserve root/parent lineage, preserve correlation across capabilities, and provide one convergence point for graph, agent/team, task, scheduled/recovery, manual, and evolve/RSI execution.

Tools, approvals/security, memory, credentials, artifacts, scheduling/recovery, and observability may retain domain-specific records, but execution-time records must be attributable to the canonical Run.

This migration is additive. `Project` and persisted `project_id` remain compatible while new runtime-facing APIs use Workspace terminology. Existing specialized executors remain valid internals and are progressively routed through `ExecutionRuntime`.

## Contracts

Preconditions:
- new product execution has a non-empty authorized workspace identifier;
- child runs are created from an existing runtime context.

Postconditions:
- execution returns one stable canonical run identity;
- durable graph persistence carries the same workspace identity;
- resume preserves workspace, run, root, parent, and correlation identity.

Invariants:
- `root_run_id` does not change;
- child runs remain in the parent's workspace unless a later ADR defines explicit cross-workspace delegation;
- capabilities invoked under an execution context do not lose run/workspace correlation;
- adapters do not create a second top-level run identity for the same execution.

## Consequences

MAIstro gains one ownership/provenance/lifecycle spine while retaining proven subsystem mechanics. Existing direct-executor callers become explicit migration debt. Naming and persistence can migrate independently from semantics, avoiding a flag-day schema rewrite.

## Out of scope

- renaming every `project_id` column immediately;
- replacing specialized executor internals with one generic interpreter;
- cross-workspace delegation;
- Rust optimization before profiling identifies stable hot paths.