# Primitive-first ontology audit

Date: 2026-08-12
Status: Discovery, non-normative
Branch: `feature/workspace-run-runtime-spine`

## Why this audit exists

The runtime-spine branch began by converging execution around `Workspace -> Run -> ExecutionRuntime -> Capabilities`. That is useful infrastructure work, but it starts too high in the abstraction stack to solve MAIstro's vocabulary sprawl safely.

Before extending that implementation, this audit derives the architecture bottom-up. The goal is to identify the smallest independently meaningful concepts, show how higher-order concepts compose from them, and find cases where multiple subsystem names are actually the same concept or one name hides several different concepts.

This document is intentionally discovery rather than an ADR or SPEC. No migration should be treated as decided until the ontology is stable enough to make the decision explicit.

## Working test for a primitive

A concept is a candidate primitive when it cannot be expressed as a composition of other MAIstro concepts without dropping into ordinary implementation detail.

A concept is not primitive merely because it has a class, protocol, package, registry, database table, or execution path today.

## Working hierarchy

### Level 0: candidate primitives

These are the current bottom-layer candidates. The audit may reduce this list further.

- **Model**: an inference target/model identity.
- **PromptTemplate**: reusable instruction/message structure with substitution points.
- **ParameterSet**: inference/behavior configuration independent of the prompt and model.
- **Schema**: a data contract for input, output, state, or events.
- **Protocol**: rules for communicating with or invoking a target.
- **Credential**: authority material used by a binding.
- **PolicyRule**: a rule that constrains an action or transition.
- **Predicate**: a condition that evaluates data/state to a decision value.
- **Transform**: deterministic mapping from input to output.

`Tool`, `Agent`, `Node`, `Graph`, `Run`, `Provider`, and `Workspace` are deliberately not listed as primitives. Current evidence shows they are compositions, runtime facts, roles/views, or product boundaries.

### Level 1: semantic capability and fulfillment

The audit now distinguishes four concepts that current subsystems often blur together:

```text
Capability = semantic ability that may be requested
Provider   = selectable implementation of a capability contract
Binding    = authorized/configured route from a consumer to fulfillment
Invocation = one concrete runtime use of a binding
```

A provider is not a binding. `CapabilityRegistry` stores multiple providers under a slot, selects one by activation/fallback/trust, and health-checks the provider before returning it. The provider then implements the slot-specific protocol. That is implementation selection, not the consumer's authorization/configuration relationship.

A binding is provisionally:

```text
Binding = Capability + Protocol/Contract + Target/Provider selection
        + InputSchema + OutputSchema + Configuration/Credential + Policy
```

The exact minimum fields remain under audit. The important invariant is that a binding answers "how may this consumer fulfill this capability?", while an invocation answers "what happened on this specific call?"

Possible fulfillment/binding forms include:

- model provider
- Python/function
- HTTP/API
- MCP
- foreign harness
- A2A/remote agent
- subprocess/sandbox
- human interaction
- graph/subgraph

This does not mean the product vocabulary must call all of these "bindings." It means they should not each invent a separate invocation architecture if their semantic difference is only protocol/target.

### Level 2: intelligence and behavior

```text
Genome = Model + PromptTemplate + ParameterSet
Agent  = Genome + authorized Bindings + Policy
```

A **Tool** is provisionally a capability/binding exposed for agent invocation, not an independent execution primitive.

This also makes agents-as-tools ordinary rather than exceptional. If Agent A does not have a direct binding for Capability X, it may have a delegation binding to Agent B. Agent B can possess the model, genome, credentials, policy, context, and direct capability binding required to perform X successfully and safely.

```text
Agent A
  -> capability request X
  -> authorized delegation binding to Agent B
  -> Agent B direct binding for X
  -> invocation
```

This decomposition is materially smaller than the current `AgentIdentity`/`AgentSpec` objects, which also carry task identity, scheduling, tracing, memory, delegation, security policy, provenance, and execution metadata. Those concerns should not define what an Agent intrinsically is.

### Level 3: executable envelope

```text
Node<T> = an addressable composition/execution position containing T
```

`T` may be:

- Agent
- Binding/invocation adapter
- Transform
- Human interaction
- Graph
- another executable/composite type discovered later

