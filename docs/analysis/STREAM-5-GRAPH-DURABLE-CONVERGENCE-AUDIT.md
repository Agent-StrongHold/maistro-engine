# Stream 5: Graph + Durable Execution Convergence Audit

Status: pre-implementation audit against `develop`

## Purpose

Stream 5 converges the existing in-memory `GraphRun` path and durable DAG execution path behind the canonical execution spine without discarding behavior from either implementation.

The target shape is:

```text
Run
+ GraphExecutionState
+ NodeRun
+ Attempt
        ↓
ExecutionRuntime
        ↓
Checkpoint / Event persistence
```

`Run` owns universal lifecycle. `GraphExecutionState` owns graph-specific traversal state. `NodeRun` owns logical node execution. `Attempt` owns one physical execution try. `ExecutionRuntime` owns mechanics only.

This audit intentionally does not introduce canonical Run/NodeRun/Attempt models ahead of Stream 1.

## Readiness

### Hard blocker

Stream 1 must establish a stable canonical `Run -> NodeRun -> Attempt` contract, including terminalization/reconciliation and the `Attempt -> ExecutionRuntime` seam.

Stream 5 must not migrate production durable execution before that contract exists. The current durable executor can persist `RUNNING`; wrapping its coroutine with runtime cancellation before canonical reconciliation exists risks leaving persistence in a false non-terminal state.

### Required before final convergence

Stream 2 checkpoint/resume contracts must be stable before the durable pause/resume path is switched to the canonical spine.

### Not blockers to audit/parity work

- Stream 3 authorization
- Stream 4 reachability audit
- Stream 6 capability execution
- Stream 7 product adapters

## Current execution systems

### `GraphRun`

Primary implementation: `packages/maistro-core/src/maistro/graph/run.py`.

It currently owns both graph semantics and execution lifecycle:

- graph phase transitions
- graph-local cancellation flag
- active-node traversal
- conditional edge evaluation
- sequential plus parallel outgoing edges
- concurrent execution of the active set with `asyncio.gather`
- cycle counting / max-cycle termination
- blackboard and pipeline state
- node-run creation
- graph completion/failure events
- result assembly

Its routing helper can return one sequential target plus any number of parallel targets whose conditions evaluate true.

### Durable DAG executor

Primary implementation: `packages/maistro-core/src/maistro/graph/durable_runs/executor.py`.

It currently provides:

- persisted `DurableRunRecord`
- persisted `DurableNodeRecord`
- optimistic versioning
- checkpoint-after-node semantics
- persisted pause/wait
- persisted HITL pause/resume
- durable blackboard snapshot
- halt requests
- synth-depth/recursion tracking
- step-budget protection
- resume entrypoint

However, it owns a second execution lifecycle and a second graph traversal algorithm.

## Confirmed semantic mismatches

### 1. Conditional routing is not equivalent

`GraphRun` evaluates supported edge expressions using the current plan/code/review state and only follows matching edges.

The durable `_next_node` does not evaluate the edge condition. If all outgoing edges are conditional, it selects the first one.

Therefore durable execution cannot currently claim behavioral parity for conditional graphs.

### 2. Parallel traversal is not equivalent

`GraphRun` maintains an `active` set and executes all active nodes concurrently. Routing can produce multiple next nodes, including explicit parallel edges.

The durable model persists one `current_node_id` and walks one node at a time.

This is not merely an implementation detail. Fan-out/fan-in semantics, scheduling order, failure behavior, checkpoint shape, and blackboard merge behavior can differ.

### 3. Retry/attempt meaning is duplicated

`DurableNodeRecord.attempts` increments when the node is entered again, including resume behavior. Existing non-durable `NodeRun` also owns retry behavior.

Canonical `Attempt` must become the physical try record. Stream 5 must not preserve `attempts` as another competing lifecycle counter once Stream 1 lands.

### 4. Cancellation/terminalization is inconsistent

`GraphRun` catches `asyncio.CancelledError`, moves through `CANCELLING`, cancels active node runs, then records the graph as `FAILED`.

Durable records define a distinct `CANCELLED` state, but the durable walk has no canonical transaction/reconciliation boundary tying coroutine interruption to persisted terminal state.

The migration must preserve resumability while ensuring runtime cancellation cannot leave a run persisted as `RUNNING`.

### 5. Pause/resume exists only on the durable path

Durable execution can checkpoint node state and return with `PAUSED_WAIT` or `PAUSED_HITL`, later rebuilding `NodeContext` and resuming.

`GraphRun` does not expose equivalent persisted pause/resume behavior.

This behavior must survive convergence and become canonical Run/NodeRun/Checkpoint behavior rather than being deleted.

### 6. Durable graph state is broader than a cursor

The current durable record persists:

- DAG snapshot
- current node cursor
- ordered node records
- blackboard snapshot
- HITL answers
- resume time
- optimistic version
- lifecycle timestamps
- failure detail

After convergence, graph-specific portions belong in `GraphExecutionState`; universal lifecycle portions belong in canonical `Run`, `NodeRun`, `Attempt`, Event, and Checkpoint records.

