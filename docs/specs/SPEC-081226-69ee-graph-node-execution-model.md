---
id: SPEC-081226-69ee
title: Graph and Node Execution Model
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
  - maistro-engine#ADR-081226-69ee
implements:
  - maistro-engine#ADR-081226-69ee
related:
  - maistro-engine#ADR-081226-a66b
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests:
  - packages/maistro-core/tests/test_graph_compat.py
  - packages/maistro-core/tests/test_node_type_registry.py
source:
  - packages/maistro-core/src/maistro/graph
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-69ee: Graph and Node Execution Model

- **Status:** Active
- **Date:** 2026-08-12
- **ADR:** `ADR-081226-69ee`

## Required model

```text
Graph
├── Node[]
└── Edge[]

Run
├── graph snapshot/reference
├── GraphExecutionState
└── NodeRun[] -> Attempt[] -> ExecutionRuntime
```

## Requirements

1. A Graph MUST support one or more Nodes; one Node is valid.
2. A persisted Graph MUST resolve Workspace ownership.
3. A Run MUST execute a stable effective Graph snapshot/reference that is not changed by later Graph edits.
4. Node definition MUST contain NodeType/configuration and MUST NOT contain live Run/Attempt state.
5. Traversal selection of a Node MUST create/use a canonical NodeRun; physical work MUST occur through Attempt.
6. NodeType implementations MUST NOT persist/own an independent universal Run lifecycle.
7. GraphExecutionState MUST be separable from Run and MUST contain graph-specific traversal state only.
8. Edge predicates/conditional routing MUST be evaluated by graph/domain logic, not ExecutionRuntime.
9. Fanout/fanin readiness MUST be decided by graph/domain logic; Runtime MAY enforce bounded concurrency after Nodes are declared ready.
10. A subgraph Node SHOULD create a child Run with parent/NodeRun correlation and an immutable target snapshot.
11. Durable graph persistence MUST preserve optimistic versioning/checkpoints/snapshots while mapping lifecycle to canonical Run/NodeRun.
12. Existing graph and durable behavior MUST have parity tests before duplicate paths are removed.

## NodeType registry contract

A NodeType registration MUST declare enough metadata for the domain layer to validate and dispatch it, including a stable type identifier, configuration/schema contract and executor/binding strategy. Registration MUST NOT grant permissions by itself.

Initial categories to support or map:

- `agent`
- `api`
- `capability` / `tool`
- `harness`
- `human`
- `evaluation`
- `transform`
- `control` / `router`
- `subgraph`

Package-specific types MAY extend the registry.

## Acceptance Criteria

1. A one-node Graph executes through Graph -> Run -> NodeRun -> Attempt.
2. Editing a Graph after Run start does not change the running snapshot.
3. Conditional routing chooses the same path in legacy GraphRun and canonical adapter tests.
4. Parallel fanout/fanin produces equivalent readiness/completion behavior under bounded Runtime concurrency.
5. Paused durable graph state reloads and resumes with the same graph snapshot and NodeRun identities.
6. Cancelling graph execution terminalizes active Attempts and reconciles NodeRuns/Run.
7. A NodeType test proves Runtime receives ready work without importing/interpreting graph predicates.
8. A subgraph Node creates a correlated child Run and parent NodeRun waits/reconciles correctly.
9. DurableRunRecord/DurableNodeRecord adapter tests prove canonical Run/NodeRun identity survives restart.
10. Architecture fitness checks can detect a NodeType executor that attempts to own Run persistence.

## Non-goals

This SPEC does not define the permission algorithm, capability provider selection, event envelope or UI graph editor behavior.
