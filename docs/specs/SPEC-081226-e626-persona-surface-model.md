# SPEC-081226-e626: Persona and Surface Model

- **Status:** Active
- **Date:** 2026-08-12
- **ADR:** `ADR-081226-e626`

## Required Persona shape

Canonical Persona MUST expose or resolve:

```text
persona_id
workspace_id
name
purpose/description?
theme/metadata?
allowed_surfaces[]
node_template_catalog[]
graph_template_catalog[]
permission_ceiling
policy_defaults
binding_availability[]
model/provider defaults?
created_at/updated_at
```

Domain packages MAY attach namespaced extension metadata without redefining Persona lifecycle.

## Requirements

1. Workspace MUST support more than one Persona.
2. Persona MUST have exactly one owning Workspace unless explicitly defined as a platform/global template-like Persona in a future ADR; current user Personas are Workspace-owned.
3. Selecting/using a Persona MUST be request/session/surface context, not a single global Workspace lock preventing concurrent Personas.
4. Persona MUST NOT own execution status, retry, cancellation or checkpoint state.
5. Launching work through a Persona MUST create/use canonical Graph/Node/Run services.
6. Run SHOULD retain `persona_id` provenance when a Persona initiated/configured the work.
7. Persona template catalogs MUST reference canonical template identities/versions/visibility; catalog membership MUST NOT mutate template content.
8. Persona permission ceiling MUST be a subset of Workspace effective permission.
9. Persona Binding availability MUST NOT expose a Binding disallowed by Workspace/User permission.
10. Surface availability MUST be checked at the product/API layer but MUST NOT replace Invocation permission checks.
11. Changing Persona defaults MUST NOT mutate already-instantiated Nodes/Graphs or active Runs.
12. Model/provider defaults MUST resolve through canonical Model/Provider/Binding policy, not direct provider calls from UI.
13. Specialized package Personas MAY add surfaces/templates/domain metadata but MUST use the canonical execution lifecycle.

## Acceptance Criteria

1. Create two Personas in one Workspace and use them concurrently without changing a Workspace-wide active-persona field.
2. Each Persona exposes a distinct template catalog while both reference shared canonical templates without copying content.
3. A Persona cannot add a Binding permission absent from Workspace authority.
4. Disabling a Builders CLI surface prevents that surface from operating under the Persona while UI/API security still uses canonical permission checks.
5. Launching a Graph from Persona A creates a Run correlated to the same Workspace and records Persona A provenance.
6. Editing Persona A defaults after Run start does not alter the Run's effective snapshot.
7. Persona B can launch the same Graph/template with different allowed defaults/bindings and produces its own Run provenance.
8. Builders mapping proves UI/CLI/RSI surfaces operate on the same underlying Graph/Run records.
9. A Canvas/Book Builder mapping can reference Canvas-specific templates/bindings while book-domain objects remain Canvas-owned.
10. Turing persona-level defaults can be represented without requiring Turing runtime to own a separate Run status model.

## Non-goals

This SPEC does not prescribe Persona UI design, require every Workspace to have multiple Personas, or make all agent personality/self-model data Persona-level.
