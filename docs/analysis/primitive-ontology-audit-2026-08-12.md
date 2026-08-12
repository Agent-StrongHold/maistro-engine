# Primitive-first ontology audit

Date: 2026-08-12
Status: Discovery, non-normative
Branch: `feature/workspace-run-runtime-spine`

## Why this audit exists

The runtime-spine branch began by converging execution around `Workspace -> Run -> ExecutionRuntime -> Capabilities`. That work may remain useful, but it starts too high in the abstraction stack to safely resolve MAIstro's vocabulary sprawl.

This audit derives the architecture bottom-up. The goal is to identify the smallest independently meaningful concepts, recursively decompose higher-order concepts, and find cases where multiple subsystem names are the same concept or one name hides several concepts.

No migration here is normative yet. Do not lock ADR/SPEC/AC until the ontology is sufficiently evidenced.

## Working test for a primitive

A concept is a candidate primitive when it cannot be expressed as a composition of other MAIstro concepts without dropping into ordinary implementation detail. A class, registry, package, database table, protocol, or execution path does not make a concept primitive.

## Working hierarchy

### Level 0: candidate primitives

- **Model**: inference target/model identity.
- **PromptTemplate**: reusable instruction/message structure.
- **ParameterSet**: inference/behavior configuration independent of prompt and model.
- **Schema**: input/output/state/event contract.
- **Protocol**: rules for communicating with or invoking a target.
- **Credential**: authority material used by a binding.
- **PolicyRule**: constraint on an action or transition.
- **Predicate**: condition evaluated against data/state.
- **Transform**: deterministic mapping from input to output.

`Tool`, `Agent`, `Node`, `Graph`, `Run`, `Provider`, `Session`, and `Workspace` are not primitives under current evidence.

### Level 1: semantic capability and fulfillment

Current source supports five separate meanings:

```text
Capability = semantic ability that may be requested
Provider   = selectable implementation of a capability contract
Binding    = consumer-scoped authorized/configured route to fulfillment
Invocation = one concrete runtime use of a resolved Binding
Session    = optional continuity handle across Invocations/Runs
```

A Provider is not a Binding. `CapabilityRegistry` registers multiple providers under a slot, selects active/fallback/trust-ranked providers, and health-checks them. That is implementation resolution. It does not say which Agent may use the capability or with what credentials/policy.

A provisional Binding is:

```text
Binding = Capability
        + target/provider selection
        + Protocol/contract
        + input/output Schema
        + configuration/Credential
        + Policy
```

The minimum fields remain under audit. The invariant is clearer than the representation:

- Capability answers **what may be requested?**
- Provider answers **what implementation can fulfill it?**
- Binding answers **how may this consumer reach authorized fulfillment?**
- Invocation answers **what happened on this specific use?**
- Session answers **what continuity must survive between uses?**

Possible fulfillment forms include local Python/function, HTTP/API, MCP, foreign harness, A2A/local agent, subprocess/sandbox, human interaction, model provider, and graph/subgraph.

### Level 2: intelligence and behavior

```text
Genome = Model + PromptTemplate + ParameterSet
AgentDefinition = identity/classification + Genome
Agent = AgentDefinition + authorized Bindings + Policy
```

Execution/spawn context is not intrinsic Agent identity.

A **Tool** is increasingly supported as a role/view: a Binding or capability exposure rendered into a model-call schema. In `agents/base.py`, `AgentIdentity.tools` is merely a list of names. Those names are transformed into function schemas by `_build_tool_schema()` and passed with a separate `tool_executor` into the reasoning strategy. Tool schema exposure and tool execution are therefore already separate dimensions in source.

Agents-as-tools follows naturally. If Agent A lacks a direct binding for Capability X, it can possess a delegation binding whose target is Agent B. Agent B may have the genome, credentials, context, policy, and direct bindings required to perform X safely and successfully.

```text
Agent A
  -> capability request X
  -> authorized Agent-backed Binding
  -> Agent B
  -> Agent B's direct Binding for X
  -> Invocation
```

