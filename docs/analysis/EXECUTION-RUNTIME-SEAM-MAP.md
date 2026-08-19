# Execution Runtime Seam Map

Status: implementation guide for issue #373 and the post-Eigent consolidation program.

## Objective

MAIstro's product spine is:

```text
Workspace -> Run -> ExecutionRuntime -> Capabilities
```

Python remains authoritative for workspace, run, graph, agent, tool, persistence,
policy, and user-facing semantics. `ExecutionRuntime` owns only replaceable
execution mechanics:

- bounded concurrency and slot acquisition
- cancellation propagation
- deadline enforcement
- event sequencing
- backpressure primitives
- runtime health and migration-trigger measurements

The runtime must not decide what a graph edge means, how a run transitions, what
a tool is allowed to do, or how domain state is persisted.

## Current seam map

| Surface | Current execution/state owner | Existing good seam | Runtime bypass / duplication | Convergence action |
| --- | --- | --- | --- | --- |
| Graph, legacy | `maistro.graph.run.GraphRun` | `NodeExecutor` overrides and graph events | Own in-memory graph lifecycle, cancellation, retry, fan-out, callbacks | Preserve domain traversal. Run its mechanics through `ExecutionRuntime`; retire duplicated mechanics only after behavior parity. |
| Graph, durable | `maistro.graph.durable_runs.executor` + `DurableRunStore` | Checkpoint after steps; pause/resume; persisted run/version state | Separate traversal semantics from `GraphRun`; caller owns resume scheduling | Treat as the persistence candidate for canonical Run attempts. Inject runtime mechanics around walks without moving graph meaning into runtime. |
| Hive graph | `backend/services/graph_runner.py` + `dag_run_store.py` | Streaming path already reaches maistro-core | Custom execution path remains beside core execution | Route product entry points to one core graph adapter, then remove the parallel Hive traversal after parity tests. |
| Scheduler | `backend/services/scheduler.py` | Persistent schedule metadata/audit | Trigger bookkeeping does not own/create a canonical Run | A schedule must call a Run launcher. The launcher creates a Run, then invokes the runtime-backed executor. Scheduler never executes domain work directly. |
| Delegation | `maistro.a2a.delegate.A2ADelegator` | `agent.delegate_remote` already maps remote work to durable pause/resume | `A2ATask` has an independent in-memory task lifecycle | Preserve dispatch/trust logic; migrate delegated work identity to parent/child Runs. The delegation node waits on child-run completion. |
| Harness | `HarnessSessionManager` + `HarnessNodeExecutor` | Graph `NodeExecutor` adapter is already clean and policy-gated | Session mechanics are separate, but do not need a new domain lifecycle | Keep the adapter. Runtime bounds/cancels the node execution outside it; harness manager continues to own harness-session protocol. |
| Task worker | `maistro.tasks.runner.TaskRunner` + `TaskQueue` | Injected `TaskExecutor`; lane admission is explicit | Queue task status is another execution lifecycle; lane gate overlaps runtime concurrency mechanics | Keep queue/admission as ingress until Run adoption. Convert dequeued task -> Run. Move generic execution slots to runtime only when lane semantics can be preserved explicitly. |
| Recovery | `maistro.tasks.recovery` + durable-run executor/store | Crash-loop and version-compatibility policy is reusable | `tasks.recovery` does not resume persisted execution; durable resume is graph-specific | Recovery policy decides eligibility. Canonical Run persistence identifies the attempt/checkpoint. Runtime performs mechanics; domain adapter performs resume. |
| RSI | `backend/services/rsi.py` | Explicit cancellation/status concepts | Own in-memory run state and task ownership | Replace RSI-local run identity with canonical Run. RSI service becomes a workload producer/domain adapter. |
| Evolve | `backend/services/evolution.py` | `EvolutionCycle` is already a clear workload unit | Private 300-second asyncio loop calls cycles directly, outside Run/runtime/scheduler | Represent a cycle as a scheduled Run. Scheduler launches it; runtime provides mechanics; evolve keeps population/tournament semantics. |

## Important non-equivalences

### `GraphRun` and durable runs are not interchangeable yet

`GraphRun` supports graph-specific conditional routing, parallel outgoing work,
cycles, graph phases, node retries, and callbacks. The durable executor provides
durable checkpoints, pause/resume, and optimistic versioning, but its traversal
is intentionally simpler in places.

Therefore:

1. do not replace `GraphRun` wholesale with the durable executor;
2. do not encode graph traversal rules inside `ExecutionRuntime`;
3. first put shared mechanics behind the runtime boundary;
4. then consolidate traversal/domain semantics behind parity tests.

### Task lanes are policy, not merely a semaphore

`TaskRunner` reserves capacity for LIVE/BACKGROUND lanes and priority tiers.
`ExecutionRuntime` provides generic bounded concurrency but must not silently
flatten those scheduling semantics. A future adapter may translate lane policy
to runtime slot requests, but the policy remains Python/domain-owned.

### Remote delegation is already modeled as a wait

`agent.delegate_remote` correctly treats delegated work as external work that
pauses and later resumes a durable DAG. Do not invent another wait primitive.
The identity behind that wait should become a child Run instead of an independent
`A2ATask` lifecycle.

## First implementation slice

`maistro.runtime.ExecutionRuntime` is intentionally domain-opaque. The initial
`PythonExecutionRuntime` supplies:

- `execute(compiled_graph, run_context, run_id, executor, timeout_s)`
- `cancel(run_id)`
- monotonic `emit(event)` sequencing
- `acquire_slot` / `release_slot`
- bounded concurrency
- deadline propagation via `asyncio.timeout`
- metrics/health snapshots
- event-loop lag sampling
- process CPU and max-RSS measurements

The injected `executor` remains the owner of graph/run/agent/tool semantics. This
keeps a future `RustExecutionRuntime` substitutable without moving product meaning
across the language boundary.

## Migration order

### 1. Establish runtime mechanics

Land the protocol, Python implementation, tests, metrics, and architecture guard
rails. No production caller is switched in this step.

### 2. Add a durable graph adapter

Create a small adapter whose domain executor calls `run_durable_dag` /
`resume_durable_dag` while `PythonExecutionRuntime` owns concurrency, cancellation,
deadline, and event ordering. Preserve the existing durable store unchanged.

### 3. Introduce canonical Run ownership

Workspace owns Runs. Run persistence owns parent/child identity, attempts,
status, checkpoints, provenance, and event sequence references. Do not make the
runtime repository-aware.

### 4. Route scheduler through Run creation

A schedule creates a Run. Remove scheduler-local notions of execution status
beyond schedule metadata such as last trigger/next trigger.

### 5. Convert delegation to child Runs

Keep A2A routing/trust and remote transport. Replace the independent delegated
execution lifecycle with a parent/child Run relationship and durable wait/resume.

### 6. Route RSI/evolve through Run + scheduler

RSI and evolve become workload/domain adapters. Remove their private background
execution lifecycle only after equivalent cancellation, status, and observability
are available from Run/runtime.

### 7. Reconcile legacy `GraphRun`

Write behavior-parity tests for parallel edges, conditions, cycles, retries,
cancellation, and graph events. Consolidate graph domain execution only after
those tests prove no behavior regression.

### 8. Shrink duplicated task/runtime mechanics

Once queue ingress creates Runs, decide which TaskRunner lane/admission mechanics
remain product scheduling policy and which generic mechanics can delegate to the
runtime.

## Runtime event direction

`ExecutionRuntime.emit()` sequences opaque events. It is not the canonical event
schema. The Run/event workstream defines domain event types and persistence, then
supplies an event sink to the runtime.

This avoids creating a second event model while still making event ordering an
explicit runtime mechanic.

## Rust guard rail

A Rust runtime is not authorized by this abstraction. Migration is considered
only after profiling/load tests show sustained evidence such as:

- runtime/orchestration mechanics consuming roughly 25-30%+ backend CPU;
- event-loop p99 lag above roughly 20-50 ms at target concurrency;
- scheduling overhead above roughly 5% of end-to-end latency for short tasks;
- Python worker/process growth materially outpacing useful throughput;
- graph dispatch/concurrency primitives dominating profiles;
- tens of thousands of simultaneously active nodes/connections making Python
  overhead material;
- demonstrated runtime memory/serialization bottlenecks.

If justified, prefer a small PyO3/maturin execution kernel behind the same
`ExecutionRuntime` interface. Rust owns mechanics; Python owns meaning.

## Exit condition for this workstream

The consolidation is succeeding when product entry points converge on:

```text
Workspace
  -> Run
      -> ExecutionRuntime
          -> domain executor / capability adapters
```

and graph, scheduler, delegation, recovery, RSI/evolve, harness, and task ingress
no longer invent independent execution lifecycles where a Run relationship is the
actual concept.
