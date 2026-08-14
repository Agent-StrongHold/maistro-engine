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

## 2. Live Hive RSI owns another private Run lifecycle, and cleanup cancellation is broken

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

`stop_run()` cancels that asyncio task and marks the run stopped. For cleanup mode, however, `_drive_cleanup()` is awaiting `asyncio.to_thread(loop.run)`. Cancelling the asyncio waiter does **not** terminate the executor thread. `LocalRsiLoop` can therefore continue model calls, tests, worktree mutations, and artifact/report writes after the API-visible RunState says `stopped`.

This is a live duplicate universal lifecycle and a broken cancellation edge. Migration must not preserve the current apparent stop semantics as parity. Canonical cancellation has to reach the physical RSI worker or the product must report that cancellation is pending until the worker actually terminates.

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

The thread boundary is also a Stream 1/6 migration requirement: cancellation of the outer asyncio Task alone is insufficient. Any canonical adapter around this synchronous loop needs a cooperative cancellation token, process isolation/termination boundary, or equivalent mechanism that actually stops physical work.

## 4. `LocalRsiLoop` is a deliberately bounded recursive improvement workflow

Its documented invariants include:

- throwaway/local worktrees rather than mutating the user's checkout
- native builder-agent patch generation
- test gate on every promotion
- each accepted cycle becomes the next baseline
- fixed maximum cycle count
- no external PR/push from the local loop itself

The implementation also contains provider-transient classification/fallback behavior and richer tournament/targeting machinery.

This is specialized RSI behavior worth preserving.

## 5. Cleanup mode depends on Bootstrap's separate builder-agent implementation, not `maistro.builders`

Hive creates its patch function with `make_builders_apply_patch(...)` from `maistro_rsi.local_loop`.

Despite the helper name, its lazy implementation imports `BuilderSession`, `TurnRunner`, and `ResponsesAPICallable` from `maistro_bootstrap.builders`. It does **not** depend on the structurally unreachable `maistro.builders` subsystem audited elsewhere.

That distinction matters during convergence:

- `maistro.builders` is a separate product/orchestration subsystem whose private lifecycle is a Stream 7 migration target.
- `maistro_bootstrap.builders` is live Bootstrap builder-agent behavior consumed by RSI cleanup and belongs to the Bootstrap/control-plane compatibility surface.

### Stream 7 handoff

Do not use RSI cleanup as evidence that the unreachable `maistro.builders` package is a live dependency. Preserve or deliberately replace the `maistro_bootstrap.builders` patch-generation contract used by RSI while separately migrating the `maistro.builders` subsystem on its own evidence and callers.

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

- cleanup start/status behavior
- bounded/test-gated LocalRsiLoop behavior
- a **working physical cancellation** replacement for the current broken cleanup `stop`
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

RSI should become another producer/consumer of canonical Run rather than retain private RunState lifecycle. Cancellation must not terminalize the canonical Run/Attempt as stopped while an uncancelled cleanup worker continues mutating state.

### Stream 5

If RSI cleanup is represented as Graph behavior, preserve bounded cycle/test-gate/revision semantics through GraphExecutionState or product nodes rather than generic Run states.

### Stream 6

Provider fallback/capacity behavior inside LocalRsiLoop should be reconciled with canonical Provider/Invocation rather than retained as a fully separate provider-selection plane. If the physical RSI operation stays thread-backed temporarily, its Invocation/Attempt cancellation adapter must stop or cooperatively halt the underlying work.

### Stream 7

Prioritize live cleanup-mode parity first. Preserve review/Ralph/promotion domain behavior. Treat greenfield/autorun as future behavior sources unless explicitly activated. Track Bootstrap's builder-agent implementation separately from `maistro.builders`.

## Reachability lesson

Subsystem names are not enough to infer dependencies. The live RSI cleanup path composes `maistro_bootstrap.builders` behavior; that does not make the separate `maistro.builders` subsystem reachable. Migration ownership must follow the actual imported implementation and rooted caller chain.
