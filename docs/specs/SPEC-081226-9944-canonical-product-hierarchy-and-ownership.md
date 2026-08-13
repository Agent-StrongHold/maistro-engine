# SPEC-081226-9944: Canonical Product Hierarchy and Ownership

- **Status:** Active
- **Date:** 2026-08-12
- **ADR:** `ADR-081226-9944`
- **Technical Area:** Domain architecture, ownership, execution boundaries

## Purpose

This specification makes the canonical MAIstro product hierarchy testable. It defines the observable requirements for converging existing Project, graph, task, schedule, session and specialized-package behavior onto the Workspace-centered product model without requiring an immediate destructive migration.

## Canonical relationships

```text
User
└── Workspace[]
    ├── Persona[]
    ├── Graph[]
    │   ├── Node[]
    │   └── Edge[]
    ├── Run[]
    │   └── NodeRun[]
    │       └── Attempt[]
    ├── Session[]
    ├── Artifact[]
    ├── Schedule[]
    ├── Memory
    ├── Credentials
    ├── Integrations
    ├── Policies
    ├── NodeTemplate[]
    └── GraphTemplate[]
```

Fulfillment is orthogonal:

```text
Capability -> Provider -> Binding -> Invocation
```

## Definitions

### Workspace

Durable product ownership boundary. A Workspace is identified by a stable `workspace_id` or a compatibility-resolved existing Project identifier during migration.

### Persona

Workspace-owned product context containing purpose/defaults/surface availability/template visibility and policy/binding ceilings. Persona does not execute.

### Graph

Editable composition of Nodes and Edges. A Graph containing exactly one Node is valid.

### Node

Universal executable position in a Graph. NodeType controls type-specific configuration/behavior without creating a separate top-level lifecycle.

### Run

One logical execution record.

### NodeRun

Logical execution of one Node within a Run.

### Attempt

One physical execution attempt for a NodeRun.

### Session

Conversation/collaboration continuity that may reference multiple Runs.

### Schedule

Trigger/cadence configuration that creates or resumes a Run when fired.

## Requirements

### R1. Workspace identity

Every newly introduced durable product-domain object MUST have one of:

1. a `workspace_id`; or
2. an explicit documented global/enterprise scope; or
3. a temporary compatibility resolver that deterministically maps its current owner identifier to a Workspace.

A plain filesystem path does not satisfy Workspace ownership.

### R2. Project compatibility

Existing Project/project_id-backed data MUST remain resolvable during Workspace migration.

The migration MUST NOT require destructive renaming of all stored columns before the canonical Workspace API can be introduced.

A compatibility layer MUST be capable of resolving a legacy Project identifier to the canonical Workspace identity used by new services.

### R3. Filesystem terminology

New domain/API fields MUST NOT use `workspace` to mean a filesystem path when the product Workspace object is in scope.

New filesystem-root fields SHOULD use `workdir`, `workspace_path`, `sandbox_root` or a more specific name.

Existing ambiguous fields MAY remain behind adapters until their callers migrate.

### R4. Persona ownership

A persisted Persona MUST identify its owning Workspace.

Deleting, moving or cloning a Persona MUST follow Workspace authorization rules once hierarchical permissions are implemented.

Persona MUST NOT own execution lifecycle state equivalent to RunStatus.

### R5. Graph ownership

A persisted Graph MUST be Workspace-scoped.

A Graph MUST support one Node without requiring a special single-agent execution model.

A Node MUST be owned through its Graph or otherwise explicitly Workspace-scoped during editing/template workflows.

### R6. Run ownership

Every canonical Run MUST resolve to exactly one Workspace.

A child Run MUST inherit or explicitly narrow its Workspace context. Cross-Workspace delegation is not implicitly allowed by parentage and will require explicit permission/binding policy.

Run, NodeRun and Attempt lifecycle semantics are specified by their dedicated lifecycle ADR/SPEC.

### R7. Session relationship

A Session MUST remain distinct from Run.

A Session MAY reference zero, one or many Runs over its lifetime.

Ending a Run MUST NOT require ending the Session.

### R8. Schedule relationship

Firing a Schedule MUST produce a canonical Run or resume an explicitly resumable canonical Run according to policy.

A Schedule executor MUST NOT maintain an independent terminal workload truth after the Run has been created.

Historical scheduler execution records MAY remain as compatibility projections that reference the canonical Run.

### R9. Specialized package integration

When Canvas, Design, Turing, Builders, RSI, Evolve, Hive or another specialized package executes user workload, the product entry path MUST resolve to a canonical Workspace and ultimately a canonical Run.

