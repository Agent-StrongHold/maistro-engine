# Runtime Seam Map — 2026-08-12

Status: analysis, non-normative

This document turns the primitive-first ontology audit into an implementation-oriented seam map. The ontology is supporting evidence, not the deliverable. The goal is to identify the smallest ownership handoffs that let MAIstro's existing subsystems participate in one coherent product/runtime without rewriting domain mechanics that already work.

The strategic direction remains:

```text
Workspace -> Run -> Runtime -> Capabilities
```

But the runtime should be a lifecycle/identity boundary around specialized execution, not a universal replacement for every domain executor.

## Core stitching rule

For every way work enters MAIstro, trace:

```text
Product/API trigger
    -> request/trigger
    -> ExecutionRuntime creates or loads canonical Run context
    -> specialized adapter keeps domain mechanics
    -> Invocation(s) / child Runs as needed
    -> canonical events, lifecycle, artifacts/checkpoint references
    -> workspace-visible Run history
```

The thing to consolidate is duplicated **identity and lifecycle ownership**. The thing to preserve is specialized **domain execution mechanics**.

## Runtime contract already present on this branch

`maistro.runtime` currently carries `WorkspaceRef`, `RunContext`, and `ExecutionContext`, including workspace ownership, run/root/parent identity, actor, correlation, lifecycle state, and metadata. `ExecutionRuntime` currently adapts only the durable graph path.

This is useful scaffolding, not a settled ontology. In particular, `RunKind` values should not be taken as proof that graph, task, team, scheduled work, etc. are primitive execution species. They are currently classification metadata and may collapse or move as convergence proceeds.

## Seam matrix

