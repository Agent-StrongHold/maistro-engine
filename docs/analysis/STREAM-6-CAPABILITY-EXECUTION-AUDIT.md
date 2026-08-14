# Stream 6 Capability Execution Audit

Date: 2026-08-14
Branch: `audit/stream-6-capability-execution`
Baseline: `develop`

## Purpose

Prepare the capability-execution stream without defining canonical interfaces ahead of the core spine or authorization streams.

Stream 6 owns the convergence of:

`Capability -> Provider -> Binding -> Invocation -> Attempt -> ExecutionRuntime`

plus credentials, ToolExposure, MCP, HTTP, harness execution, provider health/fallback, and the security/tool machinery that must sit on the real invocation path.

This audit does not introduce Binding, Invocation, Attempt, or authorization semantics while those contracts are still owned by other streams. Safe pre-implementation work may add characterization tests that pin behavior the later convergence must preserve.

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

### Stream 2: events/checkpoints

The canonical EventEnvelope is strongly preferred before Stream 6 migrates real invocation producers because Invocation should not invent another event/correlation representation.

Stream 6 can define static adapters/types after Stream 1/3 without waiting for the complete checkpoint/outbox implementation.

### Stream 3: authorization/resources

Required before real Binding/Invocation enforcement.

Needed contracts:

- WorkspaceMembership / ProjectMembership resolution
- workspace/project resource visibility
- credential scope
- Binding scope
- policy scope
- explainable authorization decision seam

Persona must remain absent from authorization.

### Streams 4, 5, and 7

These are not prerequisites for initial Stream 6 implementation.

- Stream 4 continuously supplies reachability/migration findings.
- Stream 5 consumes the canonical capability path as graph/durable execution converges.
- Stream 7 consumes it from products/services/UI.

## Current capability execution inventory

### Capability registry

`maistro.capabilities.registry.CapabilityRegistry` already provides substantial behavior worth preserving:

- slot definitions
- provider registration
- explicit activation
- enable/disable state
- health checks on resolution
- fallback policies
- baseline providers
- trust-tier-based implicit selection
- boot validation for hard-required slots

This should be adapted into the canonical model rather than replaced wholesale.

### Capability provider protocol

`maistro.capabilities.protocols.CapabilityProvider` already defines useful provider metadata/mechanics:

- `name`
- `slot`
- `trust_tier`
- `requires()`
- `healthcheck()`

The eventual canonical Provider can wrap/normalize this behavior. Provider health is provider-selection mechanics, not Run/Attempt lifecycle.

### Current canonical-slot bootstrap

`maistro.capabilities.bootstrap.default_capability_registry()` currently defines:

- `infra_monitor`
- `infra_action`
- `approval`
- `self_repair`
- `harness_runner`

This is an existing capability inventory, not the complete future product Capability set.

### Harness execution

Harness is the most complete existing example of the future capability path.

Current shape:

`Node -> NodeExecutor/HarnessNodeExecutor -> HarnessSessionManager -> CapabilityRegistry -> HarnessRunner provider`

Preserve:

- provider abstraction
- health/fallback behavior
- Warden input filtering
- action-policy gating
- session cleanup
- sandbox/microVM boundary
- typed unavailable behavior

Converge later to:

`Node -> Binding -> authorization -> Provider selection -> Invocation -> Harness adapter -> Attempt/ExecutionRuntime`

Do not preserve HarnessSessionManager as a second universal execution lifecycle.

### HTTP

`maistro.capabilities.http_client` and HTTP-backed providers are execution mechanisms/providers.

They should become provider implementations behind Binding/Invocation, not a parallel lifecycle.

Preserve HTTP transport behavior, timeouts, errors, health checks, and safety controls.

### Credentials

`maistro.credentials` currently contains provider/store/pool/rotation mechanisms and credential records.

Preserve:

- secret storage/provider abstraction
- rotation/pool mechanics
- availability/cooldown behavior
- references to credentials

Do not place credential secret values onto Node, Graph, Binding, Run, Event, or Invocation records.

Once Stream 3 lands resource scope, credentials should be selected through authorized scoped references.

### Skills and ToolExposure

Existing skills/tool/MCP surfaces contain descriptions, schemas, adapters, handlers, and exposure mechanisms.

Canonical target:

- Skill/package metadata may describe reusable behavior.
- Capability describes what can be done.
- Provider implements a Capability.
- Binding authorizes/configures a Node to use it.
- ToolExposure projects authorized Bindings into model-consumable tool schemas.
- Invocation records an actual use.

ToolExposure must not become another capability registry or authorization source.

### MCP

MCP is a provider/interface protocol, not a new universal execution object.

Preserve:

- discovery
- schemas
- server/client adapters
- transport
- health
- tool-call conversion

Route actual calls through Binding -> Provider -> Invocation.

### Approval/security/policy

Existing Warden, Sentinel/policy, ApprovalGate, SafeHarnessRunner, and sequence-policy machinery contain useful enforcement behavior.

The migration rule is:

- authorization answers whether a principal/Node may use a Binding/resource
- policy evaluates contextual constraints on a permitted action
- approval can suspend/continue a permitted Invocation when policy requires it
- provider safety wrappers enforce provider-specific safety boundaries

Do not merge these concepts into one generic permission object.

## Existing execution systems that must not become canonical by accident

### `NodeExecutor`

Useful specialized backend seam, but not the canonical Invocation contract.

### `HarnessSessionManager`

Useful harness adapter/session machinery, but not universal Run/Attempt ownership.

### `CapabilityRegistry.resolve()`

Useful provider-selection implementation, but currently lacks canonical Binding authorization and Invocation provenance.

