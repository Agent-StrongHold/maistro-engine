# ADR-081226-e626: Persona and Surface Model

- **Status:** Accepted
- **Date:** 2026-08-12
- **Updated:** 2026-08-13
- **Deciders:** MAIstro maintainers
- **Technical Area:** Product context, surfaces, defaults, reusable catalogs

## Context

MAIstro has several product surfaces and specialized packages. The first
convergence draft allowed multiple live Personas inside one Workspace. Product
review rejected that shape: the Workspace is the durable environment/body of
work, and its Persona is the single coherent description of how MAIstro behaves
in that environment. Specialized actors are Agents, not extra Personas.

## Decision

### Workspace and live Persona are 1:1

Normal canonical state is:

```text
Workspace 1 ----- 1 Persona
```

A Workspace may temporarily have no Persona during onboarding or migration, but
canonical persistence must not allow two live Personas with the same
`workspace_id`. There is no active-Persona selector on Workspace.

### Persona is the Workspace product context

The live Persona contains identity/name, purpose/description/theme,
`workspace_id`, allowed surfaces, NodeTemplate and GraphTemplate catalog
references, defaults, binding/capability availability, and namespaced extension
metadata.

Persona does not own membership or execution state.

### Persona is not Agent

Persona describes how MAIstro behaves in one Workspace. Agent is the executable
actor/definition used inside Graph execution. Specialized actors, supervisors,
critics, writers, coders and similar roles are represented by Agents/Nodes, not
secondary Personas.

### Persona is not execution

Persona never owns a Run lifecycle. Product surfaces create/edit canonical
objects and launch canonical Runs. A Run initiated through a Workspace should
retain `persona_id` provenance and the effective configuration snapshot needed
for reproducibility.

### Persona is changed at Workspace-owner scope

Workspace access is modeled separately through WorkspaceMembership. Members and
contributors operate through the Persona, while owner-level Workspace authority
is required to change the Persona because those changes affect the whole
Workspace environment.

### Surfaces, catalogs and defaults

Surfaces are named interaction modes such as UI, API, Builders CLI or Builders
RSI. Persona catalogs reference canonical templates rather than copying them.
Changing Persona defaults affects future object creation and does not silently
mutate existing Nodes, Graphs or active Runs.

### Specialized packages extend the one Persona

Builders, Canvas, Design, Turing and future packages may contribute surfaces,
templates, bindings and namespaced Persona metadata. They do not create another
live Persona merely to represent a specialized actor or tool.

## Consequences

- Each Workspace has one coherent behavior/configuration point.
- Agent remains the abstraction for specialized executable actors.
- There is no multi-Persona switching model to synchronize.
- Existing multi-Persona assumptions require migration.
- Specialized product packages keep their UX without creating separate runtimes.

## Compliance

An implementation complies when every live Persona belongs to one Workspace,
canonical persistence prevents a second live Persona for that Workspace, Persona
contains no Run lifecycle, template catalogs remain references, and product
surfaces operate on the same canonical Workspace objects and Runs.

## References

- `ADR-081226-9944`
- `ADR-081226-bb3a`
- `ADR-081226-6e34`
