# MAIstro Architecture Convergence Matrix

Status: working implementation map for the post-sprawl convergence effort.

This document maps the current repository into the canonical product/runtime hierarchy derived from the intended UX. It is deliberately not an ADR yet. The purpose is to identify what already exists, what is duplicated, and where each existing subsystem belongs before locking architecture.

## Canonical hierarchy

```text
User
└── Workspace[]
    ├── Persona
    │   ├── allowed surfaces
    │   │   ├── UI
    │   │   ├── Builders CLI
    │   │   └── Builders RSI
    │   ├── NodeTemplate[]
    │   └── GraphTemplate[]
    │
    ├── Graph[]
    │   ├── source_template_id/version?
    │   ├── Node[]
    │   │   ├── source_template_id/version?
    │   │   ├── NodeType
    │   │   ├── Parameters
    │   │   ├── Bindings
    │   │   ├── Permissions
    │   │   └── Policy
    │   └── Edge[]
    │
    └── Run[]
        ├── graph reference/snapshot
        ├── NodeRun[]
        ├── Attempt[]
        ├── Events
        ├── Artifacts
        └── Outputs
```

Underlying reusable primitives:

```text
Model
PromptTemplate
ParameterSet
Schema
Protocol
Capability
Provider
Binding
Credential
Permission
Policy
Predicate
Transform
```

Execution vocabulary:

```text
Run = logical execution/history owned by the Workspace
NodeRun = execution record for one Node within a Run
Attempt = one physical execution attempt of a Run or NodeRun
ExecutionRuntime = mechanics for an Attempt, never domain meaning
Session = continuity scope that may span Runs
Invocation = one call/turn through a Binding
```

Template semantics:

```text
NodeTemplate  -> instantiate -> Node  -> mutate -> optionally save as new NodeTemplate
GraphTemplate -> instantiate -> Graph -> mutate -> optionally save as new GraphTemplate
```

Instantiation is copy + provenance, not live inheritance. Existing workspace objects must not silently change when their source template changes.

## Permission model

Permissions constrain downward:

```text
User
  ↓
Workspace
  ↓
Persona
  ↓
Graph
  ↓
Node
  ↓
Binding
  ↓
Invocation
```

A child may narrow permissions but must never widen what its parent permits. Effective permission is the intersection of all applicable scopes.

This is what makes agent-as-tool delegation safe: an Agent Node without a direct binding to a capability can invoke an Agent-backed Binding whose target is configured and authorized to perform that capability.

## Convergence matrix