### credential pool selection

Useful provider-key mechanics, but not authorization and not provider selection by itself.

## Preservation map

| Existing behavior/system | Canonical destination | Action |
| --- | --- | --- |
| Capability slot | Capability | normalize/adapt |
| CapabilityProvider | Provider | preserve/adapt |
| CapabilityRegistry | provider inventory/selection implementation | preserve behind canonical seam |
| registry active provider | Binding/provider preference or provider-selection input | migrate carefully |
| provider health | provider selection | preserve |
| fallback policy | provider selection | preserve |
| HarnessRunner | Provider protocol | preserve |
| HarnessSessionManager | provider adapter mechanics | narrow |
| HarnessNodeExecutor | graph-to-capability compatibility adapter | migrate/remove after canonical path |
| HTTP client/providers | Provider mechanics | preserve |
| CredentialProvider/store | credential infrastructure | preserve |
| CredentialPool | provider credential mechanics | preserve |
| Skill/MCP tool schema | ToolExposure input | adapt |
| Warden | invocation safety boundary | preserve |
| SequencePolicyEngine | policy evaluation | preserve |
| ApprovalGate | invocation approval seam | preserve |
| Graph `NodeExecutor` retry/cancel interaction | Attempt lifecycle | consume Stream 1 semantics, do not redefine |

## Required canonical inputs before implementation

### From Stream 1

Stream 6 needs an authoritative answer for:

1. How a new Attempt is created for a NodeRun.
2. Whether one Invocation maps one-to-one to an Attempt or whether an Attempt may contain multiple lower-level provider operations.
3. Where retry creation occurs.
4. How cancellation/deadline reaches the physical provider call.
5. How Invocation output/error is returned to Attempt terminalization.
6. Which IDs are required at execution entry (`workspace_id`, `project_id`, `run_id`, `node_run_id`, `attempt_id`).

Stream 6 must consume these answers, not invent them.

### From Stream 3

Stream 6 needs:

1. permission required to use a Binding
2. project/workspace resource-scope representation
3. credential visibility/use permission
4. policy visibility/use permission
5. project ancestry lookup adapter or accepted caller-supplied path contract
6. explainable deny result suitable for Invocation rejection

## Safe work before blockers land

The following are safe because they characterize or adapt existing behavior without defining a canonical choke point:

- provider registry behavioral-parity tests
- provider health/fallback characterization
- Harness provider-path characterization
- HTTP/provider error-mapping characterization
- credential-reference inventory and leak tests
- MCP/tool-schema inventory
- existing caller/reachability mapping
- compatibility adapters that remain intentionally ignorant of Binding/Invocation IDs

Do not add canonical Binding/Invocation records merely to make these tests compile.

## Provider selection parity floor

Stream 6 now has executable characterization tests in:

`packages/maistro-core/tests/capabilities/test_stream6_provider_parity.py`

They pin five existing behaviors that the canonical Binding/Invocation path must preserve unless an explicit architecture decision changes them:

1. an explicitly activated healthy provider wins even when another provider has a lower trust tier;
2. an unhealthy active provider falls back to the declared baseline for `BASELINE` slots;
3. disabling a `BASELINE` slot resolves to its baseline rather than its active primary;
4. an unhealthy active provider resolves to typed absence (`None`) for `SAFE_NOOP` slots;
5. when no provider is explicitly activated, implicit selection prefers the lowest trust tier.

These tests intentionally exercise only current provider-selection mechanics. They do not define Binding, Invocation, authorization, Attempt, events, or retry semantics.

## First implementation slices after unblock

### Slice 1: canonical static objects/adapters

Once Stream 1 and Stream 3 contracts are merged:

- Capability adapter over existing slot definitions
- Provider adapter over existing CapabilityProvider implementations
- Binding with workspace/project scope and credential references
- Invocation request/result identity/provenance fields
- no production caller switch yet

### Slice 2: authorized provider selection

- resolve Binding visibility/use permission
- resolve credential visibility/use permission
- select healthy Provider/fallback
- return an explainable failure if no authorized provider is available

### Slice 3: Attempt integration

- invoke provider under the existing Stream 1 Attempt
- propagate deadline/cancellation from ExecutionRuntime seam
- no retry loop inside Invocation if Attempt owns retries

### Slice 4: events

- emit canonical invocation/provider-selection events through Stream 2 EventEnvelope
- correlate workspace/project/run/node_run/attempt/invocation IDs

### Slice 5: adapters

Migrate, one at a time:

- Harness
- HTTP
- MCP tools
- native tools/skills
- LLM/provider path where applicable

Behavior-parity tests must stay green while compatibility layers are removed.

## Merge order

Required common-base order for production Stream 6 work:

1. Stream 1 canonical Run/NodeRun/Attempt seam onto `develop`
2. Stream 3 authorization/resource-scope contract onto `develop`
3. Stream 6 rebase/branch from that common `develop`
4. Stream 2 EventEnvelope should be consumed before real producer migration if available

Stream 4, 5, and 7 do not need to merge first.

Avoid cherry-picking partial canonical contracts into Stream 6. Canonical choke points should reach the common integration branch before consumers build on them.

## Exit condition for pre-implementation phase

Stream 6 is ready to leave audit/characterization mode when all are true:

- canonical Attempt exists on `develop`
- Attempt -> ExecutionRuntime execution seam is authoritative
- `project_id` ownership/propagation is authoritative
- Stream 3 authorization/resource-scope contract is on `develop`
- provider-selection parity tests are green

At that point Stream 6 should begin Slice 1 immediately rather than perform another broad architecture audit.
