# ADR-081226-e626: Persona and Surface Model

- **Status:** Accepted
- **Date:** 2026-08-12
- **Deciders:** MAIstro maintainers
- **Technical Area:** Product context, surfaces, defaults, reusable catalogs

## Context

MAIstro exposes several ways of working: general UI/API, Builders, Builders CLI/RSI, Turing-oriented behavior, Canvas/book building and other specialized product experiences. Today these surfaces often carry their own defaults, agent definitions, tool sets and orchestration assumptions. Persona provides product context without creating another runtime.

## Decision

### Persona is a Workspace-owned product context

A Workspace MAY contain multiple Personas. Personas can be used concurrently; there is no single mutable Workspace-wide "active persona" required by the domain model.

A Persona contains at least:

- stable identity/name
- purpose/description/theme
- `workspace_id`
- allowed surfaces
- NodeTemplate catalog references
- GraphTemplate catalog references
- permission ceiling
- policy defaults
- available Binding/capability references
- optional model/provider defaults
- product/domain extension metadata where appropriate

### Persona is not Agent

Persona describes how a user/product surface operates in a Workspace. Agent is a NodeType/definition used inside Graph execution. One Persona may expose many Agent NodeTemplates and GraphTemplates.

### Persona is not execution

Persona never owns a Run lifecycle. A surface operating through a Persona creates/edits canonical objects and launches canonical Runs.

A Run launched through a Persona SHOULD record `persona_id` as provenance/context and snapshot effective execution configuration needed for reproducibility.

### Surface is an interface capability

A Surface is a named interaction mode such as web UI, API, Builders CLI or Builders RSI. Surface availability controls what product operations are offered through a Persona. Surface checks do not replace canonical permission enforcement.

The surface registry is extensible so specialized packages can add interfaces without adding execution ontologies.

### Persona catalogs reference templates

Persona template catalogs reference available NodeTemplates/GraphTemplates. They do not copy or mutate template content. Workspace/global template scope and template provenance remain governed by template semantics.

### Defaults are non-retroactive

Changing Persona model/provider/prompt/policy defaults does not silently mutate existing Nodes, Graphs or in-flight Runs. Defaults are applied when creating/instantiating new objects or explicitly reapplying configuration.

### Permissions only narrow

Persona permission ceiling is a child of Workspace permission. Persona defaults/Bindings cannot widen Workspace/User authority.

### Specialized packages map to Persona

Examples:

- Builders Persona: Builders UI/CLI/RSI surfaces, Frank/Mason/Auditor templates and workflow GraphTemplates.
- Book Builder Persona: Canvas/book UI, image/compositor/export bindings and book workflow templates.
- Turing: persona-level identity/personality defaults may extend Persona; agent-specific cognition/self-model state remains Agent/Node-domain data where appropriate.

Package-specific UX/domain assets may remain in their packages.

## Consequences

- Multiple product modes share Workspace/Graph/Run semantics.
- Builders/Canvas/Turing can expose strong UX without private execution roots.
- Persona defaults become auditable provenance rather than hidden surface configuration.
- Existing surface-specific settings need migration/adapters.

## Compliance

A Persona implementation complies when it is Workspace-owned, contains no Run lifecycle, references rather than mutates template catalogs, narrows permissions, treats defaults as future-object defaults, and all enabled surfaces manipulate the same canonical objects/services.

## References

- `ADR-081226-9944`
- `ADR-081226-bb3a`
- `ADR-081226-6e34`
