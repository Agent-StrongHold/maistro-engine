---
id: SPEC-081426-b1d3
title: Project Scope Tree
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
  - maistro-engine#ADR-081426-b1d3
implements:
  - maistro-engine#ADR-081426-b1d3
related:
  - maistro-engine#ADR-081226-9944
  - maistro-engine#ADR-081226-6e34
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
source:
  - packages/maistro-core/src/maistro/projects
  - packages/maistro-core/src/maistro/workspaces
layer: Domain
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081426-b1d3: Project Scope Tree

- **Status:** Active
- **Date:** 2026-08-14
- **ADR:** `ADR-081426-b1d3`

## Required model

```text
Workspace
├── Persona
├── Templates[]
└── Root Project
    ├── Project[]
    └── project-scoped objects/resources
```

## Requirements

### R1. Root Project

Creating a Workspace MUST create exactly one persisted Root Project in the same durable operation or an equivalent failure-atomic workflow. The Root Project MUST have a stable `project_id`, the Workspace's `workspace_id`, `parent_project_id = null`, and `is_root = true`.

Root creation MUST be idempotent for a Workspace. The Root Project MUST NOT be moved, deleted, or assigned a parent.

### R2. Project tree integrity

Every non-root Project MUST belong to exactly one Workspace and have exactly one parent Project in that Workspace. Project ancestry MUST be acyclic. Cross-Workspace parenting and moves MUST be rejected.

### R3. Project-scoped object membership

Every project-scoped durable object MUST carry a non-empty `project_id` whose Project belongs to the object's Workspace. Objects filed at the visible Workspace root use the Root Project's ID rather than a nullable Project reference.

### R4. Workspace-wide Templates

NodeTemplate and GraphTemplate MUST remain Workspace-owned and MUST NOT require Project membership. Template instantiation MUST require a destination Project in the same Workspace. The instantiated object MUST carry the destination `project_id` while preserving exact Template provenance.

### R5. Creation defaults

Creation defaults MUST resolve in this order:

```text
Workspace -> Persona -> Root Project -> ancestors -> destination Project
```

For each setting, the closest specified value wins. Resolved values become owned configuration on the new object. Later Project-default changes MUST NOT mutate existing objects. Moving an object MUST NOT reapply defaults.

### R6. Scoped resource visibility

A resource scoped to Project P MUST be visible to P and descendants of P only. It MUST NOT become visible to ancestors, siblings, or Projects outside P's subtree. Cross-Workspace resource visibility is denied by default.

### R7. Object moves

Moving an object MUST preserve its existing owned configuration. Before committing the move, the service MUST verify that every required scoped resource remains visible from the destination Project. If any required resource is unavailable, the move MUST fail atomically with the object's original Project unchanged.

### R8. Membership and grants

Workspace grants and all applicable Project grants from the destination object's ancestry MUST accumulate. A Project grant applies only within the Project subtree in which it was issued. A narrower Project MAY grant actions not granted at broader scopes.

### R9. Denies

Applicable explicit denies MUST accumulate. If an action/resource is both granted and denied, the deny wins. A descendant grant MUST NOT bypass a deny inherited from an ancestor scope.

Conceptually:

```text
effective authority = union(applicable grants) - union(applicable denies)
```

### R10. Delegation authority

Authority to perform an action MUST NOT imply authority to delegate that action. Grant/delegation authority MUST be explicit and scope-bound.

### R11. Project deletion

Root Project deletion MUST always fail. Non-root Project deletion MUST fail while the Project contains child Projects or durable project-scoped content/resources requiring explicit disposition. Deletion MUST NOT implicitly recursively delete, move, or reparent contained state.

### R12. Persona exclusion from authorization

Persona MUST NOT contribute grants, denies, credential visibility, or security authority. Persona preferences MAY select or prefer a capability/provider/binding only after Project/resource authorization has made it available.

## Acceptance Criteria

1. Creating a Workspace creates exactly one stable Root Project; repeated root provisioning returns the same Project.
2. Root Project cannot be moved, deleted, or parented.
3. Nested Projects maintain same-Workspace parent/child integrity and reject cycles.
4. A project-scoped Graph created at the Workspace root carries the Root Project ID rather than a null Project ID.
5. Workspace-wide GraphTemplate instantiation into Project A yields a Graph in A while leaving the Template Workspace-wide.
6. Project defaults resolve nearest-wins at creation and never retroactively mutate an existing object.
7. Moving an object leaves its resolved configuration byte-for-byte equivalent except for filing/scope metadata.
8. A Root credential/resource is visible from all descendants; a child resource is invisible to the Root and siblings.
9. A move requiring a resource unavailable in the destination is rejected without changing the object's original `project_id`.
10. Workspace + ancestor + target Project grants accumulate inside the target scope and do not leak to siblings.
11. A narrower Project can grant stronger authority inside its subtree.
12. An inherited deny beats both inherited and descendant grants.
13. `publish` permission alone does not allow granting `publish` to another principal.
14. A non-empty Project cannot be deleted implicitly.
15. Persona configuration cannot create authorization that Project/Workspace grants do not provide.

## Migration guidance

The existing Project package MUST be re-audited piece-by-piece. Matching tree/resource behavior may be refactored into this model. Existing assumptions that Project is the Workspace ownership root MUST be removed rather than preserved through compatibility facades.

## Non-goals

This SPEC does not define UI folder presentation, graph traversal, Run state transitions, Provider selection algorithms, or the storage technology used for Project persistence.
