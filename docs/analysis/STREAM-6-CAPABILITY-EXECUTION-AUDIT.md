# Stream 6 Capability Execution Audit

Date: 2026-08-14
Branch: `audit/stream-6-capability-execution`
Baseline: `develop`

## Purpose

Prepare the capability-execution stream without defining canonical interfaces ahead of the core spine or authorization streams.

Stream 6 owns the convergence of:

`Capability -> Provider -> Binding -> Invocation -> Attempt -> ExecutionRuntime`

plus credentials, ToolExposure, MCP, HTTP, harness execution, provider health/fallback, and the security/tool machinery that must sit on the real invocation path.

This audit is intentionally documentation-only. It does not introduce Binding, Invocation, Attempt, or authorization semantics while those contracts are still owned by other streams.

## Current dependency status

### Stream 1: core domain spine

Required before Stream 6 can implement the canonical invocation path.

Needed contracts:

- canonical Project ownership/persistence and `project_id` propagation
- canonical Run / NodeRun / Attempt model
- authoritative `attempt_id`
- Attempt -> ExecutionRuntime execution seam
- lifecycle/terminalization behavior sufficient for Invocation to report one physical call into one Attempt

Current `develop` still exposes the legacy graph-owned execution model:

- `GraphRun` owns universal run lifecycle state and cancellation
- `NodeRun` owns retry counters and retry loops
- there is no canonical first-class Attempt record on `develop`
- the graph `NodeExecutor` seam is a specialized execution-backend hook, not the canonical Invocation/Attempt seam

Therefore Stream 1 is the hard blocker for production Invocation integration.

There is no current open Stream 1 PR. PR #388 contains the ExecutionRuntime/convergence work, but its own follow-up sequence places canonical Run / NodeRun / Attempt after that runtime foundation. Stream 6 should not infer or invent the missing Attempt contract.

### Stream 2: event/checkpoint/persistence

Open PR: #395 `feat(events): canonical event envelope and sequencing contract`.

Stream 6 can design without this merged, but implementation should consume the canonical event envelope rather than invent invocation-specific callbacks or telemetry records.

Required integration points once available:

- Invocation started/completed/failed events
- `workspace_id`, `run_id`, `node_run_id`, `attempt_id`, `invocation_id` correlation
- provider-selection/fallback events where operationally meaningful
- credential/security decisions represented as domain payloads, not alternate event envelopes

Checkpoint work itself is not a direct Stream 6 blocker.

### Stream 3: project authorization + resources

Open PR: #393 `feat(auth): project authorization and resource scopes`.

This is a direct Stream 6 dependency and should land before canonical Binding/Invocation enforcement is wired.

The proposed contract already establishes the seams Stream 6 needs:

- WorkspaceMembership / ProjectMembership
- sticky denies and narrowing grants
- ResourceScope for workspace/project resources
- resource kinds for credential, Binding, and policy
- `AuthorizationResolver.resolve(...)`
- `AuthorizationResolver.can_view_resource(...)`
- Persona explicitly excluded from authorization

Stream 6 should consume this contract, not create a parallel capability-specific permission evaluator.

Remaining Stream 3 work that can follow later without blocking the first Stream 6 implementation:

- repository-backed membership persistence
- adapter from canonical Project ancestry rather than caller-supplied project paths

### Stream 4: legacy Project + reachability audit

Open PR: #394 `docs: start Stream 4 legacy Project and reachability audit`.

Not a hard implementation dependency. Its findings should be continuously consumed, but Stream 6 does not need to wait for the audit PR to merge before doing its own capability inventory.

Relevant handoff pattern for Stream 6:

- identify capability/security/credential systems that are implemented but off the real production path
- preserve behavior that has real callers
- classify compatibility-only abstractions for later deletion

### Stream 5: graph + durable execution convergence

Not required before Stream 6 can define and implement capability/provider/binding/invocation objects after Stream 1 and Stream 3 are stable.

Stream 5 becomes a consumer of Stream 6 when graph nodes need to invoke capabilities through Bindings. Stream 6 must not depend on GraphRun/durable convergence to establish the capability contract.

### Stream 7: product adapters

Blocked on the canonical spine and on Stream 6 contracts for product paths that expose capabilities/tools. No Stream 7 work is required before Stream 6 starts.

## Merge-order conclusion

Stream 6 should not wait for every stream to merge.

Minimum safe order for implementation:

1. Stream 1 lands canonical Run / NodeRun / Attempt plus `project_id` and Attempt -> ExecutionRuntime seam.
2. Stream 3 lands authorization/resource-scope contract.
3. Stream 6 rebases on current `develop` and implements Binding/Invocation against those contracts.

Strongly preferred before producer migration:

4. Stream 2 canonical EventEnvelope lands, so Invocation emits canonical events from day one.

Not required before Stream 6 starts:

- Stream 4 audit merge
- Stream 5 graph/durable migration
- Stream 7 product adapters

PR #388's ExecutionRuntime foundation also needs to be on the branch Stream 6 consumes if it has not already been absorbed by the canonical Stream 1 work. Stream 6 should rebase after the relevant spine merges rather than cherry-pick partial canonical contracts from several branches.