| Existing object / subsystem | Current package or surface | Canonical concept | Parent | Children / contents | Runtime responsibility | Permission scope | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Authenticated user / service identity | `auth/`, `security/auth_*` | User / Actor | none | workspace memberships, sessions | none | root actor constraints | KEEP, unify actor reference |
| `Project` / `project_id` semantics | core persistence, memory, durable run records, APIs | Workspace | User | Persona, Graphs, Runs, artifacts, credentials, policy | none | workspace ceiling | RENAME/CONVERGE semantically to Workspace; preserve storage compatibility during migration |
| No stable first-class equivalent | product architecture gap | Persona | Workspace | surfaces, NodeTemplates, GraphTemplates, defaults, policy | none | persona ceiling | INTRODUCE |
| Agent recipe files / recipe registry | `agents/recipes` | likely NodeTemplate or GraphTemplate depending recipe shape | Persona | prompt/model/tool/binding defaults or multi-node composition | none | template maximum | SPLIT by semantic shape; do not keep `Recipe` as a universal parallel ontology |
| PM fleet definitions | `agents/pm_fleet` | NodeTemplate catalog / Persona defaults | Persona | specialized Agent node definitions and delegation constraints | none | persona/node | REHOME |
| Builders worker/stage registration | `builders/runtime.py` | NodeTemplate dispatch metadata / Binding registry | Persona or Builders GraphTemplate | handler, prompt version, allowed tools | invocation only | node/binding | DECOMPOSE `BuildersRuntime`; retire as separate runtime concept |
| Builders `RunRequest` | `builders/contracts.py` | Run projection + NodeRun request | Workspace Run | worker/stage context, artifacts | none | inherited from Run/Node | MERGE into canonical Run/NodeRun adapter |
| Builders `RunResult` | `builders/contracts.py` | NodeRun/Run result projection | Run | artifacts, claims, logs | none | inherited | MERGE |
| Builders `StageEvent` | `builders/contracts.py` | canonical Event projection | Run / NodeRun | message, actor, stage | sequencing only | event visibility follows parent | MERGE |
| Builders CLI | CLI surface | Persona-exposed interface | Persona | builders operations | none | Persona surface permission | KEEP as interface, not ontology |
| Builders RSI | CLI / RSI surface | Persona-exposed interface + graph/node workload | Persona | RSI graph/node definitions | Runtime executes Runs only | Persona + Graph/Node | KEEP capability, route through shared objects |
| `AgentIdentity` / persistent agent definitions | `agents/` | NodeTemplate or Node definition fragment | Persona / Graph | genome-ish fields, tools, policy | none | node template/node | DECOMPOSE |
| `AgentSpec` | `agents/spec/agent_spec.py` | mixed Node definition + NodeRun invocation context | Graph / Run | role, task/subtask/attempt/context | none | mixed today | SPLIT definition from runtime context |
| Agent `Genome` concepts in evolve | `maistro-evolve` | Genome primitive composition | Agent NodeTemplate / Node | Model + PromptTemplate + ParameterSet | none | bounded by Agent Node | KEEP concept, normalize representation |
| Agent strategies (`direct`, `react`, `plan_execute`, etc.) | `agents/strategies` | NodeType execution policy / strategy | Agent Node | prompting/tool loop behavior | domain executor, not runtime | node | KEEP as Agent NodeType policy; remove lifecycle ownership if any |
| Agent tool name lists / model-facing schemas | agents + tool rendering | ToolExposure | Agent Node | schemas/names for allowed bindings | none | node + binding | RENAME conceptually; generated view, not execution primitive |
| `SkillDefinition` / skills catalog | `skills/`, portability | mixed Capability declaration + ToolExposure + Binding metadata + trust/prompt metadata | Persona / NodeTemplate | schema, endpoint/auth, prompt/trust/source | none | persona/node/binding | DECOMPOSE; keep portability format as projection |
| Skill import/export | `portability/skills.py`, MCP export | serialization/interoperability adapter | templates/catalog | external formats | none | no widening during import/export | KEEP adapter |
| Agent import/export / `AgentCard` | `portability/agents.py` | NodeTemplate interoperability projection | Persona | portable agent metadata/tools | none | template ceiling | KEEP projection |
| `CapabilityRegistry` / capability slots | `capabilities/` | Capability + Provider registry | platform/workspace/persona depending registration | providers, health/fallback | provider selection only | capability availability ceiling | KEEP, clarify scope |
| `CapabilityProvider` | `capabilities` | Provider | Capability | implementation/health | fulfillment only | cannot exceed Binding/parent permissions | KEEP |
| `HarnessRunner` slot | capabilities | Protocol + Provider family | Capability | start/send/stream/stop | invocation/session mechanics inside provider | binding/node | KEEP, remove duplicate definitions if present |
| `HarnessSessionManager` | capabilities | Binding/session adapter | Node / Session | selected provider, safety wrapper, sequence policy | sessionful invocation | node/binding | KEEP adapter |
| `HarnessNodeExecutor` | `graph/harness_executor.py` | NodeType fulfillment adapter | Harness Node | Binding invocation | domain executor invokes; ExecutionRuntime wraps attempt | Node/Binding | KEEP |
| inbound harness sessions API | Hive/FastAPI | external interface surface | Persona/Workspace policy | harness session operations | none itself | interface + binding | KEEP route, connect to canonical identity/run where work becomes durable |
| HTTP integrations | tools/integrations/providers | Protocol + Binding implementations | Node | endpoint/config/schema | invocation | binding | KEEP, normalize |
| MCP servers/tools | Hive MCP routes + portability | Protocol + Binding + ToolExposure | Persona/Node | server config, tool schemas | invocation | binding | KEEP, normalize; MCP is transport/interoperability, not execution ontology |
| sandbox backends (Docker, microVM, fake) | `tools/sandbox` | Protocol + Provider / Binding infrastructure | Harness/API/Tool Node | process isolation | process supervision may be runtime mechanic only if generic | node/binding | KEEP implementations |
| `GraphConfig`, DAG definitions | `graph/types`, Hive DAG config | Graph or GraphTemplate representation | Workspace/Persona | Nodes, Edges | none | graph ceiling | CONVERGE to canonical Graph/GraphTemplate models |
| graph Node definitions / registered node kinds | `graph/nodes` | Node + NodeType | Graph | typed config/bindings | none | node | KEEP behavior; normalize envelope |
| HITL nodes (`human.*`) | `graph/nodes` | Node(type=human/HITL) | Graph | interaction schema, timeout/escalation | pause/resume mechanics outside node semantics | node | KEEP; no separate HITL execution ontology |
| `NodeExecutor` | `graph/node.py` | Node fulfillment protocol | NodeRun | backend invocation | executor is domain adapter; runtime wraps mechanics | node/binding | KEEP seam; rename only if needed after convergence |
| `NodeRun` | `graph/node.py` | NodeRun, but currently overloaded | Run | node config, retry, result, telemetry, executor | currently owns too many mechanics | node effective permissions | DECOMPOSE to NodeRun record + Attempt/runtime mechanics + node executor |
| `GraphRun` | `graph/run.py` | Run + GraphExecutionState | Workspace Run | NodeRuns, blackboard, traversal/cycles | currently owns lifecycle/cancel/fanout | graph/run | DECOMPOSE, not delete semantics |
| `DurableRunRecord` | `graph/durable_runs/types.py` | Run persistence projection + GraphExecutionState snapshot | Workspace Run | durable node records, graph snapshot, pause data | none | run | REHOME behind canonical Run store |
| `DurableNodeRecord` | durable runs | NodeRun persistence projection | Run | result, phase, attempts, metrics | none | node/run | CONVERGE with NodeRun |
| durable DAG executor | `graph/durable_runs/executor.py` | Graph domain executor + checkpoint adapter | Run | graph walk | traversal belongs to graph adapter; runtime only mechanics | graph/node | KEEP until parity, then consolidate traversal |
| Hive `graph_runner.py` | hive-conductor | product graph adapter | Workspace/Run | stream/API glue | should not own parallel execution lifecycle | inherited | MERGE/REMOVE parallel traversal after parity |
| Hive DAG run store | hive-conductor | Run/GraphExecution persistence adapter | Workspace | run snapshots | none | workspace/run | MERGE into canonical Run repository |
| `TaskCreate` / queued Task objects | `tasks/models.py` | WorkRequest / ingress request | User/Workspace | requested work, lane, capability | none | caller/workspace | KEEP request concept, remove lifecycle duplication |
| `TaskStatus` | `tasks` | mixed ingress + Run lifecycle + domain phases | WorkRequest/Run | planning/coding/etc. | none | inherited | SPLIT; queue state != Run state != graph/node phase |
| `TaskQueue` | `tasks/queue.py` | ingress queue | Workspace/service | WorkRequests | queue mechanics | admission permission | KEEP |
| `TaskRunner` | `tasks/runner.py` | admission/scheduling adapter | WorkRequest -> Run | lane gate, executor call | generic mechanics should move to runtime only when lane semantics preserved | workspace/persona policy | DECOMPOSE |
| `LaneGate` | `tasks/lanes.py` | scheduling policy + concurrency policy | ingress/runtime adapter | live/background/tier reservations | some generic slot mechanics overlap runtime | workspace/persona | KEEP policy, optionally delegate mechanics |
| scheduling store / cron schedules | `scheduling/store.py`, Hive scheduler | Schedule definition + trigger history | Workspace/Persona | trigger metadata | scheduler creates Run; never executes work directly | schedule/target graph | KEEP definition; route trigger to Run launcher |
| Hive scheduler private trigger bookkeeping | hive-conductor | Schedule trigger adapter | Schedule | last/next trigger | none | inherited | KEEP metadata, remove execution ownership |
| `A2ADelegator`, `A2ATask` | `a2a/delegate.py` | Agent-backed Binding + child Run request; duplicate lifecycle | NodeRun/Run | target selection, task status | delegation dispatch only | caller Node + target Agent | DECOMPOSE; replace task lifecycle with child Run |
| A2A lifecycle `TaskQueue/WorkerPool/TaskLifecycleManager` | `a2a/lifecycle` | another work queue/run lifecycle family | delegation service | statuses/workers | duplicate mechanics | delegation scope | MERGE/REMOVE lifecycle duplication after child Runs |
| guest peers / remote delegation | `a2a/guest_peers.py` | remote Agent Binding + trust policy | Agent Node | peer transport | invocation | trust + binding permissions | KEEP |
| `agent.delegate_remote` graph node | graph nodes | Node(type=agent delegation) | Graph | child work request + wait state | durable pause/resume | node/binding | KEEP behavior; target becomes child Run |
| Session store | `sessions/store.py` | Session | User/Workspace | conversational continuity/messages | no Run ownership | session membership | KEEP separate from Run |
| Session collaboration | `collaboration/` | Session ACL/presence/event collaboration | Session | members, roles, presence | live fan-out only | session-local ACL under workspace | KEEP; integrate with parent permission ceiling |
| policy engine / sequence policy | `policy/` | Policy primitive + stateful policy evaluator | Workspace/Persona/Graph/Node/Binding | rules, sequence state | none | whichever scope attaches it | KEEP; standardize attachment points |
| Warden / Sentinel / security gates | `security/` | Policy enforcement / security provider | Binding/Invocation + higher scopes | scans, action gates, strikes | none | inherited effective permissions | KEEP; expose through canonical policy pipeline |
| approval gate protocols | `tools/approval` | Permission/Policy fulfillment protocol | Node/Binding | approval request | wait mechanics via Run/NodeRun | inherited | MERGE conceptually with HITL policy path |
| credentials providers/store/rotation | `credentials/` | Credential primitive + provider/store | Workspace/Persona/Binding | secrets/reference/rotation | none | credential scope cannot widen binding | KEEP; explicit ownership hierarchy |
| prompt manager/store | `prompts/` | PromptTemplate storage/versioning | Persona/NodeTemplate | prompt versions | none | template permissions | REHOME as template primitive service |
| memory scopes/stores/outcomes/learnings | `memory/` | scoped capability/data service | Workspace/Persona/Graph/Node/Run depending memory kind | episodic, semantic, outcomes, learnings | none | scope intersection | KEEP; normalize scope IDs to canonical hierarchy |
| artifacts (`ArtifactRef`, output files, dashboards) | builders + graph + delivery | Artifact | Workspace/Run/NodeRun | typed durable outputs | none | artifact inherits owner visibility | CONVERGE references/repository |
| events (`GraphEvent`, Builders StageEvent, collaboration events, event bus) | `graph/events`, `events/`, builders, collaboration | Event with scoped projections | Run/NodeRun/Session/etc. | typed event payload | ExecutionRuntime may sequence opaque events only | owner scope | CONVERGE event envelope; preserve domain event types |
| observability/tracing | `observability/` | telemetry projection | Run/NodeRun/Attempt/Invocation | spans/metrics/logs | runtime emits mechanics metrics | visibility follows owner | KEEP, correlate on canonical IDs |
| retries/backoff/circuit breakers | resilience + NodeRun + agents | Attempt policy / Provider health policy | NodeRun/Binding | retry count/backoff | runtime can enforce mechanics but policy remains Python domain | node/binding | CONVERGE ownership |
| task recovery | `tasks/recovery.py` | recovery eligibility policy | Run/Attempt | crash-loop/version compatibility | runtime performs mechanics only | run | KEEP policy, stop treating Task as recovery root |
| checkpoints | tasks + durable graph | Checkpoint | Run/NodeRun/Attempt | state snapshot/provenance | none | owner scope | CONVERGE storage/envelope |
| RSI service state in Hive | `backend/services/rsi.py` | Run producer + RSI Node/Graph domain state | Persona/Workspace | evaluation/improvement work | currently private task/cancel lifecycle | Persona/Graph/Node | REMOVE private Run lifecycle; route through canonical Run |
| `EvolutionCycle` / Hive evolution background loop | `maistro-evolve`, `backend/services/evolution.py` | Node/Graph workload + Schedule | Persona | population/tournament/eval nodes | runtime runs attempts | Persona/Graph/Node | KEEP semantics; replace private 300s loop with schedule -> Run |
| `PipelineGenome`, PopulationStore, promotion/rollback | `maistro-evolve` | Genome/templates + template promotion lifecycle | Persona | candidate definitions | none | explicit promotion gate | KEEP, connect promotion to Template provenance rather than live workspace mutation |
| tournament implementations in core/evolve | agents + evolve | evaluation policy/service | Eval Node | scoring/ranking | none | eval node | DUPLICATE-FAMILY: converge if semantics identical; otherwise name differences explicitly |
| evaluator/benchmark adapters | evolve benchmarks | NodeType(type=eval) / Binding | Graph | benchmark invocation/scoring | invocation | eval node/binding | KEEP |
| Turing integration/runtime | `maistro-turing`, integrations/turing | external capability/provider or specialized NodeTypes depending use | Persona/Node | proactive producers/chat | avoid separate Run lifecycle | binding/node | MAP case-by-case; preserve service boundary |
| Home Assistant / CoinSwarm integrations | `integrations/` | Binding/provider families + event producers | Node/Persona | REST/event adapters | invocation | binding | KEEP |
| event-trigger recipes | events recipes | GraphTemplate/Schedule-like trigger definitions | Persona | event -> graph activation | launch Run | persona/graph | REHOME |
| code registry | `code_registry/` | template/resource registry / Binding source | Persona/Node | executable code refs | none | scope | KEEP, clarify whether entries are templates, artifacts, or bindings |
| classifier / intent registry / Conduit | classifier, agents/conduit | routing policy into Persona/GraphTemplate/NodeTemplate selection | Workspace/Persona | intent/tier/model decisions | none | cannot select forbidden target | KEEP policy; route to canonical definitions |
| Hyperagent | agents/hyperagent | likely GraphTemplate/Graph composition, not primitive Agent type | Persona/Workspace | specialized node graph | graph execution | inherited | DECOMPOSE/MAP rather than preserve parallel execution ontology |
| Artificer / multi-phase engineering strategy | agents/artificer | GraphTemplate or Agent Node policy depending actual topology | Persona | phases/tools | graph/node execution | inherited | MAP by composition |
| PM orchestrator/waves/fan-in | orchestrator | Graph semantics / scheduling policy | Graph | parallel work/fan-in | generic mechanics through runtime | graph/node | KEEP semantics, remove duplicate mechanics |
| `ExecutionRuntime` / `PythonExecutionRuntime` (feature branch) | `maistro.runtime` | ExecutionRuntime | Run Attempt | concurrency/cancel/deadline/event sequence/metrics | canonical mechanics owner | receives already-authorized execution | KEEP |

