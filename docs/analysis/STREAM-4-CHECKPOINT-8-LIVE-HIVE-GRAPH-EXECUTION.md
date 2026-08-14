# Stream 4 Checkpoint 8: Live Hive Graph Execution

Date: 2026-08-14
Source audited: `develop`

This checkpoint traces the production-mounted Hive DAG and DAG-run surfaces to their actual execution implementations. It materially changes the Stream 5 migration priority because the live UI path is not the core GraphRun/durable path.

## 1. `/v1/dags` is a live, product-owned graph model

Hive `routes/dags.py` is mounted by the production app and defines its own DAG DTOs:

- DAGFile
- DAGNode
- DAGEdge
- draft/active/archived status
- nodes/edges/entry/max_cycles/run_scout
- edit-lock behavior
- audit events

The product model is real UI/API behavior and should be treated as a graph authoring projection/template source during canonical migration.

## 2. Normal UI run path uses a third executor

`POST /v1/dags/{dag_id}/run` calls:

`services.graph_runner.execute_dag(dag_data, execution_mode="interactive")`

It does not call:

- `GraphRun` directly
- core `run_graph()`
- durable run executor

Therefore there are at least three materially different graph execution implementations relevant to convergence:

1. core `GraphRun` / `run_graph`
2. core durable executor
3. live Hive `services.graph_runner.execute_dag`

Builders adds a fourth specialized private graph executor, but it is currently unreachable.

### Stream 5 priority implication

The Hive executor is the live product path, so convergence cannot be considered complete merely by merging GraphRun and durable-run internals. `/v1/dags/{id}/run` must be moved to the canonical path as an explicit production-entry migration.

## 3. Hive execute_dag has useful execution-isolation behavior

The live executor contains behavior worth preserving:

- dependency-ready wave execution
- concurrent safe/in-process nodes
- process isolation for risky nodes
- execution-tier classification
- default-to-sandbox behavior for unconfigured nodes
- block untrusted nodes without explicit admin approval
- stronger isolation floor for autonomous vs interactive mode
- explicit per-user node environment
- provider stub fail-closed behavior unless operator opts in
- usage callback seam

These are not reasons to retain the private lifecycle. They are migration requirements for canonical Node/Attempt/ExecutionRuntime.

### Stream 1 / 5 / 6 handoff

ExecutionRuntime/capability invocation must preserve the isolation-tier intent currently implemented here.

## 4. Hive execute_dag does not preserve canonical graph-routing semantics

The live executor builds only inbound dependency sets from edges.

It does not evaluate edge conditions when selecting the next ready wave. Every node becomes ready once all inbound source nodes are marked completed.

This differs from core GraphRun's conditional-routing behavior.

It also marks every ready node as completed in the traversal bookkeeping after the wave, including nodes whose result reports failure.

Classification: live traversal semantics are incomplete relative to canonical target.

## 5. Top-level success is currently unreliable

`execute_dag()` returns:

`{"status": "completed", "cycles": ..., "node_results": ...}`

once the traversal loop exits.

Individual node results may contain `success=False`, but the top-level status remains `completed` unless an exception escapes the executor.

Additionally, if no node is ready while unfinished nodes remain, the loop breaks and still returns top-level completed.

The regular executor does not use DAG `max_cycles` to bound the while loop.

### Stream 5 acceptance requirement

Canonical migration should distinguish at least:

- graph completed successfully
- graph completed with product-level negative result, if such a concept is desired
- node failure causing run failure
- deadlock/unreachable/cyclic graph
- cancellation
- timeout/deadline

Do not preserve current top-level `completed` behavior as parity merely because clients consume it today.

## 6. Live `/v1/dag-runs` owns a synthetic in-memory run projection

Hive `routes/dag_runs.py` exposes:

- list recent runs
- run detail
- SSE event stream

through `services.dag_run_store.DagRunStore`.

The store owns:

- in-memory run records
- ring-buffer retention
- buffered events
- per-run SSE subscribers
- synthetic node-state reconstruction

It is not the canonical Run persistence layer.

Classification: `live UI projection; replace backing source`.

## 7. DAG-run correlation can fragment real executions

The pm-runner event bridge accepts an optional `current_run_id_provider`, but Hive startup installs it without one.

When no run ID is available, every incoming pm event creates a new ephemeral DagRun before appending that event.

Therefore the current store cannot reliably guarantee that a UI DagRun corresponds one-to-one with a real execution.

