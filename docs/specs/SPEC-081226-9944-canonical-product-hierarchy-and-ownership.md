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

1. `Workspace` is the durable product environment. Existing `Project` identity
   remains its compatibility persistence identity during migration.
2. `WorkspaceMembership` is the User-to-Workspace relationship and supports many
   users per Workspace and many Workspaces per user.
3. Canonical Workspace roles are `member`, `contributor`, and `owner`.
4. Member operates existing workflows/templates but does not edit shared
   Graph/Node/Template definitions.
5. Contributor includes member behavior and may create/edit shared
   Graph/Node/Template definitions.
6. Owner includes contributor behavior and additionally changes the Workspace
   Persona, membership/roles, and Workspace-wide configuration.
7. Normal Workspace-to-live-Persona cardinality is 1:1. Canonical persistence
   rejects a second live Persona for the same Workspace.
8. Temporary zero-Persona state is allowed only for bounded onboarding,
   migration, deletion, or replacement transitions.
9. Specialized executable actors are Agents/Nodes rather than additional
   Personas.
10. A one-node Graph is valid and uses the same canonical Run path as any other
    Graph.
11. Manual, scheduled, delegated, Builders, RSI, Evolve and specialized-package
    execution converges on Workspace-owned Run/NodeRun/Attempt state.
12. Session remains continuity across Runs; Schedule remains trigger metadata.
13. ExecutionRuntime owns execution mechanics, not product ownership or Run
    persistence semantics.
14. Filesystem execution roots use names such as `workdir`, `workspace_path`, or
    `sandbox_root` rather than overloading product Workspace identity.

## Compatibility mapping

- legacy Project primary owner -> Workspace `owner`
- legacy Project editor -> Workspace `contributor`
- legacy Project viewer -> Workspace `member`
- legacy `project_id` -> canonical Workspace identity

Compatibility mapping must not create another durable Workspace root.

## Acceptance criteria

- canonical and legacy IDs resolve to the same Workspace;
- membership role projection matches the mapping above;
- one live Persona can be stored for a Workspace and a second is rejected;
- two Workspaces may each have one live Persona;
- specialized actors can be added without adding another Persona;
- a one-node Graph reaches the same Run lifecycle as a multi-node Graph; and
- migrated execution paths retain Workspace attribution across persistence.