### 7. Blackboard/input semantics need parity coverage

`GraphRun` maintains typed plan/code/review state plus `GraphBlackboard` and derives routing from those values.

Durable execution reconstructs a blackboard snapshot and passes the most recent completed upstream output forward by default. This is a different dataflow rule from the in-memory graph semantics and needs explicit expected behavior before migration.

### 8. Graph-specific safety behavior must be preserved

The durable executor includes behavior not present as equivalent generic Run semantics:

- `halt_requested` handling
- synth-depth increment rules
- `StepBudgetExhausted`
- optimistic concurrency protection

These should not be accidentally flattened into generic Runtime mechanics. They are graph/domain policy or persistence concerns.

## Target ownership split

### Canonical `Run`

Owns:

- workspace/project scope IDs as defined by Stream 1
- universal run status
- parent/child run relation
- lifecycle timestamps
- terminal result/error
- reconciliation from child NodeRuns

Does not own graph traversal algorithms.

### `GraphExecutionState`

Owns:

- immutable graph snapshot/reference needed for reproducible execution
- active/pending graph positions
- traversal frontier
- cycle / step accounting
- edge decisions
- graph-local blackboard state
- fan-out/fan-in bookkeeping
- graph-specific halt state
- graph-specific recursion/synth-depth state when retained

A single `current_node_id` is insufficient for canonical parallel graphs. The durable representation must support a persisted frontier/active set.

### Canonical `NodeRun`

Owns one logical execution of one graph Node within a Run, including waiting/paused state and logical result.

### Canonical `Attempt`

Owns one physical try:

- runtime/executor selection
- retry ordinal
- start/finish
- deadline/cancellation
- physical error/result
- resource/runtime metrics
- checkpoint/resume source

### `ExecutionRuntime`

Owns mechanics only:

- bounded concurrency
- cancellation propagation
- deadlines
- event sequencing mechanics
- backpressure
- process supervision
- runtime metrics

It must not decide graph routing, retry policy, Run status semantics, or checkpoint meaning.

## Parity suite required before deleting either path

The convergence PR must establish behavioral tests for at least the following.

### Traversal

1. linear graph follows the same node order
2. conditional true branch selects the same target
3. conditional false branch does not execute the rejected target
4. multiple conditional branches have deterministic documented selection semantics
5. explicit parallel edges fan out to all selected targets
6. fan-in waits according to the canonical dependency rule
7. graph with no outgoing edge completes normally
8. cycling graph respects the canonical graph budget and never reports partial completion as success

### Node outcomes

9. node success persists one logical NodeRun
10. node failure reconciles NodeRun and Run correctly
11. retry creates multiple Attempts under one NodeRun
12. retry exhaustion produces one logical failed NodeRun, not duplicate logical runs

### Cancellation/deadline

13. cancellation terminalizes the active Attempt
14. NodeRun reconciles from the cancelled Attempt
15. Run reconciles to canonical cancellation semantics
16. persisted state is never left `RUNNING` after acknowledged cancellation
17. a resumable checkpoint remains usable when policy allows resume
18. deadline expiration has distinct canonical semantics from arbitrary failure

### Pause/resume/HITL

19. wait node persists a resumable checkpoint
20. HITL node persists a resumable checkpoint and request metadata
21. resume continues the same Run and NodeRun
22. resume creates a new Attempt when physical execution restarts
23. completed upstream nodes are not re-executed during normal resume
24. optimistic concurrency prevents double-resume

### State/dataflow

25. blackboard mutations survive checkpoint/resume
26. edge predicates see equivalent canonical state before and after resume
27. fan-out branch outputs merge according to an explicit deterministic rule
28. graph snapshot/provenance survives later graph-definition mutation

### Existing durable safety behavior

29. halt request terminates according to canonical graph policy
30. recursion/synth-depth guard is preserved where still required
31. step-budget exhaustion is failure, never completion

## Migration sequence once Stream 1 lands

1. Add `GraphExecutionState` representation compatible with a persisted frontier rather than a single cursor.
2. Add adapters from legacy `GraphRun` state and `DurableRunRecord` into the canonical Run/GraphExecutionState model.
3. Route physical node execution through canonical `Attempt -> ExecutionRuntime`.
4. Preserve legacy graph traversal semantics behind parity tests.
5. Add durable fan-out/fan-in and real condition evaluation.
6. Map durable pauses to canonical waiting NodeRun + Checkpoint.
7. Map resume to a new Attempt on the existing NodeRun.
8. Reconcile cancellation/deadline through canonical terminalization before returning control.
9. Switch production durable callers only after parity coverage is green.
10. Remove duplicate durable lifecycle enums/fields only after all callers and persisted compatibility paths have migration coverage.

## Immediate implementation boundary

Until Stream 1 lands, Stream 5 may safely add documentation and parity fixtures that describe current behavior, but it should not introduce a third temporary Run lifecycle or invent placeholder canonical Attempt APIs.

The first code-bearing Stream 5 PR after the blocker clears should be narrow: canonical graph state + parity tests, not an all-at-once rewrite of the durable executor.