## Node type normalization

The current repository supports or strongly implies these NodeType families. They should share a common Node envelope while retaining type-specific configuration contracts.

```text
Node
├── agent
├── graph                 # subgraph/composite node
├── harness
├── api/http
├── mcp
├── function/tool
├── human/hitl
├── transform
├── eval
├── sandbox/process
├── external-agent/a2a
└── integration-specific  # preferably reducible to protocol/binding over time
```

A Graph containing one Node is valid. This lets most special top-level `XRun` concepts collapse into ordinary `Run -> NodeRun(type=X)` without losing type-specific behavior.

A Graph Node may itself reference another Graph. That provides composition without making Graph primitive.

## Template mapping

### NodeTemplate candidates already in the repo

The following current objects likely contribute fields to NodeTemplate rather than remaining separate reusable-definition systems:

- Agent identity/spec definition fields
- agent recipes
- PM fleet definitions
- Builders worker/stage prompt + tool registrations
- Skill definitions after decomposition
- registered graph node kind defaults
- harness provider configuration presets
- evaluator presets

A NodeTemplate should be able to describe a concrete NodeType plus its default parameters, bindings, policy, permissions, schemas, and provenance.

### GraphTemplate candidates already in the repo

- saved DAG / `GraphConfig` definitions
- multi-stage Builders workflow
- Artificer/multi-phase workflows
- Hyperagent compositions
- event-trigger recipes where the trigger itself is separated from the graph definition
- PM fleet orchestration graphs
- reusable evolve/RSI workflows