Package-specific objects MAY preserve domain state but MUST NOT become alternative universal ownership/execution roots.

### R10. Runtime boundary

ExecutionRuntime MUST accept execution context supplied by the domain layer and MUST NOT become the persistence owner for Workspace, Graph or Run domain semantics.

Runtime mechanics MAY emit correlated runtime events/metrics and control Attempt mechanics.

### R11. Capability relationship

A Node that uses an external or executable capability MUST eventually resolve fulfillment through an authorized Binding/Provider/Invocation path.

This requirement does not force all current integrations to migrate in this specification; it establishes the ownership relationship they must converge toward.

### R12. Global/enterprise scopes

Existing organization/team/global scopes MUST NOT be silently deleted.

Any object intentionally outside Workspace scope MUST document why and how Workspace-scoped product execution references it safely.

## Compatibility requirements

During migration:

- legacy Project IDs remain accepted where currently public;
- legacy Task/GraphRun/scheduler identifiers may remain as aliases or projections;
- compatibility objects must point toward canonical ownership rather than create new competing lifecycle truth;
- adapters must be removable after callers migrate;
- migration tests must prove old durable records remain readable and attributable.

## Acceptance Criteria

The hierarchy/ownership migration is considered implemented only when all applicable criteria below are true on real product paths.

### AC1. Legacy Project to Workspace resolution

Given an existing durable record containing a legacy `project_id`, the canonical Workspace service resolves it to the same logical owner without data loss.

### AC2. Workspace-scoped creation

Creating a new Graph, Persona, Run, Session, Schedule or Artifact through canonical services requires/resolves Workspace context and persists that relationship.

### AC3. Single-node Graph

A Graph with exactly one Node can be saved and executed through the same Graph -> Run entry path as a multi-node Graph.

### AC4. Manual execution creates Run

Starting executable work through the canonical manual/API surface creates a Workspace-owned Run rather than only a Task/GraphRun/package-specific lifecycle record.

### AC5. Schedule creates Run

A schedule trigger creates a Workspace-owned Run and its externally visible execution status is derived from that Run after admission.

### AC6. Session spans Runs

A single Session can create/reference at least two Runs while retaining the same Session identity and Workspace scope.

### AC7. Specialized package path

At least one specialized product path, initially whichever migration lands first, proves:

```text
product surface -> Workspace -> Graph/Node -> Run
```

without creating a new universal lifecycle record.

### AC8. Filesystem/workspace ambiguity regression test

Tests distinguish product `workspace_id` from filesystem execution roots. Supplying a filesystem path where a Workspace identity is required is rejected or handled only through an explicit compatibility adapter.

### AC9. Ownership survives restart

Workspace attribution for persisted Runs and other migrated durable objects remains resolvable after process restart.

### AC10. No new competing lifecycle

Architecture fitness/static checks, once introduced, reject a newly added subsystem-level universal Run lifecycle enum/model unless it is an explicitly documented compatibility projection.

## Migration sequence

1. Introduce canonical Workspace identity/service and Project compatibility adapter.
2. Add Workspace ownership to Persona and new template/object models.
3. Normalize Graph/Node ownership.
4. Introduce canonical Run/NodeRun/Attempt persistence.
5. Redirect manual execution and schedules to canonical Runs.
6. Redirect specialized package execution paths one at a time.
7. Add architecture fitness checks.
8. Remove legacy ownership/lifecycle adapters only after behavioral parity and reachability tests pass.

## Non-goals

This specification does not yet define:

- exact Persona persisted schema;
- template version/promotion semantics;
- Run state machine and legal transitions;
- graph traversal semantics;
- permission intersection algorithm;
- event/checkpoint envelope;
- provider-selection timing;
- physical package renames/moves;
- storage-engine replacement.

Those are handled by subsequent architecture convergence ADR/SPEC pairs.

## Evidence and tests to add during implementation

- Project -> Workspace compatibility tests
- Workspace ownership persistence tests
- one-node Graph execution test
- manual API -> Run test
- Schedule -> Run test
- Session -> multiple Runs test
- product/specialized package -> canonical Run integration test
- restart/readback ownership test
- architecture fitness test preventing new competing lifecycle roots

## References

- `ADR-081226-9944`
- `docs/analysis/ECOSYSTEM-INVENTORY.md`
- `docs/analysis/ARCHITECTURE-CONVERGENCE-MATRIX.md`
- `docs/analysis/PACKAGE-OWNERSHIP-DECISIONS.md`
