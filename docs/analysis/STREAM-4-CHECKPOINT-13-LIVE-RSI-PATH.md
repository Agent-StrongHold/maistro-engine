# Stream 4 Checkpoint 13: Live RSI Product Path

Date: 2026-08-14
Source audited: `develop`

This checkpoint refines the earlier RSI package audit by tracing the production-mounted Hive RSI route to the behavior that is actually live today.

## 1. Hive exposes a mounted RSI API, but it does not use the autonomous `autorun` path

`routes/rsi.py` is mounted as an optional feature slice and exposes:

- status
- model choices
- list/get/start/stop runs
- promotion review listing
- approve/deny review decisions
- Ralph/RLPHD state
- optional PR creation for approved patches

This is a real product/control surface when `maistro-rsi` is installed in the Hive process.

Classification: `live optional RSI product surface`.

## 2. Live Hive RSI owns another private Run lifecycle

`services/rsi.py` defines:

- private `RunState`
- run ID
- mode
- config
- status: pending/running/completed/errored/stopped
- start/end timestamps
- cycle/promotion counts
- summary/report/export paths
- an `asyncio.Task` handle

`start_run()` mints a local run ID, stores the RunState in an in-memory dictionary, launches `_drive()` as an asyncio task, and sets status running.

`stop_run()` cancels that task and marks the run stopped.

This is a live duplicate universal lifecycle and should migrate to canonical Run/Attempt rather than being preserved as a second durable source.

## 3. Cleanup mode is the actual live execution behavior

For `mode="cleanup"`, Hive constructs `LocalRsiConfig`, allocates work/report directories when absent, and calls:

`LocalRsiLoop(...).run()`

through `asyncio.to_thread` so the synchronous loop does not block Hive's event loop.

The live service forwards operator controls including:

- repo path
- test command
- max cycles
- model
- agent turns
- objective/targets
- fitness
- coverage inputs
- export/report paths
- genome models
- roster size
- scout

These values are real product behavior and belong in Stream 7 migration acceptance criteria.

## 4. `LocalRsiLoop` is a deliberately bounded recursive improvement workflow

Its documented invariants include:

- throwaway/local worktrees rather than mutating the user's checkout
- native Builders-agent patch generation
- test gate on every promotion
- each accepted cycle becomes the next baseline
- fixed maximum cycle count
- no external PR/push from the local loop itself

The implementation also contains provider-transient classification/fallback behavior and richer tournament/targeting machinery.

This is specialized RSI behavior worth preserving.

## 5. Cleanup mode currently composes directly with Builders implementation

Hive creates its patch function with `make_builders_apply_patch(...)` from `maistro_rsi.local_loop`.

Therefore the live RSI product path depends on Builders-style patch-generation behavior even though the standalone `maistro.builders` subsystem remains structurally unreachable as a process island.

This is exactly the kind of hidden behavioral dependency Stream 4 is meant to surface: “Builders is unreachable” does **not** mean every Builders-derived behavior is irrelevant to live products.

### Stream 7 handoff

When Builders execution migrates onto canonical Graph/Run, preserve the patch-generation adapter contract used by RSI or replace it with an equivalent canonical Node/GraphTemplate interface.

## 6. Greenfield mode is explicitly not wired

For `mode="greenfield"`, the live Hive service does not run `RsiCycle`.

It sets status errored and reports that greenfield benchmark-tournament mode is not wired yet and that callers should use cleanup or package CLI/runner paths.

Therefore:

- `RsiCycle`/SWE-Bench/Elo/quarantine behavior remains valuable migration source
- it is **not** current Hive production parity
- Stream 7 should not hold canonical migration hostage to matching an unwired greenfield UI path before the cleanup path is converged

Classification: `implemented/scaffolded domain behavior, not live Hive execution`.

## 7. The unreachable `autorun` loop is likewise not the mounted Hive controller

Earlier audit found `maistro_rsi.autorun` contains a richer autonomous hypothesis-tree controller but remains structurally unreachable by the current ratchet.

The live Hive controller is `_RsiService -> LocalRsiLoop`, not `autorun`.

This distinction should be explicit in product migration planning:

### Must preserve for current product parity

- cleanup start/stop/status
- LocalRsiLoop bounded/test-gated behavior
- report/export/review flow
- approve/deny idempotency
- Ralph feedback state
- optional PR promotion behavior

### Future/optional migration source

- autonomous hypothesis tree
- richer autorun spend circuit breaker
- greenfield RsiCycle benchmark tournament
- full external-agent/micro-VM shape

## 8. Review/PR behavior is product-domain state, not universal Run state

RSI review routes preserve meaningful domain semantics:

- first decision wins/idempotent review decisions
- approve vs deny
- feedback into Ralph/RLPHD model
- weight/theta deltas
- patch preview
- optional PR creation from approved patch

These should remain RSI product/domain objects/events even after execution moves to canonical Run.

Do not try to encode `approved patch`, `Ralph weight delta`, or promotion review as universal Run lifecycle states.

## 9. Current RSI RunState is in-memory and restart-sensitive

The service stores active/historical RunState only in `_runs` process memory.

A process restart loses this service-level run registry even if report artifacts remain on disk.

Canonical Run persistence can improve this without inventing a second RSI-specific durable run store.

## Immediate handoffs

### Stream 1

RSI should become another producer/consumer of canonical Run rather than retain private RunState lifecycle.

### Stream 5

If RSI cleanup is represented as Graph behavior, preserve bounded cycle/test-gate/revision semantics through GraphExecutionState or product nodes rather than generic Run states.

### Stream 6

Provider fallback/capacity behavior inside LocalRsiLoop should be reconciled with canonical Provider/Invocation rather than retained as a fully separate provider-selection plane.

### Stream 7

Prioritize live cleanup-mode parity first. Preserve review/Ralph/promotion domain behavior. Treat greenfield/autorun as future behavior sources unless explicitly activated.

## Reachability lesson

Subsystem-level unreachability is not transitive to every behavior associated with that subsystem. The live RSI cleanup path composes Builders-derived patch behavior even while the standalone Builders package remains a closed island from process entry points.
