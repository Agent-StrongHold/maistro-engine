# Stream 4 Checkpoint 2: Runtime Reachability and Lifecycle Duplication

Date: 2026-08-14
Source audited: `develop`

This checkpoint extends the Stream 4 legacy/reachability audit into live Hive Workspace behavior, GraphRun vs durable execution, and the Task/Mission/Schedule path.

## 1. Hive Workspace is live product behavior, not disposable UI state

`packages/hive-conductor/backend/main.py` mounts `routes.workspaces` at `/v1/workspaces`.

The route surface does substantially more than CRUD for a Persona tab. It currently owns or exposes:

- persona-template discovery and in-app persona authoring
- persona-declared agent discovery
- capability checklist acceptance
- workspace creation and agent materialization
- owner/editor/viewer membership
- owner-only membership changes
- protection against deleting the final owner
- archive/unarchive vs hard delete
- persona feedback aggregated across workspaces
- theme and voice overrides
- owner-only per-agent tool/prompt binding overrides

The backing `stores.workspaces` ModelStore participates in Hive's optional persisted-store wiring, so this is not merely ephemeral frontend state.

### Migration constraints

- Stream 1 owns the canonical ownership-root Workspace noun.
- Stream 3 should preserve the existing membership invariants as acceptance-test source material, especially visibility, owner-only mutation, self-removal, and last-owner protection.
- Stream 6 should absorb sticky tool-binding semantics into canonical Binding/Invocation concepts rather than leaving authorization-looking behavior inside a Persona-tab object.
- Stream 7 should preserve persona adoption, branding, feedback, theme, voice, and materialized-agent UX behavior.

Classification: `split + migrate`, not delete.

## 2. GraphRun and durable graph execution are complementary, not interchangeable

`maistro.graph.run.GraphRun` currently owns behavior that the durable executor does not implement:

- conditional-expression evaluation against typed plan/code/review output
- parallel outgoing edges and active-node batches
- `asyncio.gather` fan-out execution
- scout execution
- typed plan/code/review pipeline state
- per-role executor overrides
- in-memory event callbacks
- iteration budgeting
- cancellation propagated into active NodeRuns

The durable executor adds a different behavior set:

- persisted DAG snapshot
- checkpoint after each node
- persisted node records
- pause-wait and pause-HITL states
- resume entrypoint
- persisted HITL answers
- resume timestamps
- optimistic `version` increments
- reconstructed NodeContext/blackboard state
- halt-request propagation
- synth-depth recursion accounting
- step-budget exhaustion as explicit failure

Critically, durable `_next_node()` is Phase-1 traversal logic. It advances one `current_node_id` at a time. If all outgoing edges are conditional, it takes the first conditional edge rather than evaluating the condition. It therefore does not preserve GraphRun's routing semantics, and it does not implement GraphRun's parallel active-set traversal.

### Stream 5 handoff

Do not replace GraphRun with DurableRunRecord or vice versa. The convergence target needs parity tests covering the union of both behavior sets before either legacy abstraction is removed.

Classification: `merge behavior, replace duplicate lifecycle ownership`.

## 3. Hive Mission is already a projection over the maistro Task lifecycle

Hive's `/v1/tasks` route is implemented by `routes/missions.py`, but engine-backed mode delegates lifecycle ownership to `services.engine.EngineService` and its TaskBackend.

When engine-backed:

- Mission list/get/create map to `maistro.tasks` records.
- Hive synthesizes Mission fields from a TaskRecord.
- direct Mission status mutation returns 409 because the task runner owns lifecycle.
- deletion delegates to the TaskBackend.

This is already an adapter/projection pattern and should remain one during Run convergence.

### Semantic loss to remove

`adapters/task_backend.py` maps canonical-ish Task statuses to Mission status. It maps `cancelled` to `failed`.

That loses cancellation semantics and should not survive convergence. Canonical Run cancellation should project as cancellation, not failure.

Classification: Hive Mission = `compatibility/product projection`.

## 4. Production and demo Task execution already diverge behind a useful boundary

`EngineService` depends on a `TaskBackend` protocol.

- production default: `MaistroServerTaskBackend`, using maistro-server `/tasks`
- demo/dev only: `LocalTaskBackend`, which constructs in-process `TaskQueue + TaskRunner`

This boundary is useful and should not be collapsed prematurely. It cleanly separates product API behavior from execution placement.

However, the underlying Task domain is a competing universal lifecycle abstraction relative to canonical Run.

`TaskStatus` currently includes:

- queued
- planning
- coding
- reviewing
- testing
- completed
- failed
- cancelled

Several of those are engineering-product phases, not universal execution lifecycle states. `TaskRunner` itself currently drives queued -> planning -> coding -> completed/failed for the single-pass executor.

### Stream 1 / Stream 7 handoff

Preserve:

- lane admission and priority-tier scheduling behavior
- live/background reservation semantics
- task ownership filtering
- progress projection
- graceful worker draining
- progress webhook behavior

Do not preserve `planning/coding/reviewing/testing` as canonical Run states. Those should become graph/node/product progress semantics where needed.

Classification: Task = `compatibility execution request/projection pending Run migration`.

## 5. TaskQueue is live but explicitly non-durable

`maistro.tasks.queue.TaskQueue` states that all task state is in memory and process restart loses all tasks. Its comment still describes future PostgreSQL persistence.

The queue does contain useful execution mechanics:

- async pending queue
- claim protection against double execution
- owner-aware get/list
- transition validation
- terminal pruning
- waiter notification
- cancellation
- cleanup of terminal tasks

These mechanics should be evaluated against canonical Run persistence/recovery rather than independently receiving a second durable persistence implementation.

### Convergence constraint

Do not implement a new durable `TaskRecord` persistence track now. If Task remains as a compatibility API, persistence should project to canonical Run/Run request records rather than creating another source of truth.

Classification: `live compatibility queue; durability roadmap superseded by Run convergence`.

## 6. Hive scheduler is reachable but its advertised execution behavior is not connected

Hive starts `services.scheduler` from application lifespan. The scheduler wakes every 30 seconds, evaluates stored cron schedules, and calls `_fire_schedule()`.

`_fire_schedule()` currently:

1. updates the schedule's `last_run`
2. logs `schedule_fire`
3. reads `mission_template_id`
4. returns without submitting a Mission, Task, Run, Graph, or other execution object

The module docstring says it "fires scheduled missions," but the implementation does not actually launch one.

This is not dead code. It is a live, reachable scheduler with a disconnected execution edge.

### Handoff

The convergence target should be:

`Schedule -> Run` (or a canonical Run request/Graph invocation)

not:

`Schedule -> Mission lifecycle clone`

Stream 7 should preserve the Hive schedule product/API surface if desired; Stream 1 / recovery ownership should define the canonical execution handoff.

Classification: `reachable but behaviorally disconnected`.

## 7. A second scheduling model exists in maistro-core

`maistro.scheduling.store` independently defines:

- `ScheduledTask`
- `TaskExecution`
- `InMemoryScheduleStore`
- cron validation
- max 10 tasks/user
- minimum 15-minute interval
- execution history

Hive's `models.schemas.Schedule` is a separate Pydantic shape containing `mission_template_id`, `last_run`, and `next_run` and is stored through Hive's ModelStore infrastructure.

These are duplicate scheduling abstractions with different persistence and domain contracts.

### Migration direction

Preserve the strongest behavior from both:

- cron validation and frequency limits
- owner/user scope
- enable/disable
- run history or references to canonical Runs
- next/last fire metadata if product surfaces need it

But converge onto one Schedule object that starts canonical Runs. Do not preserve `mission_template_id` as a permanent universal coupling.

Classification: `merge`.

## Immediate handoffs

### Stream 1

- Task lifecycle is a compatibility surface, not a second canonical lifecycle.
- Do not let Task persistence become another durable source of truth.
- Schedule should launch canonical Run semantics.
- Preserve cancellation distinctly from failure.

### Stream 3

Use Hive Workspace behavior as acceptance-test source material:

- member visibility
- owner/editor/viewer roles
- owner-only member mutation
- self-removal
- last-owner protection
- owner-only workspace settings and deletion

Persona itself must remain outside permission resolution.

### Stream 5

Parity matrix must include GraphRun routing/fan-out plus durable pause/resume/checkpoint behavior before removing either implementation.

### Stream 7

- Hive Workspace is a live adopted-persona/product surface and must be migrated rather than discarded.
- Hive Mission should remain a projection, not own lifecycle.
- Hive Schedule is live UI/API behavior but its current fire path does not execute anything.

## Deletion / replacement status after Checkpoint 2

### Keep until migrated

- Hive Workspace route/model/store behavior
- TaskBackend boundary
- TaskRunner lane admission / draining semantics
- GraphRun routing and fan-out behavior
- durable graph pause/resume/checkpoint behavior

### Replace after canonical consumer exists

- Hive Mission lifecycle DTO as an owning model
- `TaskStatus` engineering phases as universal lifecycle states
- standalone Task durability roadmap
- duplicate Schedule models
- Hive schedule -> `mission_template_id` execution coupling

### Candidate for removal after product decision / caller audit

- unreachable Hive deployment `routes/projects.py` from Checkpoint 1
- legacy stub Mission stores once all product routes are engine-backed

## Next audit slices

1. event/correlation and callback islands for Stream 2
2. credential/security/tool-binding islands for Streams 3 and 6
3. Builders private graph/runtime reachability for Stream 7
4. delegation/harness execution duplicates
5. historical zero-importer and closed-island findings against current `develop`
