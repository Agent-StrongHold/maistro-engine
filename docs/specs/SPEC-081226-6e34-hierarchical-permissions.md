---
id: SPEC-081226-6e34
title: Hierarchical Permissions
repo: maistro-engine
kind: spec
status: Accepted
created: 2026-08-12
history:
  - status: Proposed
    date: 2026-08-12
  - status: Accepted
    date: 2026-08-12
substrate:
  - maistro-engine#ADR-081226-6e34
implements:
  - maistro-engine#ADR-081226-6e34
related:
  - maistro-engine#ADR-081226-9944
  - maistro-engine#ADR-081226-6b46
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests:
  - packages/maistro-core/tests/workspaces/test_membership.py
source:
  - packages/maistro-core/src/maistro/workspaces
  - packages/maistro-core/src/maistro/policy
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-6e34: Hierarchical Permissions

- **Status:** Active
- **Date:** 2026-08-12
- **Updated:** 2026-08-13
- **ADR:** `ADR-081226-6e34`

## Canonical chain

```text
User -> WorkspaceMembership -> Workspace -> Persona -> Graph -> Node -> Binding -> Invocation
```

## Requirements

1. Workspace operations resolve the User's WorkspaceMembership first.
2. Workspace roles are `member`, `contributor`, and `owner`.
3. Member uses existing workflows/resources but does not edit shared
   Graph/Node/Template definitions.
4. Contributor includes member behavior and may create/edit shared definitions.
5. Owner includes contributor behavior and additionally changes Persona,
   membership/roles, and Workspace-wide configuration.
6. Each later layer may preserve or narrow the result from earlier layers.
7. Binding and Invocation may not expand what the earlier Workspace/Persona/
   Graph/Node context allows.
8. Child Runs inherit the current Workspace context and may narrow it.
9. Cross-Workspace behavior requires an explicit product mechanism.
10. Product-surface checks and execution-time checks use the same canonical
    Workspace and membership identity.

## Evaluation order

1. User
2. WorkspaceMembership
3. Workspace
4. Persona
5. Graph
6. Node
7. Binding
8. Invocation

A restriction at any layer remains effective below that layer.

## Acceptance criteria

- canonical role behavior matches the Workspace role contract;
- contributor cannot perform owner-only Workspace changes;
- Graph/Node/Binding restrictions can narrow any Workspace role;
- child Runs do not gain capabilities absent from their inherited context; and
- cross-Workspace execution is not implicit.
