# Agent and Genome ontology audit checkpoint

Date: 2026-08-12
Status: Discovery, non-normative
Branch: `feature/workspace-run-runtime-spine`
Parent audit: `docs/analysis/primitive-ontology-audit-2026-08-12.md`

## Scope

This checkpoint resumes the primitive-first audit at the first incomplete item from the parent document: Agent/Genome boundaries. It also tightens the Capability vs Binding vs Invocation distinction because the current Agent types embed tool/capability authorization directly.

No ADR, spec, acceptance criteria, test contract, or implementation consolidation is authorized by this document. The repository remains under the v1 feature freeze described in `CONTRIBUTING.md`.

## Source evidence

### `AgentIdentity` is a composite definition, not identity

`maistro.types.agent.AgentIdentity` is documented as "Everything that defines an agent" and currently contains all of the following in one frozen dataclass:

- durable/display identity: name, version, description;
- Genome-like inference definition: soul prompt name, model, model fallbacks, model constraints;
- exposure/authorization references: tools, skills, rules;
- policy/classification: trust tier, priority tier, max tool rounds;
- delegation topology/policy: delegation mode and sub-agents;
- behavior strategy: reasoning strategy and phases;
- memory configuration;
- provenance/review/activation state.

This is direct evidence that the current noun `AgentIdentity` crosses multiple ontology levels.

### The filesystem loader already separates prompt material from the manifest

`agents/factory.py` loads `agent.yaml`, `SOUL.md`, optional `RULES.md`, and a shared `PREAMBLE.md` independently, then collapses manifest fields into `AgentIdentity`. The source-of-truth flow is filesystem seed -> database, with the database becoming authoritative after seed.

That existing physical separation supports decomposing the canonical definition without requiring separate authoring files. A manifest may remain a convenient serialized view while the domain model distinguishes its parts.

### `AgentSpec` is a spawn/invocation envelope, not an Agent definition

`agents/spec/agent_spec.py::AgentSpec` contains:

- spawned-agent identity and parentage;
- tenant;
- task/subtask IDs and attempt number;
- context and upstream outputs;
- model tier/override/temperature/max tokens;
- prompt name/label/variables;
- recipe/result type;
- tools allowed and write scopes;
- scheduling lane;
- tracing IDs.

`AgentOutput` then adds result, error/recoverability, timing, model/tier/token telemetry, and tracing.

This envelope therefore combines definition overrides with WorkRequest/Run/Attempt/Invocation context and execution telemetry. It should not become the canonical Agent object.

### The running `Agent` object is assembled behavior plus injected fulfillment services

`agents/base.py::Agent` receives an `AgentIdentity`, a reasoning strategy, LLM client, context/prompt services, Warden, memory/outcome/session/quota/tracing services, tool executor/registry, and an agent resolver. Its module explicitly says "An agent is data, not a process. The runtime is shared."

The object also turns tool names into model-facing function schemas separately from the injected `tool_executor`. This is strong evidence that model-visible ToolExposure and actual fulfillment are separate concepts even before a canonical Binding exists.

### Capability slots are provider-resolution infrastructure

`capabilities/types.py::SlotSpec` declares a named slot plus fallback policy and optional baseline provider. `CapabilityRegistry` stores providers per slot, activates/selects them, applies enabled/fallback behavior, and health-checks the selected provider.

This answers "which implementation can fulfill this capability slot now?" It does not encode which Persona/Graph/Node/Agent is authorized to use it, credentials for that consumer, or the runtime record of a particular use.

Therefore current capability-provider resolution is useful substrate, but it is not equivalent to Binding or Invocation.

## Recursive decomposition

```text
Prompt material
  PromptTemplate

Model selection
  Model
  + fallback/selection constraints

Inference/behavior configuration
  ParameterSet

Genome
  Model
  + PromptTemplate
  + ParameterSet

AgentDefinition
  durable identity/classification
  + Genome

Agent
  AgentDefinition
  + authorized Binding set
  + effective Policy

Binding
  Capability reference
  + target/provider selection
  + Protocol
  + Schema
  + configuration/Credential
  + binding-local Policy constraints

ToolExposure
  model-visible projection of an authorized Binding/Capability
  + name/description/input schema

Invocation
  one runtime use of a resolved Binding
  + inputs/outputs
  + status/timing/telemetry
  + optional provider-side handle/session

Node
  addressable executable envelope
  + payload (Agent, Binding-backed action, Transform, Human interaction, Graph, etc.)
  + node-local policy/configuration overrides

Run / NodeRun / Attempt
  execution lifecycle and retry facts
  + Invocation(s)
```