| Subsystem | Real entry point / handoff | Current lifecycle owner | Useful mechanics to keep | Disconnect from shared spine | Minimal adapter / convergence | What should disappear or shrink afterward |
|---|---|---|---|---|---|---|
| Legacy graph | `graph.executor.run_graph()` creates `GraphRun` then calls `start()` | `GraphRun` / `NodeRun`, plus graph-local events and resilience | Graph topology, condition evaluation, node scheduling, graph-specific resilience mechanics | Creates/owns execution outside canonical runtime; graph event/lifecycle semantics can diverge | Treat legacy graph as an adapter target or migrate callers to durable graph/runtime path; bind canonical execution context around graph execution while preserving graph mechanics | Independent top-level graph run identity/lifecycle; graph-only ownership of universal run facts |
| Durable graph | `run_durable_dag()` / `resume_durable_dag()` | `DurableRunRecord` + durable DAG executor | DAG walk, node resolution, pause semantics, per-node checkpointing, graph blackboard, durable resume | Graph persistence currently doubles as canonical run persistence; caller owns wake-up but no universal scheduler/runtime contract | Runtime owns canonical Run identity/state and maps graph-specific durable state as adapter/checkpoint data; scheduler/API calls runtime resume, not graph internals | `DurableRunRecord` as universal run identity; retain it only as graph adapter state/checkpoint projection |
| Task API | `POST /tasks -> TaskQueue.submit()` | `TaskQueue` | User-facing work request, queue/admission concept, task query compatibility during migration | API creates a second lifecycle object before runtime sees the work | Interpret submission as `WorkRequest`; admission eventually creates/starts a canonical Run while preserving compatibility view by task id | `TaskResponse` as independent lifecycle authority |
| Task queue / runner | `TaskRunner` dequeues, `LaneGate` admits, injected `TaskExecutor` calls Conductor | `TaskQueue` + `TaskRunner` | Lane reservations, tier ordering, worker admission/backpressure, graceful drain | Runner owns PLANNING/CODING/COMPLETED/FAILED, cancellation, progress, result and metrics independently of Run | Keep queue/admission; after permit, hand WorkRequest to runtime. Runtime owns lifecycle/cancellation/result correlation; task API becomes a view/projection | Parallel task state machine and duplicate universal metrics/status transitions |
| Scheduler | schedule fire from shipped `/v1/schedules` implementation (exact implementation path still to re-verify) | Scheduler's own in-memory schedule/fire machinery | Cron/timing, enable/disable, recurrence policy, future durable schedule store | Schedule execution is modeled as its own mini-framework and current implementation drifts from ADR-046 | Scheduler's only execution responsibility should be: resolve schedule -> submit WorkRequest / create Run through runtime. A wait wake-up similarly asks runtime to resume an existing Run | Any scheduler-owned workload lifecycle; scheduler-specific task/run semantics |
| Recovery | `tasks.recovery.CrashLoopPolicy`, checkpoint compatibility helpers; graph durable resume separately | Fragmented between Task recovery policy, graph resume, circuit breakers | Crash-loop policy, version compatibility checks, retry/recovery policy | "Recovery" is spread across task and graph concepts instead of operating on canonical persisted Run/Attempt state | Rehome policies behind runtime resume/retry/recovery decisions; adapters expose their checkpoint compatibility requirements | A separate Task recovery execution framework; duplicated recovery identity |
| A2A delegation | `A2ABroker.delegate()` creates `A2ATask`, then `Transport.run()` / `AgentInvoker` | `A2ATask` state/result plus broker transport result | Delegation budget, depth/loop guard, trust and allow-list policy, local/federated transport abstraction | Delegation invents another task id/state machine instead of participating in parent/child execution lineage | Agent-backed Binding requests fulfillment under current context; if independently inspectable work is spawned, runtime creates a child Run; transport remains fulfillment detail | Universal lifecycle semantics in `A2ATask`; duplicate agent-to-agent execution roots |
| Direct agent delegation | `Agent._delegate()` resolves target and recursively invokes it | Agent call stack/depth guard | Direct in-process optimization where appropriate | Bypasses A2A broker and canonical child/invocation lineage | Route direct and transported delegation through one agent-backed Binding contract; local direct call can remain an implementation of that Binding | Multiple delegation semantics and separate depth/policy implementations |
| Harness-backed graph node | `HarnessNodeExecutor.run() -> HarnessSessionManager.start/send/stop` | Graph `NodeRun` for node lifecycle; harness manager for foreign session | Warden/policy gating, foreign session lifecycle, response normalization | Adapter fabricates `AgentSpec(task_id="graph-harness")` and translates incompatible role enums because runtime context is unavailable at the correct seam | Supply canonical execution/invocation context directly to harness Binding/provider; graph node remains position/composition only | Synthetic task identity, lossy role bridge where not semantically required, duplicate HarnessRunner contracts |
| Durable async harness | `HarnessAdapter.dispatch/poll/cancel` | Harness handle + graph pause/resume path | External handle, poll/cancel, durable async semantics | Parallel harness lifecycle shape to sessionful harness path | One foreign-executor Binding/provider family with invocation modes (request/response, sessionful, durable async); runtime correlates handle/session to Run/Invocation | Separate top-level harness execution ontology |
| RSI | `RsiCycle.run()` creates its own `run_id` and executes branch/patch/test/eval/battle | `RsiCycle` local identity and logs | Sandbox, self-branch, quota routing, patch/test, benchmark/tournament domain loop | Local run identity is detached from workspace/run lineage and canonical events/artifacts | Thin runtime adapter supplies canonical Run context/id and captures cycle events/artifacts/results; leave `RsiCycle` algorithm intact | RSI-created universal run identity and any duplicate top-level lifecycle bookkeeping |
| Evolve | `EvolutionCycle.run_cycle()` | Domain loop only; no canonical Run owner | Evaluation, tournament, fitness, island breeding, self-improvement, migration | Work is significant/inspectable but has no shared Run identity/events | Thin runtime adapter owns Run/events/artifacts around `run_cycle()`; preserve evolution algorithm | No need to invent Evolve-specific universal lifecycle types |
| Conductor / engineering execution | Injected into `TaskRunner` as `TaskExecutor`; further entry points still need exact call-path trace | Task runner and Conductor-specific flow | Planning/coding domain orchestration that is actually product behavior | Product execution currently inherits Task lifecycle instead of runtime lifecycle | Runtime adapter should call Conductor as a specialized executable after admission; child agent/tool work inherits context | TaskRunner acting as Conductor's universal lifecycle owner |

## Important seams, not rewrites

### 1. Durable graph already has the correct scheduler boundary

The durable DAG executor explicitly says that when a run pauses, the scheduler/API is responsible for waking it by calling resume later. That is a clean ownership seam:

```text
Scheduler/API
    owns WHEN work should resume
        |
ExecutionRuntime
    owns WHICH Run is resumed and its universal lifecycle/correlation
        |
Durable graph adapter
    owns HOW the graph continues and checkpoints
```

Do not teach the scheduler graph walking.

### 2. TaskRunner already has the correct admission boundary

`TaskRunner`'s `LaneGate` solves a real scheduling problem: reserved LIVE/BACKGROUND capacity, priority ordering, bounded workers, and drain behavior. Those mechanics should survive.

The seam is immediately after admission:

```text
TaskQueue / WorkRequest
    -> LaneGate admission
    -> ExecutionRuntime.run(...)
    -> Conductor/specialized executable
```

Today the runner instead becomes another run controller and owns planning/coding/completed/failed state. That is the duplicate to remove, not the lane gate.

### 3. Delegation already separates transport from policy

`A2ABroker` has useful pieces: `DelegationBudget`, policy enforcement, `AgentInvoker`, and `Transport`. The wrong duplication is the independent `A2ATask` lifecycle.

Target shape:

```text
Agent A Run / Invocation
    -> Agent-backed Binding
    -> delegation policy/budget
    -> local or federated Transport
    -> Agent B child Run or Invocation
```

