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
  - packages/maistro-core/tests/test_graph_definitions.py
  - packages/maistro-core/tests/test_node_type_registry.py
  - packages/maistro-core/tests/runs/test_lifecycle.py
  - packages/maistro-core/tests/runs/test_store.py
source:
  - packages/maistro-core/src/maistro/graph
  - packages/maistro-core/src/maistro/runs
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
├── immutable GraphSnapshot
├── GraphExecutionState
└── NodeRun[] -> Attempt[] -> ExecutionRuntime
```

## Requirements

1. A Graph MUST support one or more Nodes; one Node is valid.
2. A persisted Graph MUST contain a non-empty `workspace_id`.
3. Node IDs MUST be unique within a Graph and Edges MUST reference Nodes in that Graph.
4. Run creation MUST capture Graph identity, Workspace identity, a stable content hash and serialized Graph definition.
5. Editing a Graph after Run creation MUST NOT change the captured Run snapshot.
6. Node definition MUST contain NodeType/configuration and MUST NOT contain live Run/Attempt state.
7. Traversal selection of a Node MUST create/use a canonical NodeRun; physical work MUST occur through Attempt.
8. Repeated traversal of the same Node MAY create another NodeRun with a new NodeRun identity/ordinal in the same Run.
9. NodeType implementations MUST NOT persist/own an independent universal Run lifecycle.
10. GraphExecutionState MUST be separable from Run and MUST contain graph-specific traversal state only.
11. Edge predicates/conditional routing MUST be evaluated by graph/domain logic, not ExecutionRuntime.
12. Fanout/fanin readiness MUST be decided by graph/domain logic; Runtime MAY enforce bounded concurrency after Nodes are declared ready.
13. A subgraph Node SHOULD create a child Run with parent/NodeRun correlation and an immutable target snapshot.
14. Child Runs MUST NOT implicitly cross Workspace boundaries.
15. `GraphConfig`, `GraphRun`, `DurableRunRecord`, `DurableNodeRecord` and equivalent duplicate lifecycle types are removal targets, not compatibility contracts.

## NodeType registry contract

A NodeType registration MUST declare enough metadata for the domain layer to validate and dispatch it, including a stable type identifier, configuration/schema contract and executor/binding strategy. Registration MUST NOT grant permissions by itself.

Initial canonical categories:

- `agent`
- `api`
- `capability` with `tool` alias
- `harness`
- `human`
- `evaluation`
- `transform`
- `control` with `router` alias
- `subgraph`

Package-specific types MAY extend the registry.

## Acceptance Criteria

1. A one-node Graph can be captured into a Run snapshot.
2. Editing a Graph after Run creation does not change the snapshot or its materialized definition.
3. A Graph without Workspace scope is rejected.
4. Duplicate Node IDs and Edges targeting Nodes outside the Graph are rejected.
5. Run creation rejects a Graph whose Workspace differs from its declared Run scope.
6. NodeRun creation rejects a Node ID absent from the captured snapshot.
7. Repeated execution of the same Node creates distinct NodeRuns under the same Run.
8. A NodeType test proves Runtime receives ready work without importing/interpreting graph predicates.
9. A subgraph child Run records parent Run/NodeRun correlation and rejects implicit cross-Workspace creation.
10. Architecture fitness checks can detect a NodeType executor that attempts to own Run persistence.

## Non-goals

This SPEC does not define the permission algorithm, capability provider selection, event envelope or UI graph editor behavior.