## Important boundary: Genome is deliberately smaller than current `AgentIdentity`

The source supports keeping Genome narrowly behavioral:

```text
Genome = Model + PromptTemplate + ParameterSet
```

The following do **not** belong in Genome unless later evidence demonstrates that they are intrinsic heritable behavior:

- credentials;
- tool/provider bindings;
- authorization grants;
- workspace/persona/graph/node permissions;
- task IDs or attempt counts;
- tracing/session IDs;
- scheduling lane;
- review/activation workflow state.

Rules and reasoning phases need a later usage pass. They may be PromptTemplate content, ParameterSet/strategy configuration, or Policy depending on whether each rule instructs behavior or constrains authority. Do not classify them by field name alone.

## Agent-backed bindings and agents-as-tools

Current local delegation already resolves a sub-agent and recursively invokes its `handle()` path, while the A2A package separately owns broker/delegator/lifecycle mechanisms. The parent audit identified this as duplicated delegation.

The Agent/Genome decomposition clarifies the target without requiring an `AgentTool` primitive:

```text
Caller Node/Agent
  -> authorized Agent-backed Binding
       capability = delegated work/capability
       target = AgentDefinition or external Agent endpoint
       protocol = local | A2A/federated
       policy = allow-list/trust/budget/depth/etc.
  -> Invocation
  -> target Agent executes under its own effective bindings/policy
```

Whether the delegated work receives a child Run or remains an Invocation inside the caller Run is still unresolved. That decision must be based on independent lifecycle, ownership, resumability, lineage and observability requirements, not on the fact that the target is an Agent.

## Capability vs Binding vs Invocation

The current capability package should not be renamed wholesale. Its slot/provider machinery has a distinct implementation-resolution responsibility.

Canonical distinction:

| Question | Canonical concept | Current evidence |
|---|---|---|
| What semantic ability exists? | Capability | capability slot names approximate this |
| What implementation can fulfill it? | Provider | `CapabilityProvider` + registry providers |
| Which provider is selected/healthy? | Provider resolution | `CapabilityRegistry.resolve()` |
| How is this consumer authorized/configured to use it? | Binding | fragmented across agent tool lists, write scopes, injected executors, credentials/policy |
| What is shown to an LLM as callable? | ToolExposure | `_build_tool_schema()` + `AgentIdentity.tools` |
| What happened on this use? | Invocation | currently distributed through agent/tool/harness/A2A execution paths |

The missing first-class concept in current core is therefore primarily **Binding**, not Capability.

## Sprawl matrix delta