This preserves agents-as-tools naturally. An Agent is simply one authorized fulfillment target for a capability.

### 4. Harness adapters prove Node and fulfillment are orthogonal

`HarnessNodeExecutor` can replace the normal graph LLM path. The graph position is therefore not the executor. A Node should be able to resolve an executable payload/binding without fabricating a Task-shaped AgentSpec.

The graph keeps Node/topology semantics. The runtime/binding layer supplies identity, authorization, policy, invocation correlation, and external-session/handle correlation.

### 5. RSI and Evolve should be wrapped, not decomposed into graphs

Both are coherent domain algorithms. Forcing their internals into Graph/Node merely to gain common observability would reproduce the same abstraction sprawl in a new direction.

Their seam is outside the loop:

```text
ExecutionRuntime Run
    -> RSI/Evolve adapter
    -> existing domain cycle
    -> events/artifacts/results recorded against Run
```

## What ExecutionRuntime should own

Evidence from these seams supports a deliberately narrow universal responsibility:

- workspace ownership
- run identity and lineage (`run_id`, root, parent)
- actor/correlation identity
- universal lifecycle (`pending/running/paused/completed/failed/cancelled`)
- cancellation and deadlines at the execution boundary
- child-run creation
- attempt/invocation correlation
- canonical event publication/sequencing
- references to artifacts and adapter checkpoints
- resume/recovery coordination
- cross-cutting capability/security/observability context

It should **not** own every subsystem's domain state machine.

## What specialized adapters should keep

- Graph: topology, edge/condition evaluation, node readiness/walk, graph blackboard, graph checkpoint payload.
- Task admission: queue semantics, lane/tier admission, worker backpressure.
- Scheduler: timing, recurrence, schedule persistence/configuration.
- Delegation: trust/allow-list/depth/budget policy and transport.
- Harness: provider protocol, foreign session/handle lifecycle, polling/cancellation wire semantics.
- RSI: branch/patch/test/evaluate/battle algorithm and sandbox mechanics.
- Evolve: population/evaluation/tournament/mutation/island algorithm.
- Conductor: its actual planning/engineering orchestration semantics.

## First convergence sequence

This order is chosen to reuse existing seams and minimize rewrites.

1. **Separate canonical Run persistence/events from graph adapter persistence.**
   - Keep existing `ExecutionContext` scaffolding.
   - Introduce one canonical Run repository/event contract.
   - Graph durable state references the canonical Run instead of serving as its only persistence implementation.

2. **Adapt TaskRunner after admission.**
   - Preserve `TaskQueue` compatibility and `LaneGate` initially.
   - Once a permit is granted, create/start a canonical Run and invoke Conductor through runtime.
   - Project Run status/result back into current Task API during migration.

3. **Make scheduler fire only submit/start/resume Runs.**
   - First re-verify the exact shipped scheduler path because #343 documents drift and the implementation has moved across package history.
   - Do not combine the scheduler-drift feature build with runtime convergence accidentally.

4. **Unify agent-backed delegation.**
   - Keep broker policy/budget/transport.
   - Replace independent A2A lifecycle ownership with Invocation/child Run lineage.
   - Make direct local delegation and federated delegation two fulfillment modes of the same binding.

5. **Clean the harness binding seam.**
   - Pass execution context instead of fabricated task ids.
   - Merge duplicate harness protocols.
   - Preserve sessionful and durable-async lifecycle modes as provider/protocol behavior.

6. **Wrap RSI and Evolve.**
   - Supply canonical Run identity from outside their existing loops.
   - Emit/capture meaningful events and artifacts without rewriting domain algorithms.

7. **Then connect cross-cutting capabilities.**
   - security/approval
   - credentials
   - memory
   - tool/capability invocation
   - observability
   - artifact provenance
   These should consume the same execution context rather than each adding another lifecycle root.

## Migration deletion test

A seam is not actually converged until the old owner can shrink or disappear.

For every adapter migration, require an explicit answer to:

1. Which old state machine is no longer authoritative?
2. Which old ID is now merely a compatibility alias/projection?
3. Which callbacks/events become canonical event consumers?
4. Which retry/cancel/resume path is deleted or delegated to runtime?
5. Which specialized mechanics remain intentionally local?

If nothing can be removed or demoted after an adapter is added, the adapter probably created another layer instead of stitching the product together.

## Immediate evidence still to trace

- Exact current scheduler service/store route location on this branch.
- Conductor construction and injected `TaskExecutor` wiring from server/bootstrap to `TaskRunner`.
- Product/API entry points for durable graph execution and HITL resume.
- Existing event stores/buses and which are production-reachable.
- Tool executor -> security/approval/credentials call path.
- Workspace/project API ownership of runs and artifacts.

Those traces should update this seam map directly. Do not resume broad noun-by-noun ontology expansion unless a seam cannot be understood without it.
