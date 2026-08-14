# Stream 4 Checkpoint 6: Product Execution and Recovery Migration

Date: 2026-08-14
Source audited: `develop`

This checkpoint classifies unreachable RSI/Canvas/Evolve execution modules and task recovery/approval behavior for canonical migration.

## 1. RSI's valuable domain loop is broader than a generic Run

`maistro_rsi.runner.RsiCycle` defines one self-improvement experiment:

- create isolated sandbox/workspace
- choose model using quota headroom
- branch/patch/test the codebase
- fail closed if quarantine is not wired for promotion
- run differential workspace probes or benchmark evaluation
- compare baseline/candidate in the Evolve tournament
- update quota-burn usage
- clean up sandbox/workspace
- produce improvement evidence

`maistro_rsi.autorun` then builds a higher-level autonomous experimentation loop around RSI cycles with:

- hypothesis tree growth
- seed hypotheses / LLM proposer
- proposer circuit breaker to prevent spend loops
- repeated experiments
- Warden quarantine before promotion
- JSONL audit trail
- atomic tree snapshots after every cycle
- retained learnings ledger across runs
- wall-clock limits
- model discovery/quota pacing
- optional PR creation

These are substantive RSI domain semantics and should not be reduced to “just call a model.”

### Stream 7 migration direction

Represent the RSI process as product graph/template behavior on canonical Graph/Run:

- hypotheses and experiment lineage remain RSI domain objects/data
- experiment cycle becomes Graph/Node structure or a specialized node backed by canonical Attempt/Invocation
- audit/promotion evidence projects into canonical Event/artifact/provenance
- retained learnings remain RSI memory/domain state

Do not preserve RSI's locally minted `run_id` as a second universal Run identity once canonical Run is available.

Classification: `preserve domain loop; replace universal execution identity/lifecycle`.

## 2. RSI HarnessAdapter is a duplicate asynchronous invocation layer

`maistro_rsi.harness_adapter.RsiCycleHarnessAdapter` adapts RSI cycles to `maistro.graph.harness.HarnessAdapter` by owning:

- handle IDs
- background asyncio tasks
- deadlines
- concurrent repeated cycle attempts under one handle
- polling
- aggregation of parallel outcomes
- timeout cancellation
- explicit cancellation

The current reachability baseline marks this adapter unreachable.

### Stream 6 handoff

Do not separately revive this handle/poll/cancel registry if canonical Invocation supports asynchronous providers. Preserve its aggregation semantics where RSI intentionally dispatches multiple independent attempts, but let canonical Invocation/Attempt own lifecycle and correlation.

Classification: `unreachable adapter; supersede/absorb`.

## 3. Canvas has a private universal job lifecycle and recovery loop

`maistro_canvas.types.GenerationJobRecord` defines:

- pending/running/done/failed/cancelled
- attempts/max_attempts
- worker lease owner/expiry
- timestamps
- result paths
- selected variant
- error state

`CanvasJobRunner` owns:

- polling
- atomic claim
- lease expiry/reaping
- worker identity
- retry/requeue
- terminal failure
- persistence after execution

The current reachability baseline marks Canvas runner/store/tool modules unreachable.

### Stream 1 / Stream 5 / Stream 7 handoff

Preserve recovery mechanics:

- claim ownership
- lease expiry / stale-worker recovery
- bounded retries
- cancellation

But move universal execution lifecycle to canonical Run/NodeRun/Attempt/checkpoint/recovery rather than retaining a separate Canvas job scheduler.

Canvas-specific generation request/result data remains Canvas domain state or node inputs/artifacts.

Classification: `domain job request + duplicate universal lifecycle`.

## 4. CanvasExecutor contains substantial domain invariants worth preserving

`CanvasExecutor` currently mixes two categories.

### Canvas domain behavior to retain

- text layers cannot invoke image generation actions
- refine requires a source image
- model registry validation/default draft selection
- prompt Warden scan
- one active generation per layer
- generation/refine/reference action semantics
- safe provider-error sanitization
- variant bounds checking
- accepted variant updates the layer and parent canvas timestamp
- explicit cancellation semantics

### Universal mechanics to migrate

- pending -> running -> done/failed/cancelled job lifecycle
- execution timestamps
- retry ownership
- background execution placement

Stream 7 should preserve the first group and consume canonical execution for the second.

Classification: `split + migrate`.

## 5. Evolve executable-terminal runner is primarily an evaluation command, not a competing lifecycle