Node is therefore not synonymous with LLM call, Agent, Tool, or Graph. Those are things a node can contain or delegate to.

The current `NodeRun` supports this conclusion indirectly: its `executor` can replace the default LLM path entirely, proving that graph position and execution backend are independent dimensions. However, `NodeRun` itself currently mixes the Node definition, payload configuration, invocation state, retry state, result, telemetry, and lifecycle. It is therefore not a clean canonical Node or Run.

### Level 4: composition

```text
Edge  = SourceNode + TargetNode + Predicate + DataMapping
Graph = Nodes + Edges
```

Graph is not primitive. A Graph may itself occupy a Node, allowing recursive composition without giving Graph a second execution ontology.

Higher-order product terms such as workflow, team, fleet, wave, pipeline, and recipe should be tested against this layer. If they differ only by graph topology/configuration/policy, they are product or authoring concepts rather than new runtime primitives.

### Level 5: execution lifecycle

The execution audit now supports a more precise decomposition:

```text
WorkRequest = desired work + inputs + constraints + scheduling intent
Run         = one execution instance of an executable/composition
Attempt     = one retry-bounded attempt within a Run or Invocation
Invocation  = one concrete use of a Binding
Session     = continuity/context spanning interactions, not execution identity
Checkpoint  = persisted event/snapshot from Run state
Recovery    = policy + replay/resume procedure over Checkpoints
```

Events, checkpoints, artifacts, metrics, retry state, correlation, parent/root lineage, and child runs attach to a Run. They do not make `GraphRun`, `NodeRun`, `Task`, `HarnessSession`, etc. fundamentally different kinds of execution unless an invariant discovered later requires a separate concept.

### Level 6: ownership/product organization

```text
Workspace = ownership/container boundary over definitions, runs, artifacts, policy and credentials
```

Workspace is useful and likely canonical at the product boundary, but it is not a primitive of execution.

## Confirmed sprawl findings

### 1. `HarnessRunner` is literally duplicated

Core currently defines a `HarnessRunner` protocol in both:

- `maistro.capabilities.protocols`
- `maistro.capabilities.slots.harness_runner`

They are not byte-equivalent. One accepts `AgentIdentity` in `start_session`; the other accepts `AgentSpec`. This is a concrete example of duplicate vocabulary already producing contract drift.

**Canonical direction:** one provider/protocol contract for a foreign harness. The Agent's authorization/configuration relationship to that provider should be represented as a binding. Harness session continuity should not define a new execution ontology.

**Action:** MERGE after the Binding vocabulary is decided. Do not add a third runtime-facing harness contract.

### 2. Agent definitions mix ontology levels

`AgentIdentity` and `AgentSpec` contain fields from multiple layers: identity, model selection, prompt selection, inference parameters, tools, task/run context, security, scheduling, tracing, memory/context, delegation and provenance.

`AgentSpec` is especially execution-shaped: it carries task IDs, attempt, upstream outputs, lane/scheduling information, tracing, and other spawn context. That is not intrinsic Agent identity.

**Canonical direction:** split reusable Agent definition from authorization/bindings/policy and from per-run invocation/spawn context. Test the minimum `Agent = Genome + authorized Bindings + Policy` model against all existing agent paths.

**Action:** DECOMPOSE.

### 3. Agent role is defined more than once

`maistro.graph.types.AgentRole` and `maistro.agents.spec.agent_spec.AgentRole` are separate enums with overlapping but non-identical members. Graph has already widened role-bearing fields to arbitrary strings because node identity/kind and agent role are different dimensions.

**Canonical direction:** role is metadata/classification on an Agent or composition, not Node identity and not an execution primitive.

**Action:** MERGE/RENAME after usage inventory.

### 4. Graph `ExecutionMode` encodes compositions as execution kinds

`ExecutionMode` currently distinguishes `TASK`, `WORKFLOW`, `AGENT`, and `GRAPH`. Under the primitive-first model, these are not peer execution mechanisms. They are different executable definitions/product views consumed by a common Run mechanism.

**Canonical direction:** eliminate or redefine this enum around actual execution semantics if such semantics exist.

**Action:** DECOMPOSE/REMOVE candidate.

### 5. `NodeConfig` mixes payload identity with node configuration