The audit should not mechanically rename every `Recipe` to `GraphTemplate`. A recipe containing only one node's definition belongs as NodeTemplate; a recipe containing composition belongs as GraphTemplate.

## Builders mapping

Builders should become a Persona-exposed surface over the canonical objects:

```text
Persona: Builders
├── surfaces
│   ├── UI
│   ├── Builders CLI
│   └── Builders RSI (when permitted)
├── NodeTemplates
│   ├── Frank
│   ├── Mason
│   └── Auditor
└── GraphTemplates
    └── Builders workflow
```

Execution:

```text
Graph instance
├── Node(type=agent, template=Frank)
├── Node(type=agent, template=Mason)
└── Node(type=agent, template=Auditor)

Run
├── NodeRun(Frank/stage...)
├── NodeRun(Mason/stage...)
└── NodeRun(Auditor/stage...)
```

`BuildersRuntime` may remain temporarily as an adapter that knows how to dispatch these Node types, but it should not remain a second execution/runtime model.

## Permission convergence

Current permission/security concepts are spread across auth scopes, collaboration roles, delegation modes/allowlists, capability provider availability, tool allowlists, Warden/Sentinel gates, sequence policy, credential access, sandbox allowlists, promotion gates, and HITL approval.

These are not all the same kind of permission, but they need one evaluation chain.

