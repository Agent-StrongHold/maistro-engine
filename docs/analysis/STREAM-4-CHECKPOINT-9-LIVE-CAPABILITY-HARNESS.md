# Stream 4 Checkpoint 9: Live Capability and Harness Paths

Date: 2026-08-14
Source audited: `develop`

This checkpoint distinguishes the genuinely live capability-provider infrastructure from canonical Binding/Invocation concepts that do not yet exist, and traces the mounted inbound harness route through its actual safety/policy wiring.

## 1. Hive Capability API is live and backed by the engine registry

Mounted `routes/capabilities.py` resolves the shared engine `CapabilityRegistry` and exposes:

- capability slots
- installed providers
- provider health views
- rediscovery without restart
- enable/disable
- active provider selection
- persisted operator activation settings
- approval inbox list/resolve
- self-repair proposal/run surfaces

This is not a dead capability island.

Classification: `live provider registry/product control surface`.

## 2. CapabilityRegistry contains useful provider resolution/fallback behavior

Core `CapabilityRegistry` provides:

- slot definitions
- provider registration
- explicit activation
- enable/disable kill switch
- active provider selection
- trust-tier fallback when no provider is explicitly active
- provider healthcheck on resolve
- baseline-provider fallback according to slot policy
- hard-required boot validation

These are real Provider/Capability mechanics worth preserving.

They are not equivalent to canonical Binding/Invocation because resolution currently answers roughly:

> which provider is active/healthy for this slot?

It does not answer:

> which Project-scoped Binding, credential, authorization decision, and provider should this Attempt invoke?

### Stream 6 migration constraint

Do not discard the registry merely because Binding/Invocation is added. Insert canonical scoping/execution around or above the useful slot/provider machinery.

## 3. App capability wiring currently resolves some credentials at provider construction

`services.capabilities_wiring` registers host-health infrastructure providers when configured and resolves `HOST_HEALTH_TOKEN` from a vault/config fallback while constructing the provider.

It also builds self-repair from registered infra monitor/action providers.

This is appropriate for deployment/operator-level providers, but it is evidence that credential ownership currently varies by provider and is not uniformly represented by a Binding.

### Stream 6 handoff

Canonical credential resolution must distinguish at least:

- deployment/operator service credentials
- user-owned credentials
- Workspace/Project-scoped resource credentials

Do not force every existing deployment secret into a user credential model merely for uniformity.

## 4. Mounted inbound Harness API is a live capability consumer

`routes/harness.py` exposes:

- start session
- send turn
- SSE stream
- stop session

It lazily constructs a process-wide `HarnessSessionManager` over:

- engine CapabilityRegistry
- Warden

Hive AuthMiddleware separately requires `harness.execute` for mutating harness routes.

Classification: `live capability execution surface`.

## 5. HarnessSessionManager already separates provider resolution from safety wrapping

Core `HarnessSessionManager.start()`:

1. resolves the live `harness_runner` provider through CapabilityRegistry
2. starts the provider session
3. wraps that provider in `SafeHarnessRunner`
4. applies Warden scanning
5. optionally applies a per-session `PolicyActionGate` if a `SequencePolicyEngine` was supplied

Missing/unhealthy provider becomes typed `Unavailable`, preserving SAFE_NOOP behavior.

This is valuable existing structure for Stream 6.

## 6. Runtime sequence policy is supported by the manager but not wired on the live Hive route

The mounted route constructs:

`HarnessSessionManager(get_engine().capabilities, warden=Warden())`

It does **not** pass a `SequencePolicyEngine`.

Therefore `HarnessSessionManager._policy` is `None`, and the live inbound harness session does not construct a `PolicyActionGate`.

### Important truth-status distinction

Live inbound harness currently has:

- authentication / `harness.execute` outer permission
- provider slot resolution/fallback
- Warden safety scanning

It does **not** currently have the optional sequence-aware runtime action-budget gate through this path.

Do not describe SequencePolicyEngine/PolicyActionGate as active harness enforcement until it is actually wired.

Classification: `implemented optional policy seam, behaviorally unwired on mounted route`.

## 7. Harness session state is another lifecycle that should remain subordinate to Invocation

`HarnessSessionManager` keeps an in-memory map of `session_id -> SafeHarnessRunner` and exposes start/send/stream/stop.

A long-lived interactive harness session is a real concept that may remain distinct from Run in the UX/domain, but execution initiated through it still needs canonical Invocation/Attempt provenance once convergence lands.

### Stream 6 direction

Preserve session protocol where useful. Do not make the session manager the source of truth for:

- Project authorization
- credential ownership
- Attempt lifecycle
- invocation accounting/correlation

## 8. Capability approval inbox is runtime/operator approval, not Project membership

The mounted capability routes expose an approval provider's pending requests and resolve them.

This reinforces the Stream 3/6 layering established in Checkpoint 7:

- Project/resource authorization decides whether the principal may reach the resource/capability.
- approval/elevation can decide whether a high-risk authorized action may execute now.

Do not merge the inbox into membership grants/denies.

## Immediate handoffs

### Stream 3

Keep outer `harness.execute` compatibility while canonical resource authorization is introduced. Approval inbox and Warden are not substitutes for Project authorization.

### Stream 6

Preserve:

- CapabilityRegistry slot/provider health and fallback
- SAFE_NOOP / baseline behavior
- HarnessSessionManager provider-resolution seam
- Warden safety wrapper
- long-lived harness session transport if product needs it

Add canonical:

- Binding/resource scope
- authorization enforcement
- credential reference/resolution
- Invocation tied to Attempt
- canonical Event/usage correlation
- optional runtime policy wiring where desired

### Stream 7

Capability/harness web APIs are live product surfaces and should become projections/consumers of canonical Binding/Invocation rather than being replaced blindly.

## Reachability truth rule reinforced

A feature can be structurally reachable while one advertised enforcement path inside it remains unwired. The harness route demonstrates why module reachability is a floor, not proof of behavioral integration.
