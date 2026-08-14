# Stream 4 Checkpoint 4: Builders, Delegation, and Policy Boundaries

Date: 2026-08-14
Source audited: `develop`

This checkpoint inventories private execution lifecycle behavior in Builders, A2A/harness delegation, and security/policy modules that must be classified before product migration.

## 1. Builders owns a second graph executor with valuable domain semantics

`maistro.builders.graph_executor.GraphPipelineExecutor` is not merely a workflow-definition helper. It owns execution behavior:

- graph validation
- ready-set calculation
- concurrent wave dispatch
- skip predicates
- unavailable-agent skips
- node timeouts
- shared iteration budget
- failure halting
- output accumulation
- gate evaluation
- bounded revise-and-rerun loops
- descendant invalidation/re-execution after a gate failure
- gate exhaustion policy (`continue` vs halt)
- direct mutation of run status/error/context

The specialized gate/revision behavior is Builders domain value and should survive migration.

The universal traversal/lifecycle mechanics duplicate canonical Graph/Run concerns and should not remain independently owned after convergence.

### Stream 7 / Stream 5 handoff

Preserve as domain behavior:

- stage definitions
- skip predicates
- quality gates
- revise targets
- max revision limits
- gate-exhaustion policy
- feedback injection when revising

Migrate onto canonical execution:

- run lifecycle
- node lifecycle
- fan-out wave execution
- timeout/cancellation
- iteration/attempt accounting
- persisted execution state
- events

Classification: `specialized graph behavior + duplicate universal executor`.

## 2. BuildersRuntime is a useful adapter seam, not primarily a lifecycle owner

`maistro.builders.runtime.BuildersRuntime` is a stateless registry/dispatcher of `(worker, stage) -> handler`, plus prompt/tool lookup.

Its `execute()` delegates one stage and returns a RunResult. It does not itself sequence stages or persist runs.

This is much closer to a product adapter / provider seam and may remain useful after convergence, provided its `RunRequest/RunResult` contracts are projected from canonical Node/Attempt/Invocation context rather than treated as another universal run model.

Classification: `keep/adapt`.

## 3. BuildersOrchestrator is a separate private Run lifecycle owner

`maistro.builders.orchestrator.BuildersOrchestrator` defines:

- private `RunState`
- Builders `RunStatus` (`queued`, `running`, `passed`, `failed`, `blocked`)
- explicit stage transition map
- current stage/worker
- runtime version assignment
- runtime ready/draining/retired state
- artifact accumulation/deduplication
- private StageEvent history
- retry counts
- completion-gate checks
- dump/load persistence serialization

The file explicitly says “Core owns workflow state,” but this is still a Builders-specific workflow-state implementation rather than the convergence program's canonical Run.

### Migration split

Preserve as Builders domain/product state:

- engineering stage vocabulary (`issue_analyzed`, `acceptance_defined`, `tests_written`, etc.)
- worker assignment
- artifact semantics
- completion gates
- runtime-version rollout/draining if Builders continues to need versioned worker runtimes

Replace with canonical execution state:

- universal Run status
- retries
- event history
- persistence of execution lifecycle

Classification: `split + migrate`.

## 4. Builders defines another private event envelope

`maistro.builders.contracts.StageEvent` carries run_id, stage, event, actor, timestamp, and message.

It is useful as a Builders/product projection but should not remain a separate durable event source once canonical Event is wired.

Handoff to Stream 2: preserve stage/actor/message as event payload/projection fields while canonical Event owns identity, sequencing, correlation, and persistence.

## 5. Harness-spawn graph node already uses durable pause/resume correctly

`agent.spawn_harness` does not create another graph-run state machine. It:

1. dispatches via an injected HarnessAdapter
2. records handle metadata in a durable pause
3. resumes from persisted answer/result data

This is aligned with the desired canonical Graph/Run recovery direction.

Classification: `preserve node behavior; migrate invocation seam`.

## 6. HarnessAdapter overlaps strongly with canonical Provider/Invocation mechanics

`maistro.graph.harness.HarnessAdapter` defines:

- `dispatch(request) -> handle`
- `poll(handle) -> result | None`
- `cancel(handle)`

with harness kinds such as Claude Code, Conductor, generic HTTP, and in-process execution.

This is effectively an asynchronous external execution provider contract.

### Stream 6 handoff

Do not build a parallel long-term Harness execution abstraction beside Provider/Binding/Invocation.

Preserve:

- async dispatch handle semantics
- polling/resolution where providers require it
- cancellation
- provider-specific metadata
- long-running external execution