`NodeConfig` carries `role`, `kind`, `system_prompt`, `temperature`, `model`, `max_tokens`, learned confidence, display name, and beam width. The comment explicitly says Phase 2 widened it for the "anything is a node" model.

This is evidence that model/prompt/parameter information belongs to the payload, for example Genome/Agent, while Node needs only composition/execution-envelope concerns.

**Canonical direction:** make Node payload-agnostic and move LLM/Agent configuration into the contained definition.

**Action:** DECOMPOSE.

### 6. `NodeRun` mixes definition, execution, retry, result, and telemetry

`maistro.graph.node.NodeRun` contains node identity and role alongside model, temperature, system/user prompts, blackboard snapshot, executor, phase, retry count, timing, token accounting, beam candidates, parsed output, error state, circuit breaker, and event emission.

It also supports either the default LLM call path or an arbitrary `NodeExecutor`, which confirms that the graph node and the backend that fulfills it are independent concepts.

**Canonical direction:** separate Node definition/payload from Run/Invocation/Attempt state and telemetry. A node execution should be a child execution fact within the containing graph Run, not the Node definition itself.

**Action:** DECOMPOSE.

### 7. Edge mixes topology and learned/runtime policy

`GraphEdge` includes source/target and condition, but also parallel, weight, trust, sign, and staleness decay. Some may be legitimate edge attributes; others may be policy/optimizer overlays rather than the minimum Edge concept.

**Canonical direction:** derive a minimal Edge, then layer optimizer/policy annotations without redefining topology.

**Action:** DECOMPOSE candidate.

### 8. Task is a work request and a Run collapsed together

`TaskCreate` contains desired work and scheduling/configuration intent: description, workspace path, constraints, lane, priority, task type, optional agent/capability targeting, program context, and session identity.

`TaskResponse` then adds lifecycle status, progress, result, started/completed timestamps, phase, and execution outcome. `TaskRunner` drives those lifecycle transitions and invokes an injected executor.

`TaskStatus` further embeds domain phases such as `PLANNING`, `CODING`, `REVIEWING`, and `TESTING` in the same enum as universal lifecycle states such as `QUEUED`, `COMPLETED`, `FAILED`, and `CANCELLED`.

**Canonical direction:** split WorkRequest/Task intent from Run. Scheduling metadata belongs to admission/scheduling policy. Domain progress phases belong to the executable/composition or progress events, not the universal Run lifecycle.

**Action:** DECOMPOSE, then MERGE the execution half into Run semantics.

### 9. Canonical `RunContext` is identity/lineage context, not a complete Run record

`maistro.runtime.types.RunContext` carries `run_id`, workspace ownership, kind, lifecycle state, root/parent lineage, actor, correlation, and metadata. `ExecutionContext` wraps it with services for propagation through adapters.

This is useful common execution identity, but it is frozen context rather than the mutable/persisted Run record itself. Meanwhile graph durable runs have their own persisted status, node records, checkpoints, outputs, pause state, and timestamps.

**Canonical direction:** retain common Run identity/lineage, but do not mistake `RunContext` for the full Run aggregate. The eventual canonical Run must separate immutable identity/context from mutable persisted execution state.

**Action:** KEEP/REFINE.

### 10. Durable graph runs are a specialized persisted Run view

`DurableRunRecord` stores graph-specific execution state: DAG snapshot, graph inputs, node records, blackboard, HITL answers, pause/resume metadata, timestamps, and errors. It now also carries canonical run lineage/correlation fields.

`DurableNodeRecord` stores per-node phase, output, latency, errors, tokens, model, cost, pause metadata, timing, and attempt count.

The comments already describe this as the "persisted graph-adapter shape," which is strong evidence that durability is a persistence characteristic of a Run rather than a distinct ontology.

**Canonical direction:** model durable graph state as a graph-specific Run state/projection attached to canonical Run identity. Preserve graph-specific snapshots without creating a second root lifecycle.

**Action:** MERGE/VIEW.

### 11. General Session is conversation continuity, not execution

`maistro.sessions.store.InMemorySessionStore` stores ordered user/assistant messages by `session_id`, prunes them using TTL, and limits retained history using `SessionConfig`. `SessionMessage` is simply role + content.

This is a distinct invariant from Run: a conversation may span multiple runs, and a run need not have a conversational session.

