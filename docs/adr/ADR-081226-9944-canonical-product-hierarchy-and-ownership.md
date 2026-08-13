# ADR-081226-9944: Canonical Product Hierarchy and Ownership

- **Status:** Accepted
- **Date:** 2026-08-12
- **Deciders:** MAIstro maintainers
- **Technical Area:** Domain architecture, ownership, execution boundaries

## Context

MAIstro has accumulated strong capabilities across `maistro-core`, Hive, server, Builders, Canvas, Design, Turing, RSI, Evolve, scheduling, durable graphs, task execution, A2A, sessions, memory, credentials, security and integrations. The ecosystem inventory shows that many of these systems are individually useful but overlap in lifecycle ownership, naming, persistence and product entry paths.

The convergence program needs one product hierarchy that can connect these systems without flattening legitimate domain packages or introducing another parallel runtime.

The architectural spine is:

```text
Workspace -> Run -> ExecutionRuntime -> Capabilities
```

The ecosystem audit adds the product and execution structure around that spine:

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
    └── other workspace-scoped resources
```

Fulfillment uses a separate relationship:

```text
Capability -> Provider -> Binding -> Invocation
```

The inventory also confirms that some current names are overloaded. In particular, `workspace` can mean either the product ownership boundary or a filesystem directory. Existing `Project` / `project_id` semantics overlap with the product Workspace concept. Several packages also contain private execution lifecycle concepts that must eventually converge on Run rather than remain competing roots.

## Decision

### 1. Workspace is the durable product ownership root

A **Workspace** is the canonical product/domain ownership boundary beneath a User.

Every durable product object must either:

1. be directly owned/scoped by a Workspace; or
2. have an explicit compatibility or global-scope reason for not being Workspace-owned.

Workspace owns or scopes at least:

- Persona
- Graph and Node objects
- Runs, NodeRuns and Attempts
- Sessions
- Artifacts
- Memory
- Credentials
- Schedules
- Integrations
- Policies
- NodeTemplates and GraphTemplates

Existing Project storage and `project_id` semantics will migrate through compatibility adapters. This ADR does not require a blind database-column rename.

### 2. Product Workspace and filesystem work directory are distinct concepts

`Workspace` means the product ownership object.

Filesystem execution roots must use unambiguous names such as:

- `workdir`
- `workspace_path`
- `sandbox_root`

Compatibility fields may remain temporarily, but new APIs and domain objects must not introduce an ambiguous `workspace` string/path where a Workspace identity is expected.

### 3. Persona is a Workspace-owned product context

A **Persona** describes the purpose, defaults, surfaces, templates, policy ceiling and available bindings through which a user works in a Workspace.

Persona does not execute work and does not own a separate execution lifecycle.

Persona can expose product surfaces such as UI, Builders CLI or Builders RSI while all of those surfaces operate on the same underlying Workspace objects and Runs.

Detailed Persona field semantics are specified separately.

### 4. Templates and mutable objects are distinct

Reusable definitions and editable Workspace objects are distinct categories:

```text
NodeTemplate  -> instantiate -> Node
GraphTemplate -> instantiate -> Graph
```

Instantiation produces an independent object with source provenance. Template/object versioning and provenance semantics are defined by a dedicated ADR.

### 5. Graph and Node are the universal composition objects

A **Graph** is an editable composition of Nodes and Edges. A one-node Graph is valid.

A **Node** is the universal executable position within a Graph. Different NodeTypes do not create different top-level execution lifecycle classes.

### 6. Run is the universal logical execution root

A **Run** represents one logical execution regardless of whether it originated from:

- a manual UI action
- a single agent
- a multi-agent graph
- a scheduled trigger
- Builders
- RSI
- Evolve
- a tool-oriented workflow
- delegation from another Run

A Run contains logical NodeRuns. A NodeRun contains one or more physical Attempts.

```text
Run
└── NodeRun[]
    └── Attempt[]