No special "agent tool" execution ontology is required.

### Level 3: executable envelope

```text
Node<T> = addressable composition/execution position containing T
```

`T` may be Agent, Binding/invocation adapter, Transform, Human interaction, Graph, foreign harness adapter, or another executable/composition.

Node is not synonymous with LLM call, Agent, Tool, or Graph. Current `NodeRun.executor` can replace the default LLM path entirely, which is direct evidence that graph position and fulfillment backend are independent dimensions.

### Level 4: composition

```text
Edge  = SourceNode + TargetNode + Predicate + DataMapping
Graph = Nodes + Edges
```

Graph is composite. A Graph may itself occupy a Node, allowing recursive composition without creating a second graph execution ontology.

Workflow, team, fleet, wave, pipeline, and recipe remain candidates for product/authoring views over Graph + policy unless a distinct invariant is found.

### Level 5: execution lifecycle

```text
WorkRequest = desired work + inputs + constraints + scheduling intent
Run         = one execution instance of an executable/composition
Attempt     = one retry-bounded attempt within Run/Invocation
Invocation  = one concrete use of a Binding
Checkpoint  = persisted event/snapshot from Run state
Recovery    = replay/resume procedure + policy over Checkpoints
Session     = separate continuity axis that may span Runs
```

Events, artifacts, metrics, retry state, correlation, lineage, checkpoints, and child runs attach to Run. They do not make `GraphRun`, `NodeRun`, `Task`, `A2ATask`, or harness session separate root execution ontologies by default.

### Level 6: ownership/product organization

```text
Workspace = ownership/container boundary over definitions, runs, artifacts,
            credentials and policy
```

Workspace is likely canonical at the product boundary but is not an execution primitive.

## Confirmed sprawl findings

### 1. `HarnessRunner` is duplicated and drifted

Core defines `HarnessRunner` in both `maistro.capabilities.protocols` and `maistro.capabilities.slots.harness_runner`. One path accepts `AgentIdentity`; the slot path accepts `AgentSpec`.

`HarnessSessionManager` resolves a provider from `CapabilityRegistry`, starts a harness session, wraps it with safety/policy, and retains a session handle for `send/stream/stop`. The slot's own documentation explicitly says the foreign harness installs/toggles/degrades like any other capability provider and normalizes responses into MAIstro's existing envelope.

**Canonical direction:** one harness Provider/Protocol. Agent authorization/configuration belongs in Binding. The harness session ID is a remote continuity handle, not a new Run identity by itself.

**Action:** MERGE duplicate protocols; RETAIN harness-session semantics as Provider/Session detail.

### 2. Agent definitions mix ontology levels

`AgentIdentity` includes prompt/model/tool/skill/rule policy, trust, delegation, strategy, memory, phases, provenance, and review state. `AgentSpec` additionally carries task IDs, attempt, upstream outputs, lane/scheduling and tracing/spawn context.

**Canonical direction:** split reusable AgentDefinition/Genome from Bindings/Policy and from per-run invocation/spawn context.

**Action:** DECOMPOSE.

### 3. Tool exposure is not tool fulfillment

`agents/base.py` converts the names in `AgentIdentity.tools` to model-facing function schemas. The reasoning strategy receives both `tools=tool_defs` and a separate `tool_executor`.

That is strong source evidence that "Tool" currently conflates at least two things:

```text
ToolExposure = model-facing name + description + input schema
Binding      = authorized/configured fulfillment route
Invocation   = concrete execution through that route
```

A ToolExposure may reference a Binding, but it should not own execution semantics.

**Action:** DECOMPOSE current Tool vocabulary; formalize ToolExposure/Binding boundary before implementation migration.

### 4. Agent-to-agent delegation is duplicated at least four ways

Current source contains overlapping delegation concepts:

1. `types.agent.AgentTask`, described as an "A2A-shaped task" with sender, target, messages, execution mode, token budget, status, result, and trace.
2. `a2a.delegate.A2ATask` plus `A2ADelegator`, with a second TaskStatus state machine and its own in-memory task registry/capability allow-list.
3. `a2a.broker.A2ABroker`, which constructs another `A2ATask`, applies delegation budget/trust/allow-list policy, and invokes an injected `Transport`.
4. `Agent._delegate()` in `agents/base.py`, which resolves another `Agent` directly and recursively calls `target.handle()` with its own delegation-depth guard.

These are not four distinct architectural invariants. They are parallel implementations of Agent-backed fulfillment plus policy and lifecycle projection.

`A2ABroker` is particularly informative: it already separates `AgentInvoker` from `Transport`, carries a delegation budget/policy envelope, and returns a `DelegationResult`. That maps cleanly onto Agent-backed Binding + Protocol/Transport + Invocation + Policy.

**Canonical direction:**

```text
Agent-backed Binding
  target = AgentDefinition/Agent endpoint
  protocol = local-call | A2A/federated transport
  policy = delegation allow-list + trust + budget + loop guard
  invocation = delegated capability use
```

`A2ATask` should become a protocol/Run projection only where independent delegated lifecycle is required, not a second universal Task aggregate.

**Action:** MERGE delegation mechanisms behind one Binding/Invocation path; VIEW/DECOMPOSE `AgentTask` and `A2ATask`; RETAIN transport and delegation policy semantics.

### 5. Human approval already behaves like a capability provider

`capabilities.slots.approval.Approval` extends `CapabilityProvider` and exposes one typed operation: `request(ApprovalRequest) -> ApprovalDecision`.

The semantic difference from an HTTP, harness, or agent-backed capability is who/what fulfills the request and whether execution may pause while waiting. That does not justify a separate invocation root.

**Canonical direction:** human approval is a human-backed Binding/Provider with typed input/output and pause/resume behavior. A Human Approval Node remains useful graph/product vocabulary when that binding occupies a Node.

**Action:** KEEP Approval contract semantics; map to Capability/Provider/Binding/Invocation; KEEP HumanApprovalNode only as a Node specialization/view.

### 6. HTTP is a protocol/transport seam, not a capability ontology

`capabilities.http_client.HttpxAsyncHttp` is explicitly the concrete implementation of an `AsyncHttp` protocol injected into HTTP-backed providers. It carries base URL, bearer-token configuration, timeout, and transport, then performs GET/POST operations.

This cleanly separates HTTP transport from semantic capability. A provider can be HTTP-backed without "HTTP tool" becoming a new architecture.

**Canonical direction:** HTTP/API is Protocol + target/configuration used by a Provider/Binding. Invocation remains the runtime call.

**Action:** KEEP transport seam; do not create a parallel HTTP execution abstraction.

### 7. Agent role is defined more than once

`maistro.graph.types.AgentRole` and `maistro.agents.spec.agent_spec.AgentRole` are separate enums with overlapping but non-identical members.

**Canonical direction:** role is Agent/composition classification metadata, not Node identity or execution identity.

**Action:** MERGE/RENAME after usage inventory.

### 8. Graph `ExecutionMode` encodes composition kinds as execution kinds

Graph `ExecutionMode` distinguishes `TASK`, `WORKFLOW`, `AGENT`, and `GRAPH`. These are executable/product-definition kinds, not necessarily different execution mechanisms.

**Action:** DECOMPOSE/REMOVE candidate.

### 9. `NodeConfig` mixes node envelope and payload definition

`NodeConfig` carries role/kind plus prompt, temperature, model, max tokens, confidence, display name, and beam width.

**Canonical direction:** Node should be payload-agnostic; model/prompt/parameters belong to Genome/payload definition.

**Action:** DECOMPOSE.

### 10. `NodeRun` mixes Node, Run, Attempt, Invocation and telemetry

`NodeRun` includes node identity, model/prompt parameters, backend selection, retry state, timing, token accounting, parsed output, errors, circuit breaking and event emission. Its arbitrary `NodeExecutor` override proves node position and backend are separable.

**Action:** DECOMPOSE into Node ref/payload + child execution fact + Attempt/Invocation + telemetry.