## Existing capability system on develop

### CapabilityRegistry is useful and should be preserved

`maistro.capabilities.registry.CapabilityRegistry` already provides:

- slot definition
- provider registration
- active provider selection
- enable/disable state
- health checking
- fallback policy
- baseline provider support
- boot validation

This maps cleanly to part of the target Provider-selection layer.

Migration direction:

`CapabilityRegistry slot + Provider` -> canonical `Capability + Provider`

The registry should remain responsible for platform/provider availability. It should not become the owner of consumer authorization, Binding configuration, Invocation lifecycle, or Attempt state.

### Existing capability slots

The core bootstrap currently defines:

- `infra_monitor`
- `infra_action`
- `approval`
- `self_repair`
- `harness_runner`

These are real existing capability families and should become canonical Capability records/projections rather than being replaced with a second registry.

### Existing Provider protocol

`CapabilityProvider` already carries:

- provider name
- slot identifier
- trust tier
- dependency requirements
- async healthcheck

This is a strong base for the canonical Provider concept, but it currently lacks canonical identity/scope/provenance fields and is coupled to a string `slot` instead of a first-class Capability identifier.

Do not break existing providers during the first convergence slice. Add adapters/projections first.

### Provider selection/fallback semantics

Current registry behavior:

- explicit active provider if selected
- otherwise first provider sorted by trust tier
- unhealthy provider falls back according to SlotSpec fallback policy
- SAFE_NOOP can return no provider
- BASELINE can return a baseline provider

This behavior must be preserved in parity tests before canonical provider selection replaces direct registry resolution.

The eventual provider selector should produce an explicit selection result suitable for Invocation provenance, rather than returning only the provider instance.

Required provenance fields should include at least:

- requested capability
- selected provider
- whether selection was explicit/default/fallback
- health/fallback reason
- Binding id
- Invocation id

### Harness system

Harness execution is already one of the most complete examples of capability/provider composition:

- `HarnessRunner` extends CapabilityProvider
- `harness_runner` is a canonical slot
- `HarnessSessionManager` resolves providers through CapabilityRegistry
- `SafeHarnessRunner` wraps providers with Warden and ActionGate/sequence-policy controls
- subprocess harness providers supply concrete fulfillment
- graph `NodeExecutor` can route a node into a harness session

This behavior should be preserved, but the current path predates canonical Binding/Invocation.

Target migration:

`Node -> harness role/executor -> HarnessSessionManager -> CapabilityRegistry -> provider`

becomes:

`Node -> Binding(harness capability) -> provider selection -> Invocation -> Attempt/ExecutionRuntime`

with HarnessSessionManager retained as a protocol/session adapter underneath Invocation where sessionful fulfillment is required.

Do not flatten HarnessSession into Invocation. A single Invocation may start/send/stop against an external session depending on protocol semantics.

### HTTP capability path

`maistro.capabilities.http` and `http_client` are existing fulfillment infrastructure. They should be classified as protocol/provider mechanics, not a second capability ontology.

Target:

`Binding(protocol=http, provider=...) -> Invocation -> HTTP adapter`

The HTTP client should not decide authorization or resource scope.

### Credentials

The credential subsystem is mature operationally but not yet scoped to the canonical ownership hierarchy.

Current `CredentialRecord` contains provider/key operational state such as priority, cooldown, blocking, usage counters, and error counters, but no canonical workspace/project resource scope.

This is exactly where Stream 3's ResourceScope contract should be attached.

Target split:

- Credential metadata/reference: scoped resource owned by Workspace or Project
- secret material: stays in credential store/provider
- Binding: references an authorized credential resource
- Invocation: resolves credential material only after authorization succeeds

Never copy raw `api_key` values into Graph, Node, Binding serialization, Event payloads, or Invocation provenance.

Existing credential pool/rotation behavior should remain provider mechanics.

### Skills and ToolExposure

The repo already has a broad skills framework and portability projections, but there is no canonical first-class `ToolExposure` object on `develop` and no canonical Binding object.

Target:

`SkillDefinition` is decomposed into reusable pieces rather than used as another execution root:

- Capability declaration
- input/output schema
- prompt/tool presentation metadata
- Binding defaults/configuration where portable
- source/trust metadata

`ToolExposure` should be generated from authorized Bindings for a particular consumer context.

A model requesting a tool does not call SkillDefinition or Provider directly:

`ToolExposure -> Binding -> authorization -> provider selection -> Invocation`

### MCP

MCP should remain a protocol/exposure surface.

Two directions must remain distinct:

- outbound: MAIstro consumes an MCP server as a Provider/protocol behind a Binding
- inbound: MAIstro exposes authorized capabilities/tools over MCP

Neither direction should own Run/Attempt lifecycle.

Inbound tool listing must eventually be generated from Bindings visible to the requesting principal/project, not from every installed provider.

### Approval/security

Existing safety systems include at least:

- Warden input scanning
- ActionGate / sequence policy
- approval capability/inbox
- sandboxing for harness/process execution
- provider trust tiers