Proposed evaluation shape:

```text
Identity authorization
  -> Workspace policy
  -> Persona policy
  -> Graph policy
  -> Node policy
  -> Binding availability + authorization
  -> Credential eligibility
  -> Invocation policy/security gates
  -> optional approval
```

Important distinction:

- **Permission** answers whether an actor/object may request an operation.
- **Policy** adds contextual/sequence/condition rules.
- **Binding** determines how an allowed capability is fulfilled.
- **Provider health** determines whether that fulfillment is currently available.

Do not collapse these into one `allowed: bool` abstraction.

## Lifecycle convergence

The repository currently has many lifecycle owners:

- Task status
- A2A task status
- A2A lifecycle manager
- GraphRun phase
- NodeRun phase
- DurableRun status
- DurableNodeRecord phase
- RSI run state
- Builders RunStatus
- scheduler execution history
- harness sessions
- collaboration sessions
- retries/circuit breakers

They should reduce to distinct axes rather than one mega-state enum:

```text
WorkRequest / queue lifecycle    # admission before a Run
Run lifecycle                    # logical work
NodeRun lifecycle                # one graph node in the logical work
Attempt lifecycle                # physical execution/retry/resume
Session lifecycle                # continuity, separate from Run
Provider health lifecycle        # availability, separate from Run
Schedule lifecycle               # trigger definition, separate from Run
```

