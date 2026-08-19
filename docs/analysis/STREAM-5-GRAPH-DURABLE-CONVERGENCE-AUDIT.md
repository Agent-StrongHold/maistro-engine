# Stream 5: Graph + Durable Execution Convergence Audit

Status: pre-implementation audit against `develop`

## Purpose

Stream 5 converges the existing in-memory `GraphRun` path, durable DAG execution path, and live Hive graph execution path behind the canonical execution spine without discarding behavior that is intentionally valuable.

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

### Live Hive executor

Production implementation: `packages/hive-conductor/backend/services/graph_runner.py`, called by mounted product routes and chat tooling.

Verified live callers include:

- `POST /v1/dags/{dag_id}/run` in `packages/hive-conductor/backend/routes/dags.py`, which calls `services.graph_runner.execute_dag(..., execution_mode="interactive")`
- chat `_tool_run_workflow()`, which also calls the private Hive executor and then reconstructs product-level node/run status from its result

The live Hive path does not use core `GraphRun`/`run_graph()` or durable execution. It currently owns useful execution mechanics that must be preserved where appropriate:

- topological ready-wave traversal
- safe in-process versus sandboxed subprocess isolation tiers
- default-to-sandbox behavior
- autonomous isolation floor
- private LLM/tool/subprocess/credential dispatch

It also contains lifecycle/routing defects that must not be preserved as parity:

- edge conditions are ignored and reduced to inbound dependency sets
- a ready wave is traversal-complete even when a node result has `success=False`
- top-level execution can return `status="completed"` after node failures
- deadlock/no-ready-with-unfinished-nodes can fall through to completed
- the regular path does not enforce DAG `max_cycles`

The alternate `execute_dag_streaming()` path attempts core `run_graph()` but has drifted out of signature compatibility: it passes a string task plus `config=` and `blackboard=` arguments that the current core `run_graph()` entrypoint does not accept.

The chat adapter adds another correctness problem: it projects each returned node as completed without checking node success, constructs an evaluation view with `phase="completed"` and no errors, and returns a top-level completed status. Failed execution can therefore be rewritten as success by the product adapter.

## Confirmed semantic mismatches

### 1. Conditional routing is not equivalent

`GraphRun` evaluates supported edge expressions using the current plan/code/review state and only follows matching edges.

The durable `_next_node` does not evaluate the edge condition. If all outgoing edges are conditional, it selects the first one.

The live Hive executor also does not evaluate edge conditions; it reduces edges to dependency relationships.

Therefore neither durable execution nor the mounted Hive production path can currently claim behavioral parity for conditional graphs.

### 2. Parallel traversal is not equivalent

`GraphRun` maintains an `active` set and executes all active nodes concurrently. Routing can produce multiple next nodes, including explicit parallel edges.

The durable model persists one `current_node_id` and walks one node at a time.

The live Hive executor operates in topological ready waves, which is closer to a persisted frontier model than the durable cursor, but its failure and routing semantics differ from `GraphRun`.

This is not merely an implementation detail. Fan-out/fan-in semantics, scheduling order, failure behavior, checkpoint shape, and blackboard merge behavior can differ.

### 3. Retry/attempt meaning is duplicated

`DurableNodeRecord.attempts` increments when the node is entered again, including resume behavior. Existing non-durable `NodeRun` also owns retry behavior.

Canonical `Attempt` must become the physical try record. Stream 5 must not preserve `attempts` as another competing lifecycle counter once Stream 1 lands.

### 4. Cancellation/terminalization is inconsistent

`GraphRun` catches `asyncio.CancelledError`, moves through `CANCELLING`, cancels active node runs, then records the graph as `FAILED`.

Durable records define a distinct `CANCELLED` state, but the durable walk has no canonical transaction/reconciliation boundary tying coroutine interruption to persisted terminal state.

The live Hive path has its own product result/status reconstruction and therefore cannot be trusted as the universal lifecycle authority.

The migration must preserve resumability while ensuring runtime cancellation cannot leave a run persisted as `RUNNING`.

### 5. Pause/resume exists only on the durable path

Durable execution can checkpoint node state and return with `PAUSED_WAIT` or `PAUSED_HITL`, later rebuilding `NodeContext` and resuming.

`GraphRun` and live Hive execution do not expose equivalent persisted pause/resume behavior.

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

The live Hive ready-wave executor has its own dependency/result assembly path, so canonical fan-out/fan-in merge semantics must be defined instead of inheriting whichever executor happens to run.

### 8. Graph-specific safety behavior must be preserved

The durable executor includes behavior not present as equivalent generic Run semantics:

- `halt_requested` handling
- synth-depth increment rules
- `StepBudgetExhausted`
- optimistic concurrency protection

The live Hive path includes execution isolation behavior that is likewise valuable but belongs below graph semantics:

- sandbox-versus-in-process selection
- default-to-sandbox behavior
- autonomous isolation floor

