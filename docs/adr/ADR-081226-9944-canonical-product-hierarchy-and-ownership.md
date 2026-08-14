---
id: ADR-081226-9944
title: Canonical Product Hierarchy and Ownership
repo: maistro-engine
kind: adr
status: Accepted
created: 2026-08-12
accepted: 2026-08-12
layer: Foundation
owners: ['@BlakeMatthews-dev']
history:
  - status: Proposed
    date: 2026-08-12
  - status: Accepted
    date: 2026-08-12
---

# ADR-081226-9944: Canonical Product Hierarchy and Ownership

## Decision

MAIstro converges on the product spine:

```text
Workspace -> Run -> ExecutionRuntime -> Capabilities
```

Workspace is the durable product environment and ownership root. `Project` is not a compatibility persistence identity for Workspace; consumers must move to the canonical Workspace model directly.

User access is many-to-many through `WorkspaceMembership`:

```text
User[] <-> WorkspaceMembership[] <-> Workspace[]
```

Canonical Workspace roles are `member`, `contributor`, and `owner`. Members operate existing workflows and templates. Contributors additionally create or modify shared Graphs, Nodes, and Templates. Owners additionally control the Workspace Persona, membership/roles, and Workspace administration/policy.

Workspace identity and ownership are separate. A personal Workspace is simply one with one owner membership. A shared Workspace may have multiple members and multiple owners. Workspace records do not contain a primary-owner field.

A Workspace has one live Persona in normal product state. Temporary zero-Persona states are allowed only during bounded onboarding or replacement. Specialized executable actors are Agents/Nodes rather than secondary Personas.

Workspace owns or scopes Graphs, Runs, Sessions, Artifacts, Schedules, Memory, Credentials, Integrations, Policies, Templates, and its Persona. A one-node Graph is valid.

Execution converges on:

```text
Run -> NodeRun -> Attempt
```

Session remains continuity across Runs. Schedule remains trigger metadata that creates or resumes Runs. ExecutionRuntime owns mechanics, not Workspace, graph traversal, permission policy, or Run persistence semantics.

Capability fulfillment remains orthogonal:

```text
Capability -> Provider -> Binding -> Invocation
```

Specialized packages extend this hierarchy without introducing alternate universal ownership or execution roots. Duplicate legacy concepts are removed as their consumers are converted; preserving backward-compatible aliases is not an architectural requirement.
