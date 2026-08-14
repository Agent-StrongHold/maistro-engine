---
id: ADR-081226-6e34
title: Hierarchical Permissions
repo: maistro-engine
kind: adr
status: Accepted
created: 2026-08-12
accepted: 2026-08-12
history:
  - status: Proposed
    date: 2026-08-12
  - status: Accepted
    date: 2026-08-12
substrate: []
implements: []
related:
  - maistro-engine#ADR-081226-9944
  - maistro-engine#ADR-081226-e626
  - maistro-engine#ADR-081226-6b46
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
  - packages/maistro-core/src/maistro/policy
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# ADR-081226-6e34: Hierarchical Permissions

- **Status:** Accepted
- **Date:** 2026-08-12
- **Updated:** 2026-08-13
- **Deciders:** MAIstro maintainers
- **Technical Area:** Authorization, policy, credentials, security

## Context

MAIstro has auth scopes, collaboration roles, agent/tool allowlists, approval
checks, sandbox restrictions, credential rules and package-specific trust
systems. These controls need one path that follows the actual Workspace and Run
model.

Product review clarified that Workspace access is not a property of Workspace
itself. It is the User-to-Workspace `WorkspaceMembership` relationship.

## Decision

Authorization narrows through:

```text
User
  -> WorkspaceMembership
    -> Workspace
      -> Persona
        -> Graph
          -> Node
            -> Binding
              -> Invocation
```

WorkspaceMembership contributes the collaboration role for that User in that
Workspace. Canonical roles are member, contributor and owner.

- member may operate existing Workspace workflows/resources within the remaining
  effective limits;
- contributor adds shared Graph/Node/Template editing;
- owner adds Workspace-level Persona, membership/role and administrative changes.

Each later level may inherit or narrow what came before. A child does not create
new authority absent from its ancestors.

Permission and Policy remain distinct. Permission determines whether an action
is available at all. Policy determines whether an otherwise available action may
proceed under current conditions. Policy can deny, defer or add conditions; it
does not manufacture unavailable authority.

Invocation remains the final execution enforcement boundary for external/tool/
model/provider/harness/sandbox/agent-backed fulfillment. Earlier product checks
remain useful for UX and defense in depth.

Child Runs inherit Workspace and authorization context and may narrow it.
Cross-Workspace behavior requires an explicit mechanism rather than implicit
parentage.

Credential resolution follows an allowed Binding/Invocation and remains subject
to credential scope. Existing Warden/Sentinel/Gate/trust/sandbox systems become
inputs/evaluators on this canonical path rather than alternate roots.

## Consequences

- Collaboration roles are part of the same effective authorization path as
  Persona, Graph, Node and Binding restrictions.
- Shared Workspaces no longer need a parallel collaboration security model.
- Agent-backed tools cannot exceed the calling context.
- Existing direct provider/tool paths need convergence where they bypass this
  boundary.

## Compliance

A path complies when it resolves the actor's WorkspaceMembership, applies the
role contribution, narrows through Workspace/Persona/Graph/Node/Binding, checks
the Invocation before fulfillment, and keeps policy incapable of widening the
result.

## References

- `ADR-081226-9944`
- `ADR-081226-e626`
- `ADR-081226-6b46`