These should not be accidentally flattened into generic graph traversal. Durable safety rules remain graph/domain or persistence concerns; Hive isolation mechanics should converge beneath canonical `Attempt -> ExecutionRuntime`/capability execution rather than remain a separate Run lifecycle.

### 9. Failure authority is inconsistent on the live product path

The mounted Hive executor and chat adapter can report top-level completion after node-level failure. This is not behavior to preserve.

Canonical `NodeRun` and `Run` reconciliation must become authoritative. Product adapters may project canonical state, but they must not synthesize successful lifecycle state independently.

### 10. Production reachability includes more than the mounted DAG route

Migration scope must include both the mounted DAG route and chat workflow tool. Switching only `/v1/dags/{id}/run` would leave a second live caller on the private Hive lifecycle.

The alternate streaming path must either be repaired as an adapter to the canonical entrypoint or removed if unreachable; its current call signature is stale.

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

A single `current_node_id` is insufficient for canonical parallel graphs. The durable representation must support a persisted frontier/active set. The live Hive ready-wave representation is useful evidence for this shape, but not a lifecycle authority.

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

### Hive product adapters

Mounted routes and chat tools should:

- submit execution through the canonical graph Run entrypoint
- read authoritative canonical Run/NodeRun state
- preserve necessary isolation/configuration inputs
- project status/events for UI/chat without inventing lifecycle state

They should not retain a private graph Run state machine.

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
9. deadlock/no-ready-with-unfinished-nodes fails rather than reports completion

### Node outcomes

10. node success persists one logical NodeRun
11. node failure reconciles NodeRun and Run correctly
12. retry creates multiple Attempts under one NodeRun
13. retry exhaustion produces one logical failed NodeRun, not duplicate logical runs
14. product adapters cannot rewrite failed NodeRuns as completed
15. top-level Run cannot report completed when any required NodeRun failed under the canonical graph policy

### Cancellation/deadline

16. cancellation terminalizes the active Attempt
17. NodeRun reconciles from the cancelled Attempt
18. Run reconciles to canonical cancellation semantics
19. persisted state is never left `RUNNING` after acknowledged cancellation
20. a resumable checkpoint remains usable when policy allows resume
21. deadline expiration has distinct canonical semantics from arbitrary failure

### Pause/resume/HITL

22. wait node persists a resumable checkpoint
23. HITL node persists a resumable checkpoint and request metadata
24. resume continues the same Run and NodeRun
25. resume creates a new Attempt when physical execution restarts
26. completed upstream nodes are not re-executed during normal resume
27. optimistic concurrency prevents double-resume

### State/dataflow

28. blackboard mutations survive checkpoint/resume
29. edge predicates see equivalent canonical state before and after resume
30. fan-out branch outputs merge according to an explicit deterministic rule
31. graph snapshot/provenance survives later graph-definition mutation

### Existing durable safety behavior

32. halt request terminates according to canonical graph policy
33. recursion/synth-depth guard is preserved where still required
34. step-budget exhaustion is failure, never completion

### Existing Hive execution mechanics

35. safe nodes may retain the intended in-process execution path
36. sandbox-required nodes retain sandbox execution
37. default-to-sandbox behavior is preserved where policy requires it
38. autonomous isolation floor is preserved
39. route and chat callers observe the same authoritative Run/NodeRun state
40. streaming execution, if retained, calls the same canonical execution entrypoint contract

## Migration sequence once Stream 1 lands

1. Add `GraphExecutionState` representation compatible with a persisted frontier rather than a single cursor.
2. Add adapters from legacy `GraphRun`, `DurableRunRecord`, and the live Hive ready-wave state into the canonical Run/GraphExecutionState model where state migration is required.
3. Route physical node execution through canonical `Attempt -> ExecutionRuntime`.
4. Preserve legacy graph traversal semantics behind parity tests where they are correct.
5. Add durable fan-out/fan-in and real condition evaluation.
6. Map durable pauses to canonical waiting NodeRun + Checkpoint.
7. Map resume to a new Attempt on the existing NodeRun.
8. Reconcile cancellation/deadline through canonical terminalization before returning control.
9. Preserve Hive isolation mechanics beneath the canonical execution seam rather than its private lifecycle.
10. Migrate both `POST /v1/dags/{id}/run` and chat `_tool_run_workflow()` to the authoritative canonical entrypoint together.
11. Repair or remove the stale `execute_dag_streaming()` adapter.
12. Switch production durable callers only after parity coverage is green.
13. Remove duplicate durable/Hive lifecycle enums, result reconstruction, and fields only after all callers and persisted compatibility paths have migration coverage.

## Immediate implementation boundary

Until Stream 1 lands, Stream 5 may safely add documentation and parity fixtures that describe current behavior, but it should not introduce a third temporary Run lifecycle or invent placeholder canonical Attempt APIs.

The first code-bearing Stream 5 PR after the blocker clears should be narrow: canonical graph state + parity tests, not an all-at-once rewrite of the durable executor.