| Existing concept | Decomposition | Canonical concept | Action |
|---|---|---|---|
| `AgentIdentity` | identity + Genome fields + exposure refs + policy/classification + delegation + memory + review state | AgentDefinition + Genome + Binding refs/Policy + metadata | **DECOMPOSE / RENAME** |
| `Agent` (`agents/base.py`) | definition + strategy + injected shared runtime services + tool exposure + fulfillment adapters | runtime materialization/view of Agent | **RETAIN temporarily / DECOMPOSE boundary** |
| `AgentSpec` | spawn identity + WorkRequest refs + Attempt + context + Genome overrides + Binding permissions + scheduling + tracing | Node/Agent invocation request + Run/Attempt context | **DECOMPOSE** |
| `AgentOutput` | result + error semantics + timing + telemetry + model usage | NodeRun/Invocation result + telemetry | **DECOMPOSE / VIEW** |
| `AgentRole` (spec) | authoring/classification + role-derived prompt/tool defaults | AgentDefinition/Node template classification | **RETAIN semantics, MERGE duplicate enums later** |
| `agent.yaml` manifest | serialized authoring view across definition/genome/policy/binding refs | AgentTemplate/AgentDefinition authoring view | **VIEW / KEEP format provisionally** |
| `SOUL.md` / prompt manager key | reusable behavioral instruction material | PromptTemplate | **KEEP / REHOME canonical ownership later** |
| model/fallback/constraints fields | model target + routing constraints | Model + ParameterSet/model-selection policy | **DECOMPOSE** |
| temperature/max_tokens/tier overrides | invocation-time inference overrides | ParameterSet override | **REHOME from spawn envelope** |
| `tools` / `tools_allowed` | names of exposed/authorized operations | Binding refs + ToolExposure projection | **DECOMPOSE** |
| `write_scopes` | authorization constraint | Policy/Permission | **REHOME** |
| `sub_agents` + delegation config | target refs + delegation policy | Agent-backed Binding(s) + Policy | **DECOMPOSE** |
| `agent_resolver` | runtime resolution of target agent name | Agent-backed Binding resolver/provider adapter | **CONVERGE** |
| `_build_tool_schema()` | converts names/registry definitions to function schema | ToolExposure renderer | **KEEP semantics / REHOME** |
| `tool_executor` | concrete tool fulfillment dispatcher | Binding/Invocation service | **CONVERGE** |
| `SlotSpec` | capability slot + fallback choice | Capability declaration + provider-resolution policy | **KEEP / DECOMPOSE name later if needed** |
| `CapabilityRegistry` | slot catalog + installed providers + activation/fallback/health resolution | Capability catalog + Provider resolver | **KEEP, do not equate with Binding registry** |
| `_SlotState.active/enabled` | provider selection and global availability | provider-resolution state/policy | **KEEP** |
| `CapabilityProvider` | implementation metadata + health + capability-specific protocol | Provider | **KEEP** |
| `WorkerStatus.capabilities` (Builders) | runtime worker capability advertisement | Capability advertisement/view | **VIEW; not Binding** |

## Provisional hierarchy update

The parent audit's lower hierarchy still holds, with Agent now more strongly evidenced:

```text
User
  -> Workspace
     -> Persona                      [product/ownership concept still needs source pass]
        -> reusable templates        [NodeTemplate / GraphTemplate still needs source pass]
        -> Graph
           -> Node
              -> payload
                 -> Agent
                    -> AgentDefinition
                       -> Genome
                          -> Model
                          -> PromptTemplate
                          -> ParameterSet
                    -> authorized Bindings
                    -> effective Policy
                 -> or Binding-backed action / Transform / Human / nested Graph / adapter
           -> Edge

Workspace
  -> Run
     -> NodeRun / child execution facts
        -> Attempt(s)
        -> Invocation(s)
```

Template versus mutable workspace object remains an authoring/product distinction to verify against persistence/UI source. Do not encode class inheritance from this diagram.

## What this evidence rules out

1. Do not make `AgentIdentity` the canonical Agent record unchanged.
2. Do not make `AgentSpec` the canonical Agent or Node type.
3. Do not define Tool as both model-visible schema and execution backend.
4. Do not call provider activation/resolution a consumer Binding.
5. Do not create a special `AgentTool` execution ontology for delegation.
6. Do not move runtime task/attempt/tracing/session fields into Genome.
7. Do not mint a normative ADR/SPEC yet.

## Remaining unresolved Agent/Genome items

The next restart should inspect, in order:

1. recipe types and prompt/model configuration call sites to determine whether Recipe maps to GraphTemplate, NodeTemplate, Genome preset, or a mixed authoring view;
2. rules, phases, reasoning strategy and memory configuration usage to separate PromptTemplate/ParameterSet from Policy and runtime services;
3. agent catalog/export/persistence models to determine AgentTemplate vs AgentDefinition vs mutable workspace Agent semantics;
4. A2A lifecycle/guest-peer advertisement to determine whether any `AgentCard`-like concept is a protocol projection rather than a domain object;
5. graph Node/Edge/Graph definition types once the Agent payload boundary is stable.

Only after those passes should the audit decide whether AgentDefinition deserves a separate durable noun from NodeTemplate/Agent Node payload, and only after the broader ontology stabilizes should current date-based ADR/SPEC IDs be minted.
