# ADR-081226-69ee: Graph and Node Execution Model

- **Status:** Accepted
- **Date:** 2026-08-12
- **Deciders:** MAIstro maintainers
- **Technical Area:** Graph composition, node execution, traversal

## Context

MAIstro has GraphRun, durable graph execution, DAG builders, PM graphs, Builders workflows and package-specific orchestration. Useful traversal semantics are mixed with universal execution lifecycle and runtime mechanics. The convergence model needs Graph/Node to be universal composition objects without making every NodeType its own Run type.

## Decision

### Graph is the universal composition object

A Graph is a Workspace-scoped editable object containing Nodes and Edges. A one-node Graph is valid and uses the same execution path as larger graphs.

A Run executes an immutable effective Graph snapshot/reference. Editing the Workspace Graph after a Run starts MUST NOT silently alter that Run.

### Node is the universal executable position

A Node contains definition/configuration, not live execution state:

```text
Node
├── NodeType
├── Parameters
├── Bindings
├── Permissions
├── Policies
├── Inputs
└── Outputs
```

NodeType determines type-specific behavior. Initial canonical categories include agent, api, capability/tool, harness, human/HITL, evaluation, transform, control/router and subgraph. The registry is extensible; package-specific NodeTypes are allowed when they obey canonical lifecycle and permission boundaries.

### Node execution creates NodeRun/Attempt

When traversal selects a Node, the Run creates a NodeRun. Physical execution occurs through Attempt and ExecutionRuntime. NodeType implementations do not own Run persistence.

### GraphExecutionState is separate from Run lifecycle

Existing GraphRun semantics are decomposed into:

```text
Run + GraphExecutionState
```

GraphExecutionState owns graph-specific facts such as traversal frontier, active/selected nodes, edge decisions, blackboard/dataflow state, cycle state and graph-specific checkpoints. Run owns universal lifecycle, correlation and terminal state.

### Traversal is domain logic

The graph executor/domain layer decides:

- dependency satisfaction
- conditional edge predicates
- fanout/fanin meaning
- cycle/loop semantics
- which Nodes become ready
- graph completion/failure rules
- blackboard/dataflow updates

ExecutionRuntime only provides mechanics such as concurrency slots, cancellation, deadlines and process supervision.

### Edges express composition/routing semantics

Edges connect Nodes and may carry predicates/routing metadata. Learned weights/trust/staleness may remain graph-domain metadata where useful. Runtime mechanics do not interpret business predicates.

### Subgraph execution

A subgraph Node references an exact Graph/GraphTemplate-derived executable snapshot. The default canonical execution is a child Run correlated to the parent NodeRun so nested work retains independent history, cancellation and inspection. Implementations may optimize internal representation later only if observable lifecycle semantics remain equivalent.

### Durable graph convergence

DurableRunRecord becomes persistence/projection for canonical Run plus GraphExecutionState; DurableNodeRecord maps to NodeRun persistence. Existing optimistic versioning, graph snapshots, checkpoints and pause/resume behavior are preserved.

No old graph path is deleted until parity tests cover conditional routing, fanout/fanin, cycles where supported, retries, pause/resume, cancellation and recovery.

## Consequences

- Single-agent/single-node execution no longer needs a separate ontology.
- Graph edits cannot mutate in-flight Runs.
- Durable graph state remains useful without competing with Run.
- NodeTypes can grow without multiplying lifecycle models.
- Graph traversal and runtime mechanics become testable independently.

## Compliance

A graph execution path complies when it executes a stable graph snapshot, creates canonical NodeRuns/Attempts, keeps traversal in domain code, keeps Runtime free of graph semantics, and persists graph-specific state separately from universal Run lifecycle.

## References

- `ADR-081226-9944`
- `ADR-081226-a66b`
- `docs/analysis/EXECUTION-RUNTIME-SEAM-MAP.md`
