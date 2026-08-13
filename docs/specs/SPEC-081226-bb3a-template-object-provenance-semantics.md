# SPEC-081226-bb3a: Template, Object and Provenance Semantics

- **Status:** Active
- **Date:** 2026-08-12
- **ADR:** `ADR-081226-bb3a`
- **Technical Area:** Reusable definitions, workspace objects, provenance, versioning

## Purpose

Define executable semantics for `NodeTemplate -> Node` and `GraphTemplate -> Graph` so reusable MAIstro definitions are versioned and reproducible while instantiated Workspace objects remain independently editable.

## Canonical model

```text
Workspace
├── NodeTemplate[]
│   └── immutable Version[]
├── GraphTemplate[]
│   └── immutable Version[]
├── Node/Graph mutable objects
└── Persona[]
    └── template catalog visibility/references
```

Instantiation:

```text
NodeTemplate@version  --copy + provenance--> Node
GraphTemplate@version --copy + provenance--> Graph
```

## Required identifiers and provenance

A canonical template version MUST expose enough information to identify a stable snapshot:

```text
template_id
version
content_hash
```

A canonical instantiated object MUST retain at least:

```text
source_template_id
source_template_version
source_template_hash
```

An implementation MAY use a structured `TemplateProvenance` value rather than separate columns as long as these semantics are available.

## Requirements

### R1. Stable logical template identity

A template MUST have a stable `template_id` across its versions.

Creating a materially changed reusable definition under the same logical template MUST create a new version rather than overwrite historical version content.

### R2. Immutable historical versions

After a template version is published/persisted as an addressable version, its effective content MUST be immutable.

Metadata that does not alter semantic content MAY be appended where storage design requires it, but changing effective content MUST produce a new version/content hash.

### R3. NodeTemplate instantiation

Instantiating `NodeTemplate@V` MUST:

1. create a new Node identity;
2. copy/materialize the effective Node definition from exactly version `V`;
3. persist source template ID/version/hash;
4. attach the Node to the target Workspace/Graph context;
5. leave future Node edits independent from the template.

### R4. GraphTemplate instantiation

Instantiating `GraphTemplate@V` MUST:

1. create a new Graph identity;
2. create/materialize its Nodes and Edges from exactly version `V`;
3. persist Graph source template ID/version/hash;
4. preserve useful per-Node source provenance where the GraphTemplate originated those Nodes from NodeTemplates;
5. ensure future Graph/Node edits are independent from the template.

### R5. No floating nested template meaning

A persisted GraphTemplate version MUST NOT semantically depend on an unversioned/latest NodeTemplate reference.

Nested NodeTemplate dependencies MUST be represented by exact version references or by embedded effective snapshots.

### R6. Template update isolation

Publishing `NodeTemplate@V+1` or `GraphTemplate@V+1` MUST NOT mutate any Node/Graph instantiated from `V`.

No background migration may alter existing instances solely because a source template has a newer version.

### R7. Object mutation

A Node or Graph instantiated from a template MAY be edited without creating a template version.

Editing the object MUST retain original source provenance.

The implementation SHOULD expose whether the current object content differs from its source snapshot, using content comparison/hash where practical.

### R8. Save as new template

Saving a Node or Graph as a new template MUST create a new template identity with an initial immutable version and provenance back to the source object.

The source object MUST remain unchanged by the save operation.

### R9. Publish as new version

Publishing a Node or Graph as a new version of an existing template MUST:

1. require authorization for that template;
2. create a new immutable version under the existing template ID;
3. record provenance to the source object and prior template lineage as applicable;
4. leave prior versions and prior instances unchanged.

### R10. Persona catalogs

Persona template catalogs MUST reference templates available in its Workspace/product context rather than copy live template state into Persona.

Adding/removing a template from a Persona catalog changes availability/visibility only. It MUST NOT mutate the template or instantiated Nodes/Graphs.

### R11. Global/enterprise templates

If global/enterprise templates are supported, their scope MUST be explicit.