These controls are valuable but currently compose differently by subsystem.

Canonical Invocation should become the shared enforcement choke point for external/tool/model capability calls.

The ordering should be explicit and testable:

1. resolve Binding visibility
2. authorize requested action
3. resolve credential visibility/use permission
4. apply policy/approval requirements
5. select healthy Provider
6. create Invocation
7. execute through protocol adapter / ExecutionRuntime as appropriate
8. emit canonical events/provenance
9. record terminal result/error

Warden-style content scanning remains protocol/domain-specific preprocessing where appropriate and should not be confused with resource authorization.

## Missing canonical objects on develop

### Binding

No canonical Binding class exists on `develop`.

Binding must eventually own consumer-specific configuration and authorization references, for example:

- binding_id
- workspace_id
- project_id or ResourceScope
- capability_id
- provider constraints/preferences
- protocol configuration
- credential reference(s)
- policy reference(s)
- timeout/retry policy references where domain-owned
- enabled state
- provenance

It must not contain secret values.

### Invocation

No canonical Invocation class exists on `develop`.

Invocation should represent one actual capability fulfillment request and carry correlation/provenance:

- invocation_id
- workspace_id
- project_id
- run_id
- node_run_id
- attempt_id
- binding_id
- capability_id
- selected provider_id
- protocol
- started/finished timestamps
- terminal status
- result/error reference
- provider-selection provenance
- policy/authorization decision references where appropriate

Invocation is not a retry container. Physical retry ownership belongs to Attempt/domain retry policy once Stream 1 defines that boundary.

## Retry ownership conflict to resolve with Stream 1

Current `NodeRun` owns `retry_count`, `max_retries`, and loops attempts internally.

The convergence model says:

`NodeRun -> Attempt[]`

Therefore Stream 6 must not create a second invocation retry loop that competes with NodeRun/Attempt.

Expected separation:

- domain retry policy decides whether another Attempt is allowed
- Attempt is one physical execution attempt
- one Attempt may contain one or more Invocations only when the node's semantics require multiple external calls within that physical attempt
- provider-level transparent fallback may occur inside a single Invocation only if the canonical contract explicitly treats it as fulfillment selection rather than a domain retry; provider changes must remain visible in provenance

This needs to be pinned in Stream 1/Stream 6 integration tests.

## First implementation slices once blockers land

### Slice 1: canonical types and adapters

- add Capability identity projection over existing slot definitions
- add Provider identity/provenance adapter over CapabilityProvider
- add Binding model using Stream 3 ResourceScope
- add Invocation model using Stream 1 Attempt identifiers
- no production caller migration yet

### Slice 2: provider selector

- wrap existing CapabilityRegistry resolution
- return explicit selection provenance
- parity tests for active provider, default selection, unhealthy fallback, BASELINE, SAFE_NOOP

### Slice 3: authorization/credential enforcement

- resolve Binding visibility through Stream 3
- resolve action permission
- resolve credential visibility and `credential:use`
- fail closed before provider execution
- never expose secret material in result/provenance/events

### Slice 4: canonical Invocation executor

- one invocation service/choke point
- protocol adapters for existing HTTP/MCP/harness/provider implementations
- Attempt correlation from Stream 1
- canonical events from Stream 2

### Slice 5: ToolExposure

- generate model-facing tool schema from authorized Bindings
- route requested tool call back through Binding/Invocation
- no direct provider calls from model-facing tool implementations

### Slice 6: migrate existing consumers

Priority migration candidates:

1. harness graph execution
2. MCP/tool paths
3. HTTP integrations
4. skills/tool exposure
5. direct capability consumers that currently call registry/providers themselves

Each migration needs behavior-parity tests before compatibility paths are removed.

## Architecture invariants for Stream 6

- Provider does not own consumer authorization.
- Binding does not widen Workspace/Project permissions.
- Invocation never bypasses Binding authorization for user/project work.
- Credential secret values never enter Graph/Node/Binding/Event/provenance serialization.
- CapabilityRegistry health/fallback semantics are preserved until explicitly superseded with parity coverage.
- ToolExposure is a projection of authorized Bindings, not an execution primitive.
- MCP/HTTP/Harness are protocols/fulfillment mechanics, not alternate Run lifecycles.
- Invocation does not own Run/NodeRun/Attempt lifecycle.
- Stream 6 consumes the canonical Event envelope; it does not create a parallel event bus.
- Persona is not part of authorization resolution.

## Ready condition

Stream 6 is ready to begin implementation when all of the following are true on a common base branch:

- canonical `project_id` ownership/propagation is available
- canonical Run / NodeRun / Attempt contract is available
- Attempt -> ExecutionRuntime seam is available
- Stream 3 authorization/resource-scope contract is available

Canonical EventEnvelope is strongly preferred on the same base before the Invocation executor is wired, but it is not required for initial model/adaptor work.

The capability audit itself is complete enough to begin implementation immediately after those contracts land. No further broad discovery pass is required before Slice 1; remaining reachability findings can arrive continuously from Stream 4.