### Stream 2 / Stream 5 handoff

Canonical Run ID and Event correlation should become the backing identity for this UI. SSE can remain as a transport/projection over canonical persisted events.

## 8. `run_dag` writes fields the DagRun model does not serialize

The route obtains a `DagRun` and then assigns:

- `run.status = "completed"`
- `run.result = result`

The `DagRun` dataclass defines neither field, and its `to_summary()` / `to_detail()` do not serialize them.

Python permits those dynamic attributes, but the UI store does not expose them through its normal serializers.

The route also does not call the store's `finish_run()` after execution.

This is evidence that the DagRun store is a demo/projection artifact, not a trustworthy lifecycle source.

## 9. Streaming and non-streaming execution paths use different architectures

`execute_dag()` is the private Hive executor.

`execute_dag_streaming()` attempts to use core `maistro.graph.executor.run_graph()`.

So even within one service module, normal and streaming execution have different routing/execution implementations.

That is a convergence smell and creates behavioral drift risk.

## 10. The streaming core bridge has already drifted out of interface compatibility

Current Hive `execute_dag_streaming()` calls core `run_graph()` with:

- `task=` as a string
- `config=`
- `blackboard=`
- `llm_call=`

Current core `run_graph()` signature accepts:

- `task: GraphTask`
- `llm_call`
- model/retry/timeout/etc. keyword options

and does not accept `config` or `blackboard` keyword arguments.

This bridge is therefore incompatible with the current core API if invoked.

### Migration direction

Do not spend convergence time repairing this old bridge as a separate public contract unless a live caller requires an immediate hotfix. Move the streaming product surface directly onto the canonical production execution entrypoint.

## 11. User credentials are injected directly into node process environments

The live Hive executor accepts a `user_credentials` dict and writes values into environment variables named `USER_CRED_<KEY>` for node subprocesses.

This is another reason the executor migration intersects Stream 6.

### Stream 6 handoff

Canonical Invocation/Credential resolution should decide exactly which credential is exposed to which Capability/Provider/Attempt and materialize it at the ExecutionRuntime seam. Avoid passing broad arbitrary credential dictionaries through graph execution.

## 12. Hive graph_runner also contains its own provider/tool invocation layer

The service directly implements:

- LiteLLM HTTP calls
- subprocess LiteLLM calls
- web search tool dispatch
- clarify tool dispatch
- browse URL tool dispatch
- generic tool registry calls
- sandbox/process execution

These overlap Stream 6 Capability/Provider/Binding/Invocation ownership.

### Migration split

Preserve product/runtime behavior:

- isolation classification
- fail-closed degraded mode
- result/error shaping required by UI

Move universal capability mechanics:

- provider selection/call
- credential exposure
- tool dispatch
- Invocation correlation
- usage attribution

into canonical Stream 6 contracts.

## Updated canonical execution migration map

### Live production spine today

`Hive /v1/dags/{id}/run`
-> Hive DAGFile
-> Hive `execute_dag`
-> private ready-wave traversal
-> private LLM/tool/subprocess dispatch
-> synthetic DagRunStore events

### Canonical target

`Hive DAG authoring projection`
-> canonical Graph/GraphTemplate
-> canonical Run
-> GraphExecutionState
-> NodeRun
-> Attempt
-> Binding/Provider/Invocation
-> ExecutionRuntime
-> canonical Event/Checkpoint
-> Hive list/detail/SSE projections

## Immediate handoffs

### Stream 1

Production execution entrypoint must become the owner of Run/Attempt/ExecutionRuntime rather than Hive graph_runner.

### Stream 2

Replace synthetic DagRun event storage/correlation with canonical Event persistence and sequence IDs; retain SSE projection behavior.

### Stream 5

Add live Hive `execute_dag` to the parity/convergence matrix. Preserve isolation hooks but replace routing/lifecycle. Fix conditions, failure semantics, cycles/deadlock, cancellation, and project/run identity through canonical execution.

### Stream 6

Extract LLM/tool/credential/subprocess invocation from Hive graph_runner into canonical capability execution.

### Stream 7

Preserve DAG authoring/edit-lock/audit/UI behavior while replacing the execution backend and DagRunStore backing source.

## Priority

This should be considered a high-priority convergence seam because it is reachable from the production product API today, unlike several better-designed durable/runtime implementations that remain unreachable.