**Canonical direction:** retain Session as continuity/context. Explicitly prevent Session from becoming a synonym for Run. Harness-specific "session" needs a separate audit because it may represent a remote process handle rather than conversation memory.

**Action:** KEEP/CLARIFY.

### 12. Checkpoint, replay, and recovery are Run services, not execution roots

`TaskCheckpoint` is a sequenced persisted fact keyed by `task_id` with kinds such as tool-call boundaries, wave fan-out/completion, approval gates, spend updates, and memory promotion.

`replay()` is a pure fold over checkpoints that reconstructs `ResumeState`. `CrashLoopPolicy` records failures/quarantine decisions, and `version_compatible()` gates replay against recipe/code-registry versions.

These have clean lower-level meanings once Task is decomposed:

```text
Checkpoint = persisted Run event/snapshot
Replay     = deterministic state reconstruction
Recovery   = policy/procedure over Run + Checkpoints
```

**Canonical direction:** re-key/attach them to canonical Run/Attempt identity rather than preserving Task as a second execution root solely because recovery currently uses `task_id`.

**Action:** RETAIN semantics, REHOME lifecycle ownership.

### 13. Capability Provider, Binding, and Invocation are distinct

The first audit suspected `CapabilityProvider` and Binding might be the same layer. Source inspection disproves that simplification.

`CapabilityRegistry`:

- defines slots
- registers multiple providers per slot
- tracks active/enabled provider state
- selects fallback or trust-ranked providers
- health-checks the selected provider before resolution

`CapabilityProvider` supplies metadata (`name`, `slot`, `trust_tier`, dependencies) and health. Concrete providers additionally implement slot-specific domain protocols.

That makes Provider a selectable implementation. It does not express which Agent is authorized/configured to use which capability, and it is not one concrete call.

**Canonical direction:**

```text
Capability -> Provider/implementation
Agent -> Binding/authorization+configuration -> Provider/fulfillment
Binding -> Invocation at runtime
```

The exact relationship between Tool exposure and Binding still needs the tool/MCP/HTTP pass.

**Action:** KEEP Provider, ADD/FORMALIZE Binding, KEEP Invocation distinct.

### 14. `Strategy` is an overloaded word

Graph `NodeStrategy` is primarily prompt/output shaping. Agent `strategies` implement agent reasoning/execution approaches. These are not the same concept even though they share the name.

**Canonical direction:** reserve distinct terms for payload shaping versus agent reasoning/control policy.

**Action:** RENAME at least one family.

## Repository sprawl matrix, current evidence

