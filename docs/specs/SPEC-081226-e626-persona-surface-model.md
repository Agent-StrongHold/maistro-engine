---
id: SPEC-081226-e626
title: Persona and Surface Model
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
  - maistro-engine#ADR-081226-e626
implements:
  - maistro-engine#ADR-081226-e626
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
tests:
  - packages/maistro-core/tests/personas/test_model.py
  - packages/maistro-core/tests/personas/test_store.py
source:
  - packages/maistro-core/src/maistro/personas
layer: UserClient
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-e626: Persona and Surface Model

- **Status:** Active
- **Date:** 2026-08-12
- **Updated:** 2026-08-13
- **ADR:** `ADR-081226-e626`

## Required Persona shape

Canonical Persona must expose or resolve:

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

Domain packages may attach namespaced extension metadata without redefining
Persona lifecycle.

## Requirements

1. A live Persona must have exactly one owning Workspace.
2. Canonical persistence must reject a second live Persona for a Workspace.
3. A Workspace may transiently have zero Personas only during onboarding,
   migration, deletion/replacement, or another explicitly bounded transition.
4. Canonical product flows should converge the Workspace to one live Persona.
5. Workspace must not maintain an active-Persona selector or concurrent live
   Persona collection.
6. Specialized actors are Agents/Nodes, not additional Personas.
7. Persona must not own execution status, retry, cancellation or checkpoint
   state.
8. Launching work through the Persona must create/use canonical Graph/Node/Run
   services.
9. Run should retain `persona_id` provenance when Persona configuration shaped
   the execution.
10. Persona template catalogs reference canonical template identities and must
    not copy/mutate template content.
11. Persona settings may narrow inherited Workspace behavior but cannot widen
    authority available at the Workspace boundary.
12. Workspace owner scope is required to modify Persona configuration; member and
    contributor roles consume the Workspace through that Persona.
13. Surface availability is a product-interface rule and does not replace the
    lower execution authorization checks.
14. Persona default changes are non-retroactive for existing Nodes, Graphs and
    active Runs.
15. Specialized packages may add surfaces/templates/metadata to the one Persona
    while preserving canonical Run lifecycle.

## Acceptance Criteria

1. Creating a Persona for a Workspace succeeds when none exists.
2. Creating a second Persona for that Workspace is rejected.
3. Two different Workspaces may each own one Persona.
4. Deleting/replacing the Persona preserves the one-live-Persona invariant.
5. Updating Persona defaults leaves an already-started Run snapshot unchanged.
6. A specialized actor is represented as Agent/Node configuration while the
   Workspace continues to have only one Persona.
7. Builders UI/CLI/RSI can operate through the same Persona and underlying
   Graph/Run records.
8. Canvas/Turing-specific fields can be represented as namespaced extensions
   without creating secondary live Personas.
9. A member or contributor can operate through the Persona but cannot perform an
   owner-scoped Persona modification.
10. A Run shaped by the Persona remains correlated to the same Workspace and
    records Persona provenance.

## Non-goals

This specification does not make agent personality/self-model data Persona-level,
does not require Persona to own Workspace membership, and does not define a
multi-Persona switching UX.
