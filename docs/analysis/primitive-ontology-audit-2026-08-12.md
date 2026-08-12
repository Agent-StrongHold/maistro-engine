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

`Tool` is deliberately not yet listed as primitive. Current evidence suggests it may be a role played by a more general binding.

### Level 1: bindings

**Binding** is the strongest candidate for the missing canonical concept in the current architecture.

A binding associates a protocol with a target and the information necessary to use it:

```text
Binding = Protocol + Target + InputSchema + OutputSchema + Configuration/Credential
```

Possible binding specializations include:

- model provider binding
- Python/function binding
- HTTP/API binding
- MCP binding
- foreign-harness binding
- A2A/remote-agent binding
- subprocess/sandbox binding
- human-interaction binding

This does not mean the product vocabulary must call all of these "bindings." It means they should not each invent a separate invocation architecture if their semantic difference is only protocol/target.

### Level 2: intelligence and behavior

```text
Genome = Model + PromptTemplate + ParameterSet
Agent = Genome + exposed Bindings
```

A **Tool** is provisionally a binding exposed for agent invocation, not an independent execution primitive.

This decomposition is materially smaller than the current `AgentIdentity`/`AgentSpec` objects, which also carry task identity, scheduling, tracing, memory, delegation, security policy, provenance, and execution metadata. Those concerns should not define what an Agent is.

### Level 3: executable envelope

```text
Node<T> = an addressable composition/execution position containing T
```

`T` may be:

- Agent
- Binding/invocation
- Transform
- Human interaction
- Graph
- another executable/composite type discovered later

Node is therefore not synonymous with LLM call, Agent, Tool, or Graph. Those are things a node can contain or delegate to.

### Level 4: composition

```text
Edge = SourceNode + TargetNode + Predicate + DataMapping
Graph = Nodes + Edges
```

Graph is not primitive. A Graph may itself occupy a Node, allowing recursive composition without giving Graph a second execution ontology.

Higher-order product terms such as workflow, team, fleet, wave, pipeline, and recipe should be tested against this layer. If they differ only by graph topology/configuration/policy, they are product or authoring concepts rather than new runtime primitives.

### Level 5: execution instance

```text
Run<T> = one execution instance of T + inputs + mutable state + lifecycle
```

Events, checkpoints, artifacts, metrics, retry state, correlation, parent/root lineage, and child runs attach to a Run. They do not make `GraphRun`, `NodeRun`, `Task`, `HarnessSession`, etc. fundamentally different kinds of execution unless the audit finds an invariant that requires a separate primitive.

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

**Canonical direction:** one binding/provider contract for a foreign harness. Session lifecycle may be a protocol capability of that binding rather than a separate ontology.

**Action:** MERGE after the binding vocabulary is decided. Do not add a third runtime-facing harness contract.

### 2. Agent definitions mix ontology levels

`AgentIdentity` and `AgentSpec` contain fields from multiple layers: identity, model selection, prompt selection, inference parameters, tools, task/run context, security, scheduling, tracing, memory/context, delegation and provenance.

An Agent's intrinsic definition should be separable from the context of a particular execution.

**Canonical direction:** split definition from execution context. Test the minimum `Agent = Genome + exposed Bindings` model against all existing agent paths.

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

This is evidence that model/prompt/parameter information belongs to the payload (for example Genome/Agent), while Node needs only composition/execution-envelope concerns.

**Canonical direction:** make Node payload-agnostic and move LLM/Agent configuration into the contained definition.

**Action:** DECOMPOSE.

### 6. Edge mixes topology and learned/runtime policy

`GraphEdge` includes source/target and condition, but also parallel, weight, trust, sign, and staleness decay. Some may be legitimate edge attributes; others may be policy/optimizer overlays rather than the minimum Edge concept.

**Canonical direction:** derive a minimal Edge, then layer optimizer/policy annotations without redefining topology.

**Action:** DECOMPOSE candidate.

### 7. Task is partly a Run under another name

`TaskResponse` owns lifecycle/status, workspace, timestamps, result, progress, agent/capability identifiers and scheduling metadata. This substantially overlaps a generic Run instance plus scheduling/product metadata.

`TaskStatus` also embeds domain phases (`PLANNING`, `CODING`, `REVIEWING`, `TESTING`) in the generic lifecycle enum.

**Canonical direction:** distinguish a task/request definition from its Run. Domain phases belong to the executable/composition or progress events, not the universal run lifecycle.

**Action:** DECOMPOSE/MERGE candidate.

### 8. Capability provider and binding may be the same architectural layer

`CapabilityProvider` defines a selectable implementation with slot, dependencies, trust and health. Slot-specific protocols add domain operations. Structurally, this is close to a configured Binding/provider registry.

**Canonical direction:** determine whether Capability is product vocabulary for discoverable Bindings rather than a separate runtime primitive.

**Action:** MERGE candidate, pending full capability-slot audit.

### 9. `Strategy` is an overloaded word

Graph `NodeStrategy` is primarily prompt/output shaping. Agent `strategies` implement agent reasoning/execution approaches. These are not the same concept even though they share the name.

**Canonical direction:** reserve distinct terms for payload shaping versus agent reasoning/control policy.

**Action:** RENAME at least one family.

## Suspected duplicate families requiring full inventory

### Invocation/binding family

Current names likely describing variants of the same lower-level operation:

- Tool/tool handler
- HTTP tool/API call
- MCP tool call
- Capability provider call
- HarnessRunner call
- NodeExecutor/HarnessNodeExecutor bridge
- subprocess/sandbox exec
- A2A delegation
- human approval/question/review
- integration client operation

Question to answer: what invariant, if any, prevents these from sharing one typed Binding + Invocation contract?

### Execution-instance family

- NodeRun
- GraphRun
- durable run
- task execution
- harness session
- agent session/spawn
- scheduled execution
- recovery/replay execution
- RSI/evolve cycle/run
- A2A task lifecycle

Question to answer: which fields/state transitions are genuinely unique, versus views/adapters over one Run primitive?

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
| Binding | configured connection to an invokable target | composition of primitives |
| Genome | Model + PromptTemplate + ParameterSet | composition |
| Agent | Genome + exposed Bindings | composition |
| Tool | a Binding exposed for agent invocation | role/view, not primitive |
| Node | addressable envelope containing an executable/composition | composition primitive candidate |
| Edge | connection between Nodes, minimally topology + predicate/mapping | composition |
| Graph | Nodes + Edges | composition |
| Run | execution instance of an executable/composition | runtime |
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

## Next inventory pass

The next pass should populate a repository-wide table with:

```text
Current name | Package/path | Current responsibility | Decomposes into | Canonical term(s) | Action
```

Priority order:

1. tool definitions/registries, MCP, HTTP and integrations
2. human/HITL node contracts
3. capability slots/providers
4. AgentIdentity, AgentSpec, AgentCard and recipes
5. graph Node/Edge/Graph and executor seams
6. Task/Run/DurableRun/session/schedule/recovery/replay
7. RSI/evolve genome/cycle/pipeline concepts
8. team/fleet/wave/orchestration compositions
9. state/event/artifact/checkpoint vocabulary
10. workspace/project persistence boundary

## Effect on the current runtime-spine branch

Existing `Workspace`, execution lineage/context propagation, and capability-context work may still be reusable. However, no additional top-down execution path should be forced through `ExecutionRuntime` merely to satisfy the earlier spine shape until this audit determines whether `ExecutionRuntime`, `Capability`, and the current Run contract map cleanly onto the canonical lower-level vocabulary.

The branch should therefore preserve working commits, avoid destructive rollback, and use the ontology audit to determine the next implementation slice.