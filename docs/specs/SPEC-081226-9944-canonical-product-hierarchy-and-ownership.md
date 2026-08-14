---
id: SPEC-081226-9944
title: Canonical Product Hierarchy and Ownership
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
  - maistro-engine#ADR-081226-9944
implements:
  - maistro-engine#ADR-081226-9944
related: []
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests:
  - packages/maistro-core/tests/workspaces/test_membership.py
  - packages/maistro-core/tests/workspaces/test_store.py
source:
  - packages/maistro-core/src/maistro/workspaces
layer: Foundation
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-9944: Canonical Product Hierarchy and Ownership

- **Status:** Active
- **Date:** 2026-08-12
- **Updated:** 2026-08-13
- **ADR:** `ADR-081226-9944`

## Canonical model

```text
User[] <-> WorkspaceMembership[] <-> Workspace[]
                                      ├── Persona (one live)
                                      ├── Graph[] -> Node[]
                                      ├── Run[] -> NodeRun[] -> Attempt[]
                                      ├── Session[]
                                      ├── Artifact[]
                                      └── templates and other Workspace resources
```

## Requirements

1. `Workspace` is the durable product environment and canonical ownership root.
2. Workspace identity MUST NOT be represented by a Project alias or legacy persistence key.
3. Workspace ownership/access MUST be represented by `WorkspaceMembership`, not an `owner_user_id` field on Workspace.
4. `WorkspaceMembership` supports many users per Workspace and many Workspaces per user.
5. Canonical Workspace roles are `member`, `contributor`, and `owner`.
6. Member operates existing workflows/templates but does not edit shared Graph/Node/Template definitions.
7. Contributor includes member behavior and may create/edit shared Graph/Node/Template definitions.
8. Owner includes contributor behavior and additionally changes the Workspace Persona, membership/roles, and Workspace-wide configuration.
9. A Workspace MUST retain at least one owner membership and MAY have multiple owners.
10. Normal Workspace-to-live-Persona cardinality is 1:1. Canonical persistence rejects a second live Persona for the same Workspace.
11. Temporary zero-Persona state is allowed only for bounded onboarding, deletion, or replacement transitions.
12. Specialized executable actors are Agents/Nodes rather than additional Personas.
13. A persisted Graph MUST contain its `workspace_id`; no `project_id` fallback is required.
14. A one-node Graph is valid and uses the same canonical Run path as any other Graph.
15. Manual, scheduled, delegated, Builders, RSI, Evolve and specialized-package execution converges on Workspace-owned Run/NodeRun/Attempt state.
16. Session remains continuity across Runs; Schedule remains trigger metadata.
17. ExecutionRuntime owns execution mechanics, not product ownership or Run persistence semantics.
18. Filesystem execution roots use names such as `workdir`, `workspace_path`, or `sandbox_root` rather than overloading product Workspace identity.
19. Duplicate legacy concepts MAY be deleted once their callers are converted; compatibility aliases are not required.

## Acceptance criteria

- Workspace records contain no primary-owner field;
- one Workspace can have two owner memberships;
- the last owner cannot be removed or downgraded without another owner already present;
- user Workspace listing is derived from membership rather than embedded ownership;
- one live Persona can be stored for a Workspace and a second is rejected;
- two Workspaces may each have one live Persona;
- persisted Graphs require a canonical `workspace_id`;
- specialized actors can be added without adding another Persona; and
- a one-node Graph reaches the same Run lifecycle as a multi-node Graph.