Instantiating a global/enterprise template into a Workspace MUST still copy/materialize the selected version and persist provenance. Workspace objects MUST NOT become mutable children of global definitions.

### R12. Runtime-state exclusion

Canonical NodeTemplate and GraphTemplate persisted semantic content MUST NOT contain mutable live execution fields including Run/NodeRun/Attempt identifiers, terminal state, retry counters or runtime cancellation/deadline state.

Defaults/policies that influence future execution MAY be stored as definition data.

### R13. Legacy adapter provenance

When an existing definition format is imported/projected into a canonical template, the canonical template MUST retain source-format provenance sufficient to identify the original type/source/version where available.

Adapters MUST NOT pretend an execution-time AgentSpec/Task record is a reusable template without first separating runtime fields.

### R14. Improvement/promotion

An improvement produced by RSI/Evolve/learning MUST be represented as a candidate object/template version before it becomes an active reusable version.

Promotion MUST be explicit and auditable according to applicable policy. Historical template versions and existing instantiated objects remain unchanged.

## Acceptance Criteria

### AC1. Node independence

Given `NodeTemplate T@1`, instantiate Node `N`, edit `N`, and verify `T@1` is byte/semantically unchanged and `N.source_template_*` still identifies `T@1`.

### AC2. Template update isolation

Given Nodes `N1` and `N2` instantiated from `T@1`, publish `T@2`, and verify both existing Nodes remain unchanged until an explicit update operation is invoked.

### AC3. New instantiation selects exact version

Instantiate one Node from `T@1` and another from `T@2`; verify each materializes the corresponding definition and carries the correct version/hash provenance.

### AC4. Graph independence

Instantiate Graph `G` from `GraphTemplate GT@1`, mutate one Node and one Edge in `G`, and verify `GT@1` remains unchanged.

### AC5. Nested version pinning

Publish a GraphTemplate that uses a NodeTemplate. Update the NodeTemplate afterward. Re-instantiating the existing GraphTemplate version MUST produce the same effective graph definition as before the NodeTemplate update.

### AC6. Save Node as template

Save a customized Node as a new NodeTemplate. Verify a new template identity/version is created, provenance identifies the source Node, and the Node itself is unchanged.

### AC7. Publish new version

Publish a customized Node/Graph as a new version of an existing template. Verify the old version remains addressable and unchanged.

### AC8. Persona availability is non-mutating

Add/remove a template from a Persona catalog. Verify template content and existing instantiated objects are unchanged.

### AC9. Runtime field rejection

Canonical template validation rejects or strips into a non-template projection any live Run/NodeRun/Attempt state supplied as reusable semantic content.

### AC10. Legacy definition migration

At least one existing reusable agent definition and one existing graph/workflow definition can be projected/imported into canonical NodeTemplate/GraphTemplate representations with source provenance preserved.

### AC11. RSI/Evolve candidate behavior

An improvement path can produce a candidate template version without mutating the currently published version. Promotion creates a new explicit version only after the configured policy gate.

### AC12. Reproducibility after restart

Persist a template version and an instantiated object, restart/reload persistence, and verify both the immutable template snapshot and object source provenance resolve identically.

## Migration guidance

Initial adapters should prioritize the highest-overlap reusable-definition families:

1. AgentIdentity / agent YAML / AgentCard projections
2. graph configs and recipes
3. PM fleet definitions
4. Builders workers/stages/workflows
5. imported agent/skill formats
6. domain-specific design/Canvas templates where they map cleanly

Do not delay canonical semantics until every legacy format is migrated. Introduce adapters and migrate consumers incrementally.

## Non-goals

This specification does not define:

- NodeType registry behavior;
- Run/NodeRun/Attempt lifecycle;
- exact permission intersection algorithm;
- a generic registry implementation;
- physical package renames;
- automatic three-way template-to-instance merge UX;
- mandatory global template marketplace behavior.

## References

- `ADR-081226-bb3a`
- `ADR-081226-9944`
- `docs/analysis/ECOSYSTEM-INVENTORY.md`
- `docs/analysis/ARCHITECTURE-CONVERGENCE-MATRIX.md`