```

Detailed lifecycle states, persistence and transition rules are defined by a dedicated Run/NodeRun/Attempt ADR.

### 7. Session and Schedule remain distinct from Run

A **Session** owns conversation/collaboration continuity and may span multiple Runs.

A **Schedule** owns trigger/cadence metadata. When it fires, it creates or resumes a canonical Run. A scheduler must not become a competing execution lifecycle authority.

### 8. ExecutionRuntime owns mechanics, not product semantics

`ExecutionRuntime` owns execution mechanics such as bounded concurrency, cancellation propagation, deadlines, backpressure, process supervision, event sequencing mechanics and runtime metrics.

It does not own:

- Workspace ownership
- graph traversal meaning
- permission semantics
- business lifecycle policy
- retry eligibility policy
- delegation policy
- Run persistence semantics

Python domain code remains authoritative for product semantics.

### 9. Capability fulfillment is separate from product ownership

Nodes consume authorized capability bindings. Fulfillment is modeled as:

```text
Capability -> Provider -> Binding -> Invocation
```

This hierarchy does not replace Workspace/Graph/Run ownership. It describes how authorized work is fulfilled.

### 10. Specialized packages extend the hierarchy instead of replacing it

Canvas, Design, Turing, Builders, RSI, Evolve, Hive and future product/domain packages may provide:

- Personas and surfaces
- NodeTypes
- NodeTemplates and GraphTemplates
- capabilities/providers/bindings
- policies
- domain assets and metadata

They must not introduce a second universal product root or a second universal execution lifecycle.

Package names and physical moves are not dictated by this ADR. Package ownership and dependency direction are handled by a separate ADR after semantic mapping is complete.

### 11. Existing global and enterprise scopes are not deleted for symmetry

Legacy organization/team/global concepts may remain where they represent real infrastructure or enterprise boundaries. They must map explicitly around the User/Workspace/Persona product hierarchy rather than being deleted solely to reduce noun count.

## Consequences

### Positive

- Gives every product capability a common ownership root.
- Establishes one execution identity that schedules, agents, graphs, Builders, RSI, Evolve and delegation can share.
- Lets specialized packages remain specialized without becoming architectural islands.
- Separates continuity (Session), triggering (Schedule), execution (Run) and fulfillment (Capability/Binding).
- Makes Workspace-centric UI, auditing, observability, permissions and recovery structurally possible.
- Provides a stable target for eliminating implemented-but-unreachable subsystems.

### Negative

- Existing Project, Task, GraphRun, A2A, Builders and package-specific lifecycle APIs require compatibility adapters during migration.
- Some current fields named `workspace`, `run`, `task` or `session` will need semantic cleanup.
- Durable persistence cannot be normalized safely in one change; migrations must proceed behind parity tests.

### Neutral

- This decision does not require a package rename.
- This decision does not prescribe a storage engine.
- This decision does not make every domain asset a Graph or Node.
- This decision does not collapse Session, Schedule, Artifact, Credential, Permission or Policy into Run.

## Alternatives Considered

### Keep package-specific lifecycle models and connect them through adapters indefinitely

Rejected as the end state. It preserves the current duplication in cancellation, retries, recovery, events and ownership and makes cross-product inspection unreliable.

### Make GraphRun the universal root

Rejected. Graph traversal state is important but is not universal execution lifecycle. Graph-specific state belongs beside/inside a canonical Run rather than defining all execution.

### Make Task the universal root

Rejected. Current Task concepts combine ingress/work request, queue/scheduling information and execution state. These responsibilities need separation.

### Force all specialized packages into `maistro-core`

Rejected. Convergence is semantic, not a package-count reduction exercise. Specialized product/domain behavior remains outside core when that boundary is useful.

## Compliance

Architecture changes comply with this ADR when:

- every new durable product object declares its Workspace ownership/scope;
- new product APIs resolve Workspace context before creating durable workload state;
- a subsystem does not introduce another universal Run lifecycle;
- a NodeType implementation does not become the owner of Run persistence;
- a scheduler creates/resumes Runs instead of executing workload under a private lifecycle;
- filesystem paths are not confused with product Workspace identity;
- Session remains continuity rather than execution identity;
- specialized packages map execution onto canonical Run/NodeRun/Attempt semantics;
- capability fulfillment uses explicit authorization/binding boundaries rather than bypassing product ownership and policy.

Enforcement begins with specifications and compatibility tests, then graduates into architecture fitness checks as migrations land.

## References

- `docs/analysis/ECOSYSTEM-INVENTORY.md`
- `docs/analysis/ARCHITECTURE-CONVERGENCE-MATRIX.md`
- `docs/analysis/EXECUTION-RUNTIME-SEAM-MAP.md`
- `docs/analysis/PACKAGE-OWNERSHIP-DECISIONS.md`
- `ADR-062026-9b30`: Date-based ADR/SPEC identifiers