### 11. Edge mixes topology with learned/runtime policy

`GraphEdge` contains source/target/condition plus parallel, weight, trust, sign and staleness decay.

**Canonical direction:** derive minimal topology Edge, then layer optimizer/policy annotations.

**Action:** DECOMPOSE candidate.

### 12. Task is WorkRequest + Run projection

`TaskCreate` contains desired work and scheduling/configuration intent. `TaskResponse` adds lifecycle, progress, result and timestamps. `TaskRunner` drives lifecycle and dispatch. `TaskStatus` mixes universal states with domain phases such as planning/coding/review/testing.

**Action:** DECOMPOSE Task into WorkRequest + Run view; move scheduling to scheduler/admission policy and domain phases to progress events/executable state.

### 13. `RunContext` is identity/lineage context, not full Run aggregate

`runtime.types.RunContext` carries run ID, workspace, kind, lifecycle state, lineage, actor, correlation and metadata. `ExecutionContext` adds propagated services. Graph durable state is persisted elsewhere.

**Action:** KEEP/REFINE Run identity/context; distinguish it from mutable persisted Run state.

### 14. Durable graph runs are specialized persisted Run views

`DurableRunRecord` and `DurableNodeRecord` store graph-specific snapshots, node state, outputs, pause metadata, attempts, costs and errors while carrying canonical run lineage.

**Action:** MERGE/VIEW under canonical Run + GraphRunState rather than preserving a second root lifecycle.

### 15. General Session is conversation continuity

The general session store retains ordered conversation messages with TTL/retention. A conversation may span Runs, and a Run need not have a conversation.

Harness session IDs are a different session specialization: remote process/turn-loop continuity.

**Canonical direction:** Session is a continuity concept with explicit kinds, not a synonym for Run.

**Action:** KEEP/CLARIFY.

### 16. Checkpoint/replay/recovery are Run services

`TaskCheckpoint`, replay state reconstruction, crash-loop quarantine, and version compatibility are valid semantics currently keyed through Task.

**Action:** RETAIN semantics and REHOME under canonical Run/Attempt identity.

### 17. `Strategy` is overloaded

Graph `NodeStrategy` primarily shapes prompts/output, while agent strategies implement reasoning/control approaches.

**Action:** RENAME at least one family.

## Repository sprawl matrix, current evidence