| Current concept | Package/path | Actual responsibility | Decomposes into | Canonical mapping | Action |
|---|---|---|---|---|---|
| `CapabilityProvider` | `capabilities.protocols` | provider metadata, dependencies, trust, health | implementation metadata + provider contract | Provider | KEEP |
| `CapabilityRegistry` | `capabilities.registry` | slot registry, provider selection, fallback, health-gated resolution | capability slot catalog + provider selection policy | Capability catalog / Provider resolver | KEEP/RENAME candidate |
| duplicated `HarnessRunner` | `capabilities.protocols`, `capabilities.slots.harness_runner` | foreign harness provider/session protocol | Provider + protocol + remote continuity handle | Provider/Protocol | MERGE |
| `AgentIdentity` | `types.agent` and consumers | reusable identity plus model/prompt/tool/policy concerns | Agent definition + Genome + Bindings/Policy | Agent/Genome/Binding/Policy | DECOMPOSE |
| `AgentSpec` | `agents.spec` | spawn definition plus task/attempt/upstream/scheduling/tracing context | Agent definition + invocation/run context | Agent + Run/Invocation context | DECOMPOSE |
| multiple `AgentRole` | graph + agents | role labels with divergent members | classification metadata | AgentRole/classification | MERGE/RENAME |
| `NodeConfig` | graph types | node plus embedded LLM/prompt/behavior config | Node envelope + payload definition + parameters | Node + Genome/payload config | DECOMPOSE |
| `NodeRun` | `graph.node` | node execution object with retry/result/telemetry | Node ref + child Run/Invocation + Attempt + telemetry | Node + Run/Attempt/Invocation | DECOMPOSE |
| `NodeExecutor` | `graph.node` | alternate backend owning a node turn loop | executable backend protocol | fulfillment/provider protocol | RETAIN, map after Binding audit |
| `ExecutionMode` | graph types | labels task/workflow/agent/graph as execution modes | executable/product kind labels | view/definition kind | REMOVE/REDEFINE candidate |
| `TaskCreate` | `tasks.models` | desired work + constraints + scheduling/target hints | WorkRequest + scheduling intent | WorkRequest | RENAME/DECOMPOSE |
| `TaskResponse` | `tasks.models` | request plus lifecycle/progress/result | WorkRequest + Run projection | WorkRequest + Run view | DECOMPOSE |
| `TaskStatus` | `tasks.models` | universal lifecycle + domain phases | RunState + Progress/Phase | RunState + progress events | DECOMPOSE |
| `TaskRunner` | `tasks.runner` | queue admission + worker pool + execution dispatch + state transitions | Scheduler/Dispatcher + Run launcher | scheduling/execution service | DECOMPOSE/REHOME |
| `RunContext` | `runtime.types` | immutable run identity, ownership, lineage, correlation | Run identity/context | RunIdentity/RunContext | KEEP/REFINE |
| `ExecutionContext` | `runtime.types` | propagated run context + service bag | RunContext + runtime services | execution propagation context | KEEP/REFINE |
| `DurableRunRecord` | `graph.durable_runs.types` | persisted graph run state | Run identity + graph-specific state/checkpoint projection | Run + GraphRunState | MERGE/VIEW |
| `DurableNodeRecord` | `graph.durable_runs.types` | persisted node execution/result/attempt telemetry | Node ref + child execution state + metrics | child Run/Invocation state | DECOMPOSE/VIEW |
| `SessionConfig` / session store | `types.session`, `sessions.store` | conversation history continuity + retention | message history + retention policy | Session | KEEP/CLARIFY |
| `TaskCheckpoint` | `tasks.checkpoint` | sequenced recovery fact | run id + event kind + payload + definition versions | Checkpoint/Event | REHOME |
| `ResumeState` / `replay()` | `tasks.replay` | deterministic reconstruction from checkpoints | fold/checkpoint projection | Run state reconstruction | KEEP/REHOME |
| `CrashLoopPolicy` | `tasks.recovery` | quarantine decision using circuit breaker | recovery policy | PolicyRule/RecoveryPolicy | KEEP/REHOME |
| Graph/DAG | `graph` | node/edge composition plus graph-specific runtime features | Nodes + Edges + annotations/policies | Graph | KEEP/DECOMPOSE overlays |

## Emerging canonical lifecycle

The lifecycle evidence currently points to this hierarchy:

```text
WorkRequest
  describes desired work
  may select or produce an Executable definition
        |
        v
Run
  identity: run_id, workspace, actor, lineage, correlation
  definition/executable reference
  inputs
  mutable lifecycle state
  outputs/artifacts
  events/checkpoints
        |
        +-- Attempt(s)
        |     retry-bounded execution attempts
        |     errors/backoff/telemetry
        |
        +-- Invocation(s)
        |     concrete Binding uses
        |     tool/model/agent/harness/human/etc.
        |
        +-- child Run(s)
              nested graph/agent/subgraph/delegated execution where
              independent lifecycle/lineage is actually required

Session
  separate continuity axis that may span Runs
```

A key unresolved design question is when a Node execution is a child Run versus an Invocation/Attempt inside the parent Run. The answer should be based on independent lifecycle, resumability, ownership, and lineage requirements, not on the fact that the current class is named `NodeRun`.

## Suspected duplicate families requiring full inventory

### Invocation/binding family

Current names likely describing variants of the same lower-level operation:

- Tool/tool handler
- HTTP tool/API call
- MCP tool call
- capability slot/provider operation
- HarnessRunner call
- NodeExecutor/HarnessNodeExecutor bridge
- subprocess/sandbox exec
- A2A delegation
- human approval/question/review
- integration client operation

Question to answer: what invariant, if any, prevents these from sharing Capability + Binding + Invocation mechanics while retaining specialized protocols/providers?

### Execution-instance family

The first lifecycle pass has reduced some ambiguity but these remain to inspect:

- Graph executor/non-durable graph run state
- harness process/session handles
- agent session/spawn
- scheduled execution
- RSI/evolve cycle/run
- A2A task lifecycle
- wave execution