Domain-specific phases such as planning/coding/reviewing belong in Graph/Node state or events, not the universal Run status enum.

## Storage and ownership rules

Durable ownership should follow the UX/domain hierarchy rather than implementation packages.

- User owns or participates in Workspaces.
- Workspace owns Persona configuration, editable Graph objects, Run history, workspace artifacts, and workspace-scoped credentials/policy.
- Persona owns reusable NodeTemplates and GraphTemplates visible within that Workspace context.
- Graph owns Nodes and Edges as an editable working object.
- Run references/snapshots the executable Graph; the Workspace owns the Run history.
- Run owns NodeRuns, Attempts, Run events, and Run artifacts.
- Session is owned at the appropriate user/workspace interaction scope and references Runs rather than containing their lifecycle.

Do not make Graph deletion destroy Run history. Runs should preserve enough graph snapshot/provenance to remain intelligible after the working Graph or template changes.

## Highest-value duplicate families to remove

### 1. Execution lifecycle duplicates

`TaskStatus`, `A2ATask`, `GraphRun`, `DurableRunRecord`, Builders `RunStatus`, and RSI local Run state currently overlap.

Target: canonical Run + NodeRun + Attempt, with adapters during migration.

### 2. Agent delegation duplicates

Direct agent delegation, `A2ADelegator`, A2A lifecycle workers, guest-peer delegation, and graph `agent.delegate_remote` overlap.