| Current concept | Actual responsibility | Canonical mapping | Action |
|---|---|---|---|
| `CapabilityProvider` | implementation metadata/health + slot protocol | Provider | KEEP |
| `CapabilityRegistry` | capability-slot catalog + provider selection/fallback | Capability catalog + Provider resolver | KEEP/RENAME candidate |
| duplicated `HarnessRunner` | foreign harness provider/session protocol | Provider + Protocol + Session handle | MERGE |
| `HarnessSessionManager` | provider resolution + safety/policy + remote continuity | Binding/Provider adapter + Session manager | DECOMPOSE/REHOME |
| `Approval` | typed human approval provider | human-backed Provider/Binding | KEEP/MAP |
| `AsyncHttp` / `HttpxAsyncHttp` | transport protocol + configured implementation | Protocol/transport | KEEP |
| `AgentIdentity.tools` | names of model-visible actions | Binding references / ToolExposure declarations | DECOMPOSE |
| `_TOOL_SCHEMAS` / `_build_tool_schema` | render model-facing function schemas | ToolExposure | KEEP/REHOME |
| `tool_executor` | actual tool dispatch path | Binding resolver/invoker | RENAME/CONVERGE |
| `AgentTask` | A2A-shaped delegated task + status/result | delegated WorkRequest/Run projection | DECOMPOSE/VIEW |
| `A2ATask` | second delegated task lifecycle | delegated Invocation/child-Run projection | DECOMPOSE/VIEW |
| `A2ADelegator` | delegation allow-list + routing + task registry | Binding authorization/routing + duplicate lifecycle | DECOMPOSE/MERGE |
| `A2ABroker` | delegation policy + target resolution + transport | Agent-backed Binding resolver/invoker | RETAIN semantics, CONVERGE |
| `Agent._delegate()` | direct local sub-agent invocation | local Agent-backed Binding invocation | MERGE |
| `DelegationBudget` | deadline/token/depth/cycle policy | Invocation/Binding Policy | KEEP/REHOME |
| `Transport` / `LocalTransport` | delegation wire/invocation mechanism | Protocol/Transport | KEEP |
| `AgentIdentity` | reusable identity plus genome/tool/policy concerns | AgentDefinition + Genome + Bindings/Policy | DECOMPOSE |
| `AgentSpec` | spawn definition plus task/attempt/upstream/tracing context | AgentDefinition + Run/Invocation context | DECOMPOSE |
| multiple `AgentRole` | divergent classification labels | Agent/composition metadata | MERGE/RENAME |
| `NodeConfig` | Node plus embedded LLM/prompt/behavior config | Node + payload/Genome config | DECOMPOSE |
| `NodeRun` | node execution + retry/result/telemetry | Node ref + Run/Attempt/Invocation | DECOMPOSE |
| `NodeExecutor` | alternate backend for a node turn loop | executable/fulfillment protocol | RETAIN, map to Binding/provider boundary |
| graph `ExecutionMode` | task/workflow/agent/graph labels | executable/product kind | REMOVE/REDEFINE candidate |
| `TaskCreate` | desired work + scheduling/target hints | WorkRequest | RENAME/DECOMPOSE |
| `TaskResponse` | request + lifecycle/progress/result | WorkRequest + Run view | DECOMPOSE |
| `TaskStatus` | universal lifecycle + domain phases | RunState + Progress/Phase | DECOMPOSE |
| `TaskRunner` | queue/worker/dispatch/state transitions | Scheduler/Dispatcher + Run launcher | DECOMPOSE/REHOME |
| `RunContext` | run identity/ownership/lineage/correlation | RunIdentity/RunContext | KEEP/REFINE |
| `ExecutionContext` | propagated RunContext + services | execution propagation context | KEEP/REFINE |
| `DurableRunRecord` | persisted graph run state | Run + GraphRunState | MERGE/VIEW |
| `DurableNodeRecord` | persisted child node execution | Node ref + child execution state | DECOMPOSE/VIEW |
| session store | conversation continuity/retention | Session | KEEP/CLARIFY |
| `TaskCheckpoint` | sequenced recovery fact | Checkpoint/Event | REHOME |
| `ResumeState` / replay | reconstruction from checkpoints | Run state reconstruction | KEEP/REHOME |
| `CrashLoopPolicy` | quarantine/recovery decision | RecoveryPolicy/PolicyRule | KEEP/REHOME |
| Graph/DAG | composition + graph-specific overlays | Graph = Nodes + Edges + annotations | KEEP/DECOMPOSE overlays |

## Emerging fulfillment model

The strongest convergence from this pass is:

```text
Capability
  "what can be requested"
      |
      v
Provider
  "what implementation can do it"
      |
consumer authorization/configuration
      v
Binding
  capability + target/provider + protocol + schemas + credentials + policy
      |
      v
Invocation
  one concrete runtime use
      |
      +-- optional Session continuity
      +-- Attempt/retry facts
      +-- events/telemetry/artifacts
```

A model-visible Tool is an exposure of a Binding/Capability contract. It is not the Binding itself and not the Invocation.

Fulfillment targets can differ without creating parallel architectures:

```text
Binding target/provider
  +-- local function/tool
  +-- HTTP/API service
  +-- MCP server/tool
  +-- Agent
  +-- foreign harness
  +-- human
  +-- model provider
  +-- subprocess/sandbox
  +-- graph/subgraph
```

This is now source-supported for local model tools, HTTP-backed providers, human approval, foreign harnesses, and local/A2A agent delegation. MCP still needs direct source inspection before claiming complete convergence.

## Emerging lifecycle

