---
id: SPEC-081226-e626
title: Persona and Product Surface Model
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
  - maistro-engine#ADR-081426-b1d3
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
  - packages/maistro-core/src/maistro/personas
layer: Domain
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-e626: Persona and Product Surface Model

- **Status:** Active
- **Date:** 2026-08-14 revision
- **ADR:** `ADR-081226-e626`

## Requirements

### R1. Cardinality

A Workspace MUST have at most one live Persona record at a time. Persona identity MUST be scoped to one Workspace.

### R2. Purpose, taste, and style

Persona MUST support explicit representation of purpose and configurable taste/style guidance. Implementations MAY structure these as typed fields, text guidance, or extensible settings, but the stored model MUST be able to express all three concerns distinctly.

### R3. Behavioral and creation defaults

Persona MAY define defaults used when creating new Workspace/Project objects or resolving ordinary behavior. These defaults are preference/configuration inputs and become ordinary object-owned configuration when applied at creation time.

### R4. Preferences

Persona MAY name preferred models, providers, capabilities, Bindings, prompts, parameters, or templates. A preference MUST NOT imply that the preferred resource is authorized or visible in the current Project.

### R5. Product surfaces

Persona MAY configure relevant product surfaces such as `ui`, `builders_cli`, and `builders_rsi`. Surface configuration controls product experience/exposure, not security authority.

### R6. No authorization semantics

Persona MUST NOT contain or compute:

- permission ceilings,
- security grants,
- explicit denies,
- Project membership,
- credential visibility,
- privilege elevation,
- authority widening or narrowing.

Authorization services MUST be able to resolve Principal authority without consulting Persona.

### R7. Agent separation

Persona MUST NOT own Run/NodeRun/Attempt state and MUST NOT be treated as an Agent actor. Agent behavior executes through Nodes/Graphs/Runs.

### R8. Project-default interaction

When creation defaults are resolved, Persona defaults MAY be applied after Workspace defaults and before Project ancestry defaults. Project defaults closer to the destination MAY override Persona defaults. Once created, the object owns the resolved configuration.

## Acceptance Criteria

1. A Persona can encode a Workspace purpose independently from its name.
2. A Persona can encode taste/aesthetic and style/voice guidance independently.
3. Persona can configure UI/Builders surfaces without changing the principal's effective permissions.
4. A Persona can prefer Binding A while Project authorization makes only Binding B available; A remains unavailable.
5. Persona data has no `permission_ceiling`, grants, denies, or credential-scope field.
6. Authorization resolution produces the same result when Persona style/taste/purpose/preferences change.
7. Persona creation defaults participate in new-object resolution but later Persona changes do not mutate existing objects.
8. Exactly one live Persona per Workspace is enforced by the Persona store/service.
9. Persona remains definition/configuration only and contains no Run/Attempt lifecycle state.

## Non-goals

This SPEC does not define Project authorization, Agent identity, Provider fallback, or the visual design of Persona-editing UI.