Converge the abstraction so a harness is a Provider/Capability execution mode and its dispatch is represented by canonical Invocation tied to the current Attempt.

Classification: `merge into Provider/Invocation contract`.

## 7. A2A graph delegation also reuses durable pause/resume

`agent.delegate_remote` supports two paths:

- in-process delegation through `A2ADelegator`
- cross-instance delegation through `GuestPeerManager`

The graph node itself dispatches once and then pauses/resumes through the durable executor.

This is good architecture to preserve.

Classification: node/recovery behavior = `keep`.

## 8. A2ADelegator contains another private task lifecycle and in-memory store

`maistro.a2a.delegate` defines its own:

- `TaskStatus`: queued, assigned, running, completed, failed, cancelled
- transition table
- `A2ATask`
- in-memory task dictionary
- result/error/timestamps
- delegation mode and target-selection state

That task lifecycle competes with canonical Run/Attempt/Invocation once delegation becomes first-class execution provenance.

### Preserve

- delegation modes
- allowed-target capability checks
- target-selection policy
- parent/target agent identity
- delegation metadata

### Replace

- independent A2ATask execution lifecycle
- independent durable-source ambitions, if any are added later

Target conceptually:

`parent Attempt -> Invocation/delegation -> child Run (or remote run reference)`

with canonical Event/provenance for status changes.

Classification: `keep delegation policy; replace duplicate lifecycle`.

## 9. GuestPeerManager is trust/provider configuration, not authorization-by-Persona

`maistro.a2a.guest_peers.GuestPeerManager` owns:

- peer registry
- active/inactive state
- peer URL
- authentication method/credential
- allowed agent IDs
- outbound HTTP dispatch
- audit logging

This is external-provider/trust configuration. The `allowed_agents` list is existing delegation-specific policy and should be evaluated during migration, but it must not become the Project authorization algorithm by accident.

Stream 6 should absorb peer transport/provider behavior; Stream 3 should decide how canonical Project resource authorization gates access to a peer/binding.

Classification: `provider/trust config + domain policy`.

## 10. Similar names in security/policy hide distinct concerns

There are at least three separate concepts that could be incorrectly collapsed during convergence:

### `maistro.security.Gate`

Ingress safety boundary:

- sanitize user input
- Warden scan
- strike/lockout escalation
- request sufficiency checks
- supervised-mode clarification

This is input security/safety, not Project authorization.

### `maistro.policy.SequencePolicyEngine`

Sequence-aware runtime action policy:

- cumulative action state per key
- deny
- require approval
- allow
- budget/accounting rules
- commits state only when action is allowed

This is runtime execution policy, not identity membership resolution.

### `maistro.policy.PolicyActionGate`

Adapter from harness action dictionaries into SequencePolicyEngine charges. It is an execution-policy seam used by harness execution.

This belongs near Invocation/runtime mechanics, but remains conceptually distinct from Project authorization.

### Stream 3/6 invariant

Keep these layers distinct:

1. identity/authentication
2. Project/Workspace authorization/resource visibility
3. input safety/security scanning
4. runtime execution policy/budgets/approval
5. Capability/Binding/Provider Invocation

The convergence effort should connect them in order, not merge them into one generic “permission/security gate.”

## Immediate handoffs

### Stream 2

- Builders `StageEvent` should become a product projection over canonical Event.
- Delegation/harness state changes need canonical correlation rather than private logs.

### Stream 3

- A2A `allowed_agents`, input Warden rules, and runtime policy rules are not substitutes for Project membership/resource authorization.
- Guest peer/resource visibility should be checked by canonical project authorization before invocation.

### Stream 5

- Builders gate/revision behavior belongs in parity/migration coverage as specialized graph behavior.
- Do not duplicate GraphPipelineExecutor traversal mechanics after canonical graph execution supports the needed hooks.

### Stream 6

- HarnessAdapter should converge into Provider/Invocation.
- A2A cross-instance transport should converge into provider/invocation mechanics where feasible.
- Preserve async handle/poll/cancel behavior.
- Parent Attempt -> delegated Invocation -> child/remote Run provenance should replace A2ATask as universal lifecycle.

### Stream 7

- Keep Builders stage vocabulary, worker roles, quality gates, artifacts, and revise behavior.
- Replace private RunState/RunStatus/retry/event persistence with canonical primitives.

## Next Stream 4 slices

1. current-state recheck of historical zero-importer / closed-island findings
2. remaining privilege/governance/security overlap with canonical Project authorization
3. product-specific private execution loops in RSI/Evolve/Canvas/Hive
4. service/UI callers that still depend on compatibility DTOs
