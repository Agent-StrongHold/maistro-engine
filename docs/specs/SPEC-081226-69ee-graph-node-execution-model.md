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
  - maistro-engine#ADR-081426-b1d3
  - maistro-engine#ADR-081226-a66b
  - maistro-engine#ADR-081426-1f7c
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
source:
  - packages/maistro-core/src/maistro/graph
  - packages/maistro-core/src/maistro/runs
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-69ee: Graph and Node Execution Model

- **Status:** Active
- **Date:** 2026-08-14 revision
- **ADR:** `ADR-081226-69ee`

## Required model

```text
Workspace-wide GraphTemplate
        |
        | instantiate into Project
        v
Project-scoped Graph
├── Node[]
└── Edge[]

Run
├── immutable GraphSnapshot(workspace_id, project_id)
├── GraphExecutionState
└── NodeRun[] -> Attempt[] -> ExecutionRuntime
```

## Requirements

1. A Graph MUST support one or more Nodes; one Node is valid.
2. A persisted Graph MUST contain non-empty `workspace_id` and `project_id` values.
3. The Graph's Project MUST belong to the Graph's Workspace.
4. Node IDs MUST be unique within a Graph and Edges MUST reference Nodes in that Graph.
5. GraphTemplate MUST remain Workspace-wide and MUST NOT carry destination Project filing as Template identity.
6. GraphTemplate instantiation MUST require a destination Project in the same Workspace and record exact Template provenance on the resulting Graph.
7. Run creation MUST capture Graph identity, Workspace identity, Project identity, stable content hash, and serialized Graph definition.
8. Editing or moving a Graph after Run creation MUST NOT change the captured Run snapshot.
9. Node definition MUST contain NodeType/configuration and MUST NOT contain live Run/Attempt state.
10. Traversal selection of a Node MUST create/use a canonical NodeRun; physical work MUST occur through Attempt.
11. Repeated traversal of the same Node MAY create another NodeRun with a new NodeRun identity/ordinal in the same Run.
12. NodeType implementations MUST NOT persist/own an independent universal Run lifecycle.
13. GraphExecutionState MUST be separable from Run and MUST contain graph-specific traversal state only.
14. Edge predicates/conditional routing MUST be evaluated by graph/domain logic, not ExecutionRuntime.
15. Fanout/fanin readiness MUST be decided by graph/domain logic; Runtime MAY enforce bounded concurrency after Nodes are declared ready.
16. A subgraph Node SHOULD create a child Run with parent/NodeRun correlation and an immutable target snapshot.
17. A child Run MUST default to its parent's Project unless an explicit same-Workspace destination Project is requested and authorized.
18. Child Runs MUST NOT cross Workspace boundaries through ordinary execution APIs.
19. `GraphConfig`, `GraphRun`, `DurableRunRecord`, `DurableNodeRecord`, and equivalent duplicate lifecycle types are removal targets, not compatibility contracts.

## NodeType registry contract

A NodeType registration MUST declare enough metadata for the domain layer to validate and dispatch it, including a stable type identifier, configuration/schema contract, and executor/binding strategy. Registration MUST NOT grant permissions by itself.

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

1. A one-node project-scoped Graph can be captured into a Run snapshot.
2. Editing or moving a Graph after Run creation does not change the snapshot, its materialized definition, or captured Project identity.
3. A Graph without Workspace or Project scope is rejected.
4. A Graph whose Project belongs to another Workspace is rejected by the canonical persistence/service boundary.
5. Duplicate Node IDs and Edges targeting Nodes outside the Graph are rejected.
6. Workspace-wide GraphTemplate instantiation requires a destination Project and produces independent topology/provenance.
7. NodeRun creation rejects a Node ID absent from the captured snapshot.
8. Repeated execution of the same Node creates distinct NodeRuns under the same Run.
9. A NodeType test proves Runtime receives ready work without importing/interpreting graph predicates.
10. A subgraph child Run inherits the parent's Project by default.
11. Explicit same-Workspace cross-Project child execution records the destination Project and requires authorization at the service boundary.
12. Cross-Workspace child creation is rejected.
13. Architecture fitness checks can detect a NodeType executor that attempts to own Run persistence.

## Non-goals

This SPEC does not define Project grant algorithms, Provider selection, durable Event envelopes, or UI graph-editor behavior.
