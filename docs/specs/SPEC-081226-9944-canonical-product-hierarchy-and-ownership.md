---
id: SPEC-081226-9944
title: Canonical Product Hierarchy and Ownership
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
  - maistro-engine#ADR-081226-9944
implements:
  - maistro-engine#ADR-081226-9944
related:
  - maistro-engine#ADR-081426-b1d3
  - maistro-engine#ADR-081226-e626
  - maistro-engine#ADR-081226-a66b
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
source:
  - packages/maistro-core/src/maistro/workspaces
  - packages/maistro-core/src/maistro/projects
  - packages/maistro-core/src/maistro/personas
  - packages/maistro-core/src/maistro/graph
  - packages/maistro-core/src/maistro/runs
layer: Domain
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-9944: Canonical Product Hierarchy and Ownership

- **Status:** Active
- **Date:** 2026-08-14 revision
- **ADR:** `ADR-081226-9944`

## Canonical hierarchy

```text
User[] <- WorkspaceMembership -> Workspace[]
Workspace
├── exactly one live Persona
├── Workspace-wide Templates[]
└── exactly one Root Project
    ├── nested Project[]
    └── project-scoped durable objects
```

Execution:

```text
Graph -> Node[]
Run -> NodeRun[] -> Attempt[] -> ExecutionRuntime
```

Capability fulfillment:

```text
Capability -> Provider -> Binding -> Invocation
```

## Requirements

1. Workspace MUST be the durable environment boundary and MUST NOT structurally require a single owning User.
2. Workspace membership MUST be represented separately from Workspace identity.
3. Every Workspace MUST have exactly one live Persona.
4. Persona MUST encode taste, style, purpose, and behavioral/default preferences rather than security authority.
5. Every Workspace MUST have exactly one persisted Root Project.
6. Project-scoped durable objects MUST identify exactly one Project in the same Workspace.
7. NodeTemplate and GraphTemplate MUST remain Workspace-wide reusable definitions rather than Project-filed objects.
8. Graph MUST be a project-scoped mutable composition object. Node definition MUST remain separate from NodeRun/Attempt execution state.
9. Run MUST be the universal logical execution identity and MUST preserve `workspace_id` and `project_id` from its captured Graph snapshot.
10. NodeRun MUST identify logical execution of a Node; Attempt MUST identify one physical try.
11. ExecutionRuntime MUST key physical work by Attempt identity and MUST not become the business lifecycle authority.
12. Session MUST remain distinct from Run and MAY span multiple Runs.
13. Capability, Provider, Binding, and Invocation MUST remain separate from Run lifecycle and Project ownership concepts.
14. Existing package-specific AgentRun/GraphRun/DurableRun/Task lifecycles MUST migrate toward the canonical execution hierarchy rather than become new universal lifecycle classes.

## Acceptance Criteria

1. A Workspace can have multiple Users through WorkspaceMembership without changing Workspace identity.
2. Workspace creation provisions one Root Project and one live Persona can be attached independently of membership.
3. A Workspace-wide Template can be instantiated into different Projects without moving or duplicating the Template itself.
4. A persisted Graph contains both Workspace and Project identity.
5. A Run captures the Graph's Workspace and Project identity immutably for that execution.
6. Retry preserves Run/NodeRun identity and creates a new Attempt.
7. Persona fields cannot grant permissions or expose otherwise unavailable credentials/resources.
8. Child Run creation cannot cross Workspace boundaries through ordinary execution APIs.
9. Architecture checks can identify new competing universal Run lifecycle definitions as violations.

## Non-goals

This SPEC delegates Project-tree details to `SPEC-081426-b1d3`, execution mechanics to `SPEC-081426-1f7c`, and authorization resolution details to `SPEC-081226-6e34`.
