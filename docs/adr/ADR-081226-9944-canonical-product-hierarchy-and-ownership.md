# ADR-081226-9944: Canonical Product Hierarchy and Ownership

- **Status:** Accepted
- **Date:** 2026-08-12
- **Updated:** 2026-08-13
- **Deciders:** MAIstro maintainers
- **Technical Area:** Domain architecture, ownership, execution boundaries

## Context

MAIstro has accumulated useful but overlapping ownership and execution concepts
across core, Hive, server, Builders, Canvas, Design, Turing, RSI, Evolve,
scheduling, durable graphs, tasks, sessions, memory, security and integrations.
The convergence program needs one durable product root and one execution root
without flattening legitimate product packages.

The architectural spine remains:

```text
Workspace -> Run -> ExecutionRuntime -> Capabilities
```

Product review clarified two parts of the original hierarchy:

1. user access to a Workspace is a separate many-to-many
   `WorkspaceMembership` relationship; and
2. the normal live Workspace-to-Persona relationship is 1:1, not a collection of
   simultaneously active Personas.

## Decision

### 1. Workspace is the durable product environment and ownership root

A Workspace is the canonical durable environment/body of work. Durable product
objects either resolve to exactly one Workspace or document an intentional
global/enterprise scope.

Workspace owns or scopes at least Graphs/Nodes, Runs, Sessions, Artifacts,
Memory, Credentials, Schedules, Integrations, Policies, Templates and its single
live Persona.

Existing `Project` / `project_id` persistence migrates through compatibility
adapters. This decision does not require a blind database-column rename.

### 2. User access is modeled through WorkspaceMembership

Users and Workspaces are many-to-many:

```text
User[] <-> WorkspaceMembership[] <-> Workspace[]
```

WorkspaceMembership answers who can access/control a Workspace. It is distinct
from Workspace identity and distinct from Persona.

Canonical roles are:

- **member**: use/chat/run existing workflows, instantiate/use templates,
  provide inputs, participate in Sessions/HITL and consume permitted outputs;
  member does not modify shared Graph/Node/Template definitions.
- **contributor**: member rights plus create/modify shared Graphs, Nodes and
  Templates.
- **owner**: contributor rights plus modify the Workspace Persona, manage
  membership/roles, and administer Workspace settings/policy.

Legacy `owner_user_id` plus editor/viewer member storage may remain behind an
adapter until durable membership persistence is normalized.

### 3. Workspace has one live Persona

Normal state is:

```text
Workspace 1 ----- 1 Persona
```

A Workspace may transiently have no Persona during migration/onboarding, but
canonical persistence must not allow two live Personas for one Workspace.
Persona describes how MAIstro behaves in that environment: purpose, defaults,
surfaces, template catalogs, policy ceiling and available bindings.

Specialized actors are Agents/Nodes, not secondary Personas.

### 4. Product Workspace and filesystem work directory are distinct

`Workspace` means the product ownership object. Filesystem execution roots use
unambiguous names such as `workdir`, `workspace_path` or `sandbox_root`.
Compatibility fields may remain temporarily.

### 5. Templates and mutable objects are distinct

```text
NodeTemplate  -> instantiate -> Node
GraphTemplate -> instantiate -> Graph
```

Instantiation produces an independent editable object with source provenance.

### 6. Graph and Node are the universal composition objects

Graph is an editable composition of Nodes and Edges. A one-node Graph is valid.
Node is the universal executable position in a Graph. NodeType supplies
specialized behavior without introducing another top-level lifecycle.

### 7. Run is the universal logical execution root

Manual, agent, graph, scheduled, Builders, RSI, Evolve, tool-oriented and
delegated workload all converge on canonical Run/NodeRun/Attempt semantics:

```text
Run
└── NodeRun[]
    └── Attempt[]
```

### 8. Session and Schedule remain distinct from Run

Session owns conversation/collaboration continuity and may span multiple Runs.
Schedule owns trigger/cadence metadata and creates or resumes a canonical Run.
Neither becomes a competing execution truth.

### 9. ExecutionRuntime owns mechanics, not product semantics

ExecutionRuntime owns bounded concurrency, cancellation propagation, deadlines,
backpressure, process supervision, event sequencing mechanics and runtime
metrics. It does not own Workspace, membership, Persona, graph traversal,
permission policy, retry eligibility or Run persistence semantics.

Python domain code remains authoritative for product semantics.

### 10. Capability fulfillment is separate from ownership

Fulfillment remains:

```text
Capability -> Provider -> Binding -> Invocation
```

This does not replace Workspace/Graph/Run ownership. It describes how authorized
work is fulfilled.

### 11. Specialized packages extend the hierarchy

Canvas, Design, Turing, Builders, RSI, Evolve, Hive and future packages may
provide surfaces, NodeTypes, templates, capabilities/providers/bindings,
policies and domain assets. They must not introduce another universal ownership
root or Run lifecycle.

### 12. Existing global and enterprise scopes are preserved where real

Organization/team/global infrastructure scopes may remain where they represent
real enterprise boundaries. They map explicitly around the Workspace model
rather than being deleted for noun-count symmetry.

## Canonical relationship sketch

```text
User[]
  <-> WorkspaceMembership[]
        <-> Workspace[]
              ├── Persona (1:1 live)
              ├── Graph[]
              │    ├── Node[]
              │    └── Edge[]
              ├── Run[]
              │    └── NodeRun[]
              │         └── Attempt[]
              ├── Session[]
              ├── Artifact[]
              ├── Schedule[]
              └── other Workspace-scoped resources
```

## Consequences

### Positive

- Shared and personal Workspaces use one access model.
- Persona no longer duplicates Agent as a specialization mechanism.
- Workspace has one coherent behavior/configuration point.
- One execution identity can be shared by schedules, graphs, Builders, RSI,
  Evolve and delegation.
- Workspace-centric auditing, recovery and UI become structurally consistent.

### Negative

- Existing Project roles and owner fields need compatibility mapping.
- Existing assumptions about multiple Personas require migration.
- Task/GraphRun/package-specific lifecycle APIs still need adapters.
- Persistence normalization must proceed incrementally behind parity tests.

## Compliance

Architecture changes comply when:

- every new durable product object declares Workspace scope or a documented
  non-Workspace scope;
- Workspace access resolves through WorkspaceMembership semantics;
- canonical roles use member/contributor/owner behavior;
- a Workspace cannot have two live Personas;
- specialized actors are represented as Agents/Nodes instead of extra Personas;
- new execution enters canonical Run semantics;
- schedulers create/resume Runs rather than owning workload truth;
- filesystem paths are not confused with product Workspace identity; and
- specialized packages extend rather than replace the canonical hierarchy.

## References

- `docs/analysis/ECOSYSTEM-INVENTORY.md`
- `docs/analysis/ARCHITECTURE-CONVERGENCE-MATRIX.md`
- `docs/analysis/EXECUTION-RUNTIME-SEAM-MAP.md`
- `docs/analysis/PACKAGE-OWNERSHIP-DECISIONS.md`
- `ADR-081226-e626`
- `ADR-081226-6e34`
