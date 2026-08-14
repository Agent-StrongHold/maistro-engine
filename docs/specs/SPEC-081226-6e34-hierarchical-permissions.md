---
id: SPEC-081226-6e34
title: Scoped Grants and Deny-Wins Authorization
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
  - maistro-engine#ADR-081226-6e34
implements:
  - maistro-engine#ADR-081226-6e34
related:
  - maistro-engine#ADR-081426-b1d3
  - maistro-engine#ADR-081226-9944
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - security
  - behavioral
tests: []
source:
  - packages/maistro-core/src/maistro/projects
  - packages/maistro-core/src/maistro/security
layer: Security
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-6e34: Scoped Grants and Deny-Wins Authorization

- **Status:** Active
- **Date:** 2026-08-14 revision
- **ADR:** `ADR-081226-6e34`

## Authorization inputs

Effective authorization for a principal operating on a project-scoped object MUST be resolvable from structural data including:

```text
Principal
WorkspaceMembership
Project ancestry
ProjectMembership / scoped grants
object-specific grants where supported
explicit denies
Policies
resource visibility
```

Persona is not an authorization input.

## Requirements

### R1. Scope containment

Every grant/deny MUST have a scope. A Project-scoped grant or deny applies only to that Project and descendants. No Project authorization record may leak to siblings, ancestors, another Workspace, or otherwise outside its declared scope.

### R2. Additive grants

All applicable grants MUST accumulate. A narrower scope MAY add actions unavailable at a broader scope.

### R3. Deny wins

All applicable denies MUST accumulate. If an action/resource selector is both granted and denied, the deny MUST win regardless of which applicable scope supplied the grant.

### R4. No grant-around-deny

A grant created below the scope of an inherited deny MUST NOT restore the denied action/resource.

### R5. Workspace boundary

Cross-Workspace authorization MUST fail closed by default. Project membership never creates Workspace membership or access to another Workspace.

### R6. Resource visibility

Project-scoped resource visibility MUST be evaluated before use. A resource attached to an ancestor is available downward; a child resource is not available upward or sideways. An action grant MUST NOT by itself make an otherwise invisible resource visible.

### R7. Explicit delegation

Delegating/granting authority MUST require an explicit delegation permission or equivalent rule for the target action/scope. Possessing action X MUST NOT imply permission to grant X.

### R8. Role bundles

Named roles such as Workspace `owner`, `contributor`, and `member` MAY expand into grant bundles for convenience. Roles MUST NOT replace granular grant/deny evaluation or be treated as a universal total ordering across different scopes.

### R9. Persona independence

Changing Persona purpose, taste, style, preferred Provider/Binding, defaults, or product surfaces MUST NOT change the principal's structural grants/denies or resource visibility.

### R10. Invocation authorization

Before a Binding/Provider/Invocation uses a Project-scoped resource, the authorization path MUST verify both required action authority and resource visibility. Provider fallback MUST NOT escape the Binding/resource authorization already established.

## Acceptance Criteria

1. `Workspace: member` plus `Project A: contributor` yields both grant sets inside A and only Workspace grants outside A.
2. A grant in Project A never appears in sibling Project B.
3. A child Project may grant `publish` even when Workspace grants do not include `publish`, and that grant remains inside the child subtree.
4. A Root deny of `publish` prevents a descendant `publish` grant from becoming effective.
5. An object-specific deny beats applicable Workspace/Project grants.
6. A child-scoped Credential remains unavailable from its parent even when the principal has a broad credential-use action grant.
7. A principal with `publish` but without delegation authority cannot grant `publish` to another principal.
8. A Project administrator with explicit `grant:publish` for the Project can grant `publish` inside that Project scope but not in a sibling.
9. Cross-Workspace Project/grant references are rejected.
10. Persona modifications produce identical authorization results for identical membership/grant/deny inputs.
11. Role bundles expand into granular grants and can still be constrained by explicit denies.
12. Binding/Provider fallback cannot select a resource outside the authorized/visible candidate set.

## Non-goals

This SPEC does not prescribe the persistence schema for grants/denies, the complete action vocabulary, policy-expression language, approval UX, or Warden/Sentinel internal algorithms.