`maistro_evolve.executable_terminal_runner` runs a training evaluation set, derives feedback, then runs holdout tasks and appends both summaries to a ledger. It selects either a Codex CLI or OpenAI-compatible provider.

Unlike Canvas/Builders/RSI, this file does not define a durable job/run state machine. Its main architectural overlap is provider selection/calling.

### Migration direction

- preserve benchmark/evaluation sequencing as Evolve domain behavior
- provider implementations should converge on canonical Provider/Invocation where Evolve runs inside the platform
- retaining a standalone CLI evaluation entrypoint can still be reasonable; not every CLI/test harness must become a canonical Run if it is explicitly an offline developer tool

Classification: `domain eval command; provider convergence only`.

## 6. Task recovery/replay is unreachable but directly useful for canonical recovery

`maistro.tasks.recovery` currently provides:

- crash-loop quarantine using a circuit breaker
- checkpoint compatibility checks against recipe and code-registry versions

`maistro.tasks.replay` reconstructs resume state from ordered TaskCheckpoints:

- open tool calls
- wave status
- cumulative spend
- pending approval gates

These modules are on the current unreachable baseline.

### Streams 1/2/5/6 handoff

Do not wire them back into Task as a separate durability stack.

Port/re-express the behavior onto canonical contracts:

- TaskCheckpoint -> canonical Checkpoint/Event history
- open tool calls -> pending/in-flight Invocation/Attempt recovery
- wave status -> GraphExecutionState
- spend -> canonical usage/accounting events/state
- approval gates -> Invocation/runtime policy checkpoint state
- version compatibility -> Graph/template/runtime provenance compatibility
- crash-loop quarantine -> scheduler/recovery policy around canonical Attempts/Runs

Classification: `high-value unreachable recovery source -> port into canonical spine`.

## 7. Tool approval gate is runtime-impact policy, not Project authorization

The unreachable `maistro.tools.approval.gate` contains useful functions:

- whether a plan requires approval
- whether a tool call was declared in an approved plan
- impact-threshold evaluation
- escalation when undeclared or over threshold
- collapsing clustered impact dimensions within a time window

These are execution-time action approval semantics.

### Stream 6 handoff

Integrate with Invocation/action policy if the behavior is still desired. Do not map plan approval onto Project membership/permission grants.

Classification: `runtime policy source`.

## 8. Tool reversibility taxonomy is useful Capability metadata

The unreachable reversibility subsystem defines:

- internal
- reversible
- irreversible

plus optional compensator, impact estimator, and idempotency key metadata. External tools default to irreversible.

This maps cleanly to Capability/Provider/Invocation safety metadata.

### Stream 6 handoff

Preserve the taxonomy as capability/invocation metadata rather than reviving a parallel tools registry. It can inform:

- approval requirements
- compensation/recovery
- retry safety
- idempotency behavior
- audit severity

Classification: `metadata/behavior source -> absorb into Capability/Invocation`.

## Consolidated product migration rule

Across Builders, RSI, and Canvas the same pattern is now evidence-backed:

**Keep specialized domain behavior. Replace specialized universal lifecycle behavior.**

Concrete examples:

- Builders quality gates/revisions stay; Builders RunState does not own universal lifecycle.
- RSI hypothesis/evaluation/promotion loop stays; RSI-local run identity does not own universal lifecycle.
- Canvas layers/generation/variant rules stay; CanvasJobRunner does not own universal lifecycle.
- Evolve benchmarks stay; provider calling converges where platform-managed.

## Immediate handoffs

### Stream 1

Port claim/retry/recovery semantics into canonical Run/Attempt rather than adding durability to each product queue.

### Stream 2

Task replay and product audit logs contain event/checkpoint semantics worth translating into canonical Event/Checkpoint.

### Stream 5

Builders revision invalidation and product recovery state should be supported through GraphExecutionState hooks rather than private graph executors.

### Stream 6

Absorb HarnessAdapter-style async execution, RSI harness dispatch, Evolve providers, approval gates, and reversibility metadata into Capability/Provider/Invocation contracts where appropriate.

### Stream 7

Use the product-specific behavior inventories above as migration acceptance criteria.

## Next Stream 4 slices

1. privilege/governance/resource-authorization overlap for Stream 3
2. active service/UI callers that still expose legacy lifecycle DTOs
3. deletion prerequisites for the strongest closed islands