Target: Agent-backed Binding -> child Run -> durable wait/resume.

### 3. Tool/capability/skill/harness/API fulfillment duplicates

Target vocabulary:

```text
Capability -> Provider -> authorized Binding -> Invocation
```

ToolExposure is the model-visible projection of allowed bindings. Harness/MCP/HTTP/function/agent/human are fulfillment/protocol varieties, not independent execution roots.

### 4. Reusable definition duplicates

Agent recipes, skills, PM fleet definitions, Builders prompt/tool registries, DAG configs, and other recipe/config systems overlap with the new NodeTemplate/GraphTemplate model.

Target: preserve specialized authoring/import formats as projections, but converge durable reusable definitions.

### 5. Events and correlation IDs

Graph events, Builders stage events, collaboration events, integration events, audit records, tracing IDs, task IDs, run IDs, A2A task IDs and harness session IDs currently create fragmented observability.

Target: canonical owner IDs plus typed event projections. Session/provider IDs remain where semantically distinct.

## Implementation sequence implied by this matrix

1. Lock vocabulary and ownership semantics in ADR/spec after this matrix is reviewed.
2. Introduce canonical Workspace-compatible naming without destructive Project storage migration.
3. Introduce Persona and template provenance models.
4. Define canonical Run, NodeRun and Attempt lifecycle/persistence.
5. Adapt durable graph persistence to canonical Run without changing graph traversal semantics.
6. Route scheduler triggers through Run creation.
7. Convert TaskRunner from lifecycle owner to WorkRequest/admission -> Run adapter.
8. Convert A2A delegated tasks to child Runs while preserving trust/routing.
9. Normalize Agent definition into Genome + Bindings + Permission/Policy and remove runtime fields from reusable definitions.
10. Normalize ToolExposure/Skill/Capability/Provider/Binding/Invocation boundaries.
11. Map Builders CLI + Builders RSI to Persona-exposed surfaces and canonical Graph/Node templates.
12. Route RSI/evolve through Graph/Node + Run rather than private loops/lifecycles.
13. Converge artifacts/events/observability on canonical owner IDs.
14. Apply hierarchical permissions across User -> Workspace -> Persona -> Graph -> Node -> Binding -> Invocation.
15. Remove compatibility adapters and duplicate lifecycle/type families only after behavior-parity tests are green.

## Guardrail

Do not refactor a subsystem merely because its name differs from the canonical vocabulary. Merge only when semantics overlap. Preserve real distinctions such as Session vs Run, Provider vs Binding, Schedule vs Run, graph traversal vs runtime mechanics, and policy vs permission.

The success criterion is not fewer class names by itself. It is that every product capability can be placed unambiguously in the hierarchy, every execution can be traced through one Run/NodeRun/Attempt model, and no subsystem invents a second owner for the same lifecycle or permission decision.