```text
WorkRequest
  -> selects/produces Executable definition
        |
        v
Run
  identity + ownership + lineage + correlation
  executable reference + inputs
  mutable lifecycle + outputs/artifacts
  events/checkpoints
        |
        +-- Attempt(s)
        +-- Invocation(s)
        +-- child Run(s) only where independent lifecycle/lineage is required

Session
  separate continuity axis that may span Invocations/Runs
```

The unresolved rule is when a Node execution or delegated Agent call deserves a child Run versus being an Invocation/Attempt inside the parent Run. Decide from independent lifecycle, ownership, resumability, observability and lineage requirements, not class names.

## Canonical vocabulary, provisional

| Term | Meaning | Layer |
|---|---|---|
| Model | inference model identity/target | primitive |
| PromptTemplate | reusable prompt/message template | primitive |
| ParameterSet | behavior/inference parameters | primitive |
| Schema | typed data contract | primitive |
| Protocol | interaction/invocation rules | primitive |
| Credential | authority used by Binding | primitive |
| PolicyRule | constraint on action/transition | primitive |
| Predicate | conditional decision | primitive |
| Transform | deterministic mapping | primitive |
| Capability | semantic ability that may be requested | semantic contract |
| Provider | selectable implementation | implementation |
| Binding | consumer-scoped authorized/configured route to fulfillment | composition |
| ToolExposure | model-visible presentation of an available capability/binding | role/view |
| Invocation | one runtime use of a Binding | runtime fact |
| Genome | Model + PromptTemplate + ParameterSet | composition |
| AgentDefinition | durable identity/classification + Genome | definition |
| Agent | AgentDefinition + authorized Bindings + Policy | composition |
| Node | addressable envelope containing executable/composition | composition primitive candidate |
| Edge | topology + minimal predicate/mapping | composition |
| Graph | Nodes + Edges | composition |
| WorkRequest | desired work + inputs/constraints/scheduling intent | request/product |
| Run | execution instance of an executable/composition | runtime aggregate |
| Attempt | retry-bounded execution attempt | runtime child fact |
| Session | continuity across interactions | context axis |
| Checkpoint | persisted event/snapshot for resume/recovery | runtime persistence |
| Workspace | ownership/product boundary | organizational |

## Migration rule

Do not create a new architectural noun when an existing canonical concept plus specialization/metadata expresses the same invariant.

Classify every existing noun as:

- **KEEP**: already matches one canonical meaning.
- **MERGE**: semantic duplicate.
- **RENAME**: valid concept with misleading/overloaded name.
- **DECOMPOSE**: combines ontology layers.
- **VIEW**: useful UX/product term derived from canonical concepts.
- **REMOVE**: no distinct invariant remains.
- **REHOME**: semantics valid but lifecycle/package ownership is wrong.

## Next inventory pass

Continue in this order:

1. MCP tool/server/client and integrations to finish ToolExposure/Binding/Provider/Invocation evidence.
2. Human/HITL graph node implementations to verify Node specialization vs separate lifecycle.
3. Harness node executors and session/process handles to finish Node-to-Binding mapping.
4. `AgentIdentity`, `AgentSpec`, `AgentCard`, recipes and prompt/model configuration to fully derive Genome/AgentDefinition boundaries.
5. Graph Node/Edge/Graph definition types versus executor state.
6. scheduled execution, orchestration wave/fleet/team lifecycle.
7. RSI/evolve genome/cycle/pipeline concepts.
8. state/event/artifact vocabulary.
9. workspace/project persistence boundary.

Do not write a normative ADR/SPEC yet. MCP and AgentDefinition/Genome evidence can still materially change the lower hierarchy.

## Effect on the current runtime-spine branch

Existing Workspace, run identity/lineage/context propagation, and capability-provider work may remain reusable. Do not force additional execution paths through `ExecutionRuntime` merely to satisfy the earlier spine shape until the audit determines whether `ExecutionRuntime` itself is canonical, an orchestration service over Run/Binding/Invocation, or another abstraction to decompose.

Preserve working commits, avoid destructive rollback, and let the ontology determine the next implementation slice.