Question to answer: which require independent Run identity and lineage, versus Attempt/Invocation/Session projections under another Run?

### Composition family

- Graph
- DAG
- workflow
- pipeline
- team
- fleet
- wave
- recipe

Question to answer: which have semantics that cannot be represented as Node + Edge + policies/annotations?

### Definition/configuration family

- AgentIdentity
- AgentSpec
- NodeConfig
- recipe agent definitions
- portable AgentCard
- PipelineGenome
- prompt variants
- model tier/resolution config

Question to answer: what belongs intrinsically to a definition, what is a reusable primitive, and what belongs only to a Run?

## Canonical vocabulary, provisional

| Term | Meaning | Layer |
|---|---|---|
| Model | inference model identity/target | primitive |
| PromptTemplate | reusable prompt/message template | primitive |
| ParameterSet | behavior/inference parameters | primitive |
| Schema | typed data contract | primitive |
| Protocol | interaction/invocation rules | primitive |
| Credential | authority used by a binding | primitive |
| PolicyRule | constraint on action/transition | primitive |
| Predicate | conditional decision | primitive |
| Transform | deterministic data mapping | primitive |
| Capability | semantic ability that can be requested | semantic contract |
| Provider | selectable implementation of a capability/protocol | implementation |
| Binding | authorized/configured fulfillment route available to a consumer | composition of primitives |
| Invocation | one runtime use of a Binding | runtime fact |
| Genome | Model + PromptTemplate + ParameterSet | composition |
| Agent | Genome + authorized Bindings + Policy | composition |
| Tool | agent-visible capability/binding exposure | role/view, not primitive |
| Node | addressable envelope containing an executable/composition | composition primitive candidate |
| Edge | connection between Nodes, minimally topology + predicate/mapping | composition |
| Graph | Nodes + Edges | composition |
| WorkRequest | desired work + inputs/constraints/scheduling intent | request/product |
| Run | execution instance of an executable/composition | runtime aggregate |
| Attempt | retry-bounded attempt within execution | runtime child fact |
| Session | continuity/context across interactions | context axis |
| Checkpoint | persisted event/snapshot used for resume/recovery | runtime persistence |
| Workspace | ownership/product boundary | organizational |

## Migration rule

Do not create a new architectural noun when an existing canonical concept plus specialization/metadata expresses the same invariant.

For every existing noun encountered in the audit, classify it as one of:

- **KEEP**: already matches one canonical meaning.
- **MERGE**: semantic duplicate of another concept.
- **RENAME**: useful concept, misleading/overloaded name.
- **DECOMPOSE**: combines multiple ontology layers.
- **VIEW**: useful product/UX term derived from canonical concepts.
- **REMOVE**: no distinct invariant remains after decomposition.
- **REHOME**: semantics are valid but lifecycle ownership/package boundary is wrong.

## Next inventory pass

Continue the repository-wide matrix in this priority order:

1. tool definitions/registries, MCP, HTTP and integrations, specifically Tool vs Capability exposure vs Binding vs Provider vs Invocation
2. human/HITL node contracts to test human-as-fulfillment without special execution ontology
3. harness session/process handles and A2A delegation to test agents-as-tools
4. AgentIdentity, AgentSpec, AgentCard and recipes to derive Genome/Agent boundaries fully
5. graph Node/Edge/Graph definition types versus executor state
6. scheduled execution and orchestration wave/fleet/team lifecycle
7. RSI/evolve genome/cycle/pipeline concepts
8. state/event/artifact vocabulary
9. workspace/project persistence boundary

Do not write a normative ADR/SPEC yet. The Tool/Binding/Invocation and Agent/Genome passes can still materially change the bottom half of the hierarchy.

## Effect on the current runtime-spine branch

Existing `Workspace`, run identity/lineage/context propagation, and capability-provider work may still be reusable. However, no additional top-down execution path should be forced through `ExecutionRuntime` merely to satisfy the earlier spine shape until this audit determines whether `ExecutionRuntime`, Capability/Provider resolution, and the current Run contract map cleanly onto the canonical lower-level vocabulary.

The branch should preserve working commits, avoid destructive rollback, and use the ontology audit to determine the next implementation slice.