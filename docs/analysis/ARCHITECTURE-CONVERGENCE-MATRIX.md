# MAIstro Architecture Convergence Matrix

Status: working implementation map. This is intentionally not an ADR yet. It maps current repository concepts onto the UX-derived architecture so we can distinguish true domain concepts from duplicate ownership and compatibility layers.

## Canonical hierarchy

```text
User
└── Workspace[]
    ├── Persona
    │   ├── allowed surfaces
    │   ├── NodeTemplate[]
    │   └── GraphTemplate[]
    │
    ├── Graph[]
    │   ├── source_template_id/version?
    │   ├── Node[]
    │   └── Edge[]
    │
    ├── Session[]
    ├── Artifact[]
    └── Run[]
        ├── NodeRun[]
        │   └── Attempt[]
        ├── Event[]
        ├── ArtifactRef[]
        ├── Checkpoint[]
        └── child Run[]
```

Working decisions:

1. User owns one or more Workspaces.
2. Workspace owns one Persona.
3. Existing `Project` is the compatibility/storage ancestor of Workspace.
4. Existing `maistro.personas.PersonaTemplate` is the Persona system to extend. Do not introduce a second Persona model.
5. Persona owns reusable NodeTemplates and GraphTemplates plus purpose, brand, voice, allowed surfaces, defaults and evaluation definitions.
6. Workspace owns mutable instantiated Graphs and execution history.
7. Templates instantiate independent mutable objects with source-template provenance.
8. A single-node Graph is valid.
9. Run is universal logical execution history.
10. NodeRun is universal per-Node execution history.
11. Attempt is physical retry/execution identity.
12. ExecutionRuntime owns execution mechanics only.
13. Permissions narrow through `User -> Workspace -> Persona -> Graph -> Node -> Binding -> Invocation`.
14. Builders CLI and Builders RSI are Persona-authorized surfaces over the same objects exposed by UI.

## Primitive and fulfillment vocabulary

```text
Definition primitives
  Model
  PromptTemplate
  ParameterSet
  Schema
  Protocol
  Credential
  Permission
  Policy
  Predicate
  Transform

Genome
  = Model + PromptTemplate + ParameterSet

Agent
  = Genome + authorized Bindings/ToolExposure + Permission/Policy + Memory config

Capability
  -> Provider
      -> Binding
          -> Invocation
```

`ToolExposure` is the model-facing view of an allowed Binding. A delegated Agent can be the fulfiller behind a Binding, which makes agents-as-tools an ordinary capability-routing case rather than a separate runtime architecture.

Domain `Protocol` here means an interaction/transport contract such as HTTP, MCP, harness, human, process, or agent delegation. Python `typing.Protocol` interfaces are implementation contracts and are not themselves domain Protocol objects.

## Core convergence matrix

| Existing object / subsystem | Current owner | Canonical mapping | Action |
| --- | --- | --- | --- |
| Authenticated human/service | `auth`, security auth adapters | User/Principal | KEEP; standardize Principal/PermissionContext handoff |
| `Project` / `project_id` | `projects`, persistence, APIs, durable runs, memory | Workspace compatibility representation | CONVERGE semantically; preserve storage/API compatibility |
| `Project.use_case`, profile/UI purpose fields | `projects` | Persona reference/defaults | MOVE/PROXY toward existing Persona |
| `PersonaTemplate(kind="workspace")` | `personas` | Persona | KEEP + EXTEND |
| Persona brand/voice/ui_scope/interview | `personas` | Persona purpose/surface config | KEEP |
| Persona spawns/tools/skills/evals | `personas.expander` | NodeTemplate/GraphTemplate/default Bindings/evaluation definitions | CONVERGE |
| Agent recipes | `agents/recipes` | NodeTemplate or GraphTemplate depending shape | SPLIT by semantic shape |
| PM Fleet definitions | `agents/pm_fleet` | Persona + Agent NodeTemplates + GraphTemplates | REHOME |
| `AgentIdentity` | `types.agent`, agents | Agent definition / Agent NodeTemplate content | DECOMPOSE into Genome, bindings, permissions, memory, provenance |
| `AgentCard` | portability/A2A | interoperable Agent template projection | KEEP projection |
| reusable portion of `AgentSpec` | agents spec | Agent/Node definition | SPLIT from run-time context |
| task/attempt/upstream fields in `AgentSpec` | agents spec | NodeRun/Attempt context | MOVE to execution record/context |
| Agent strategies | `agents/strategies` | Agent Node execution behavior/policy | KEEP, no independent lifecycle |
| model-facing agent tool list | agents | ToolExposure | CONVERGE from raw names to authorized Binding view |
| `AgentTask` | `types.agent` | delegated WorkRequest + child Run projection | DECOMPOSE; remove status as independent lifecycle |
| `AgentResponse` | `types.agent` | NodeRun/Invocation result projection | KEEP adapter; canonical result IDs/status elsewhere |
| `ModelConfig`, `ProviderConfig`, `ModelSelection` | `types.model`, router/providers | model/provider routing value types | KEEP as routing DTOs, not domain ownership |
| prompt approval types | `types.prompt`, prompts | domain-specific approval request over generic human approval capability | CONVERGE fulfillment, preserve prompt workflow |
| prompt manager/store | `prompts` | PromptTemplate repository/version service | KEEP, attach to Persona/NodeTemplate |
| graph definition / `GraphConfig` | `graph`, Hive DAGs | Graph / GraphTemplate | CONVERGE |
| graph node definitions | `graph/nodes` | Node + NodeType | KEEP behavior, normalize envelope |
| graph edge definitions | `graph` | Edge + Predicate/mapping | KEEP |
| DAG registry | `graph/dag_registry` | Graph/GraphTemplate catalog/repository helper | KEEP specialized catalog, align ownership |
| DAG validator | `graph/dag_validator` | Graph validation service | KEEP |
| `NodeExecutor` | `graph/node` | Node fulfillment adapter seam | KEEP until Binding convergence proves cleaner replacement |
| `NodeRun` | `graph/node` | NodeRun + Attempt mechanics currently mixed | DECOMPOSE |
| `GraphRun` | `graph/run` | Run + GraphExecutionState | DECOMPOSE; preserve traversal semantics |
| `DurableRunRecord` | `graph/durable_runs` | persisted Run + GraphExecutionState projection | CONVERGE behind canonical Run repository |
| durable node record | durable runs | persisted NodeRun projection | CONVERGE |
| durable executor | durable runs | Graph domain executor/checkpoint adapter | KEEP until graph parity tests permit consolidation |
| graph concurrency helpers | `graph/concurrency` | runtime mechanics plus graph policy | SPLIT generic mechanics to ExecutionRuntime only where equivalent |
| graph compaction/depth | `graph` | Graph-domain optimization/validation | KEEP |
| `GraphOptimizer` | `graph/optimizer` | template/definition improvement proposal service | KEEP; promotion should create template versions rather than mutate execution history |
| orchestration planner/validation | `orchestrator` | Graph construction/validation semantics | KEEP |
| hierarchy/master orchestration | `orchestrator` | Graph coordination semantics | KEEP |
| waves/fan-out/fan-in | `orchestrator/waves` | graph semantics + generic runtime mechanics | SPLIT only generic mechanics |
| `Conduit` | core | front-door routing into Workspace/Persona/Graph/Run flow | KEEP; never merge into ExecutionRuntime |
| classifier | `classifier` | request interpretation/planning service | KEEP |
| router | `router` | model/provider selection policy | KEEP |
| LLM provider registry/router | `providers` | Model Provider selection/service | KEEP, distinguish from generic capability Provider if needed by name |
| process config/presets | `config` | deployment/default configuration | KEEP; may seed Persona/templates but not own mutable Workspace state |
| `CapabilityRegistry` | `capabilities` | Capability + Provider registry | KEEP |
| `CapabilityProvider` | capabilities | Provider | KEEP |
| capability slots | capabilities | typed Capability/Provider contracts | KEEP |
| consumer authorization/configuration for a provider | fragmented today | Binding | INTRODUCE/CONVERGE explicitly |
| actual provider/tool/harness call | fragmented today | Invocation | INTRODUCE/CONVERGE explicitly |
| `HarnessRunner` | capability slot/providers | foreign executor Protocol/Provider | KEEP |
| `HarnessSessionManager` | capabilities | sessionful Binding/Invocation adapter | KEEP |
| `HarnessNodeExecutor` | graph | Node fulfillment adapter using harness Binding | KEEP |
| durable harness dispatch/handles | graph harness | durable-asynchronous Invocation variant | CONVERGE lifecycle vocabulary |
| HTTP clients/integrations | tools/integrations/providers | Protocol + Provider/Binding implementations | KEEP |
| MCP server/tool definitions | Hive/portability | Protocol + Binding + ToolExposure | KEEP as interoperability |
| concrete tools | `tools` | Provider/Binding implementations | KEEP |
| approval/reversibility/sandbox metadata | tools/security | Binding/Invocation policy attributes | CONVERGE |
| `SkillDefinition` | skills/types | composite reusable package of prompt/schema/capability/exposure/binding/provenance | DECOMPOSE conceptually; keep Skill product format |
| skills parser/loader/catalog/marketplace | skills | template/capability catalog/import services | KEEP |
| portability import/export | portability | external-format adapter into canonical templates/capabilities | KEEP |
| delivery protocol/registry | delivery | Capability/Provider/Binding family | KEEP |
| Home Assistant/CoinSwarm/ntfy/Turing integrations | integrations | Providers/Bindings plus event sources/sinks | KEEP |
| sandbox Docker/microVM/fake backends | tools/sandbox | process-isolation Provider/Binding infrastructure | KEEP |
| credential pool/providers/store/rotation | credentials | Credential resource + resolution infrastructure | KEEP; resolve material at Invocation |
| Conductor cryptographic seed/DID/signing | identity | root-of-trust infrastructure | KEEP |
| agent identity lifecycle | identity/lifecycle | Agent identity/security resource | KEEP, link to canonical Agent definition |
| `CapabilityToken` | identity/lifecycle | delegated authorization credential | KEEP; do not confuse with Capability |
| auth scopes | auth | principal authorization input | CONVERGE into hierarchical PermissionContext |
| Warden/Sentinel/Gate | security | security/policy enforcement | KEEP; require actual execution-path reachability |
| sequence policy engine | policy | Policy evaluator | KEEP beneath Permission ceiling |
| governance ConformanceEngine | governance | ADR/Spec/prior-policy conformance service | KEEP as governance/policy input; not Run lifecycle |
| self-repair provider | capabilities/providers/self_repair | CapabilityProvider invoked by scheduled/event Node/Run | KEEP provider; remove need for private background lifecycle |
| infra monitor/action slots | capabilities | Capabilities/Providers/Bindings | KEEP |
| self-repair SafetyGovernor | capabilities | domain Policy | KEEP |
| generic `State` SQLite singleton writer | `state.py` | persistence/backpressure infrastructure | KEEP below repositories; not execution state |
| `PersistedStore` | `state.py` | generic persistence adapter | KEEP; avoid making KV namespace authoritative domain model |
| Postgres/SQLite stores | persistence | repository adapters | KEEP |
| memory stores/scopes/outcomes/learnings | memory | scoped resource/knowledge service | KEEP, align scope IDs |
| repertoire recall/rehearse/compose | repertoire | learned-pattern/planning service | KEEP; `run.py` is naming collision only |
| codebase index/parser | codebase | Workspace knowledge resource | KEEP |
| code registry | code_registry | trusted-code/provenance resource | KEEP |
| Session store/search | sessions | Session continuity | KEEP distinct from Run |
| collaboration membership/presence/events | collaboration | Session collaboration resource | KEEP, inherit Workspace permission ceiling |
| EventBus/durable log/invocations/triggers | events | canonical event infrastructure candidate | KEEP + CONVERGE other event families onto it |
| graph events | graph/events | graph-specific Event projections | CONVERGE envelope/correlation |
| Builders StageEvent | builders | NodeRun/Run Event projection | CONVERGE |
| task progress/webhooks | tasks | Event projection/delivery adapter | CONVERGE |
| observability logging/metrics/tracing/replay | observability | canonical event/ID projections | KEEP |
| quota/billing/reconciliation | quota | accounting/entitlement service | KEEP; correlate to Workspace/Run/NodeRun/Invocation |
| `TaskCreate`/Task | tasks | WorkRequest/ingress | KEEP request concept |
| Task status | tasks | queue state + duplicate Run lifecycle + domain phases | SPLIT |
| TaskQueue | tasks | ingress queue | KEEP |
| TaskRunner | tasks | admission/dispatch adapter | DECOMPOSE; dequeued request eventually creates Run |
| lane gate | tasks/lanes | scheduling/admission policy | KEEP; do not flatten policy into generic semaphore |
| checkpoints/replay | tasks + durable graph | Checkpoint/reconstruction services | CONVERGE ownership under Run/NodeRun/Attempt |
| task recovery | tasks/recovery | recovery eligibility/version/crash-loop Policy | KEEP, operate on canonical persisted execution |
| resilience error classifier | resilience | Provider/Attempt failure classification | KEEP |
| resilience retry/backoff | resilience | Attempt/Invocation retry Policy | KEEP |
| resilience fallback | resilience | Provider/Binding fallback Policy | KEEP |
| resilience rate coordination | resilience | shared provider/concurrency policy | KEEP, connect to runtime/provider metrics |
| Schedule | scheduling | Schedule/trigger definition | KEEP distinct from Run |
| schedule execution history | scheduling/Hive | Run reference/trigger history | CONVERGE |
| A2A broker/delegator | a2a | Agent-backed Binding/routing service | KEEP transport/routing |
| A2A task/lifecycle queue | a2a | duplicate child-work lifecycle | MERGE into child Run after parity |
| guest peers | a2a | remote Agent Binding + trust | KEEP |
| `agent.delegate_remote` node | graph nodes | delegation Node using child Run/wait | KEEP behavior |
| HITL nodes | graph nodes | Node(type=human) | KEEP |
| capability approval slot/provider | capabilities | generic human Approval Capability/Provider | KEEP as common fulfillment mechanism |
| tool `ApprovalGate` | tools/approval | domain adapter to generic approval capability | CONVERGE fulfillment, preserve impact semantics |
| learning promotion approval | memory/learnings | domain workflow using human approval | CONVERGE fulfillment, preserve promotion state machine |
| prompt promotion approval | prompts/types | domain workflow using human approval | CONVERGE fulfillment, preserve versioning state machine |
| self-repair approval | self_repair/infra_action | domain workflow using human approval | CONVERGE fulfillment |
| governance/human review for prose invariants | governance | domain workflow using human approval | ADAPT to common mechanism when operationalized |
| shared `maistro.types` package | core | DTO/value-type namespace | KEEP; living in `types` does not imply semantic ownership |

## Product/application matrix

| Existing application | Canonical expression | Action |
| --- | --- | --- |
| Builders | Persona + Frank/Mason/Auditor NodeTemplates + GraphTemplates + UI/CLI/RSI surfaces | CONVERGE contracts/runtime onto canonical objects |
| Builders `RunRequest`/`RunResult` | Run/NodeRun adapter projections | MERGE lifecycle semantics |
| BuildersRuntime | specialized node/stage handler dispatcher | KEEP adapter, stop presenting as universal runtime |
| PM Fleet | Persona + Agent NodeTemplates + GraphTemplates | REHOME existing definitions |
| Canvas/book maker | specialized Persona + domain artifacts + image/compositor/export Nodes/Bindings | KEEP domain semantics, share ownership/execution |
| Design | specialized Persona/domain assets + renderer Providers/Bindings + design Nodes | KEEP domain semantics, share ownership/execution |
| Turing | Persona/Agent semantic extensions + Memory + triggers + canonical Runs | KEEP semantics, remove parallel execution identity |
| RSI | Persona surface/workload producer + Graph/Nodes + Run | CONVERGE private lifecycle |
| Evolve | evolution domain state + Eval Nodes + template promotion | KEEP domain state, share execution/audit IDs |

## Interface and shell matrix

| Surface | Canonical role | Action |
| --- | --- | --- |
| Hive Conductor frontend/API | primary workspace-centric product shell | KEEP; thin duplicate services/stores onto canonical core services |
| maistro-server | generic API/compatibility shell | KEEP; same domain services as Hive |
| Builders CLI/TUI | Persona-authorized Builders surface | KEEP |
| Builders RSI CLI | Persona-authorized Builders surface | KEEP |
| maistro-rsi CLI | Persona-authorized RSI surface | KEEP, map work to Runs |
| MCP | interoperability surface/protocol | KEEP |
| harness session API | foreign-harness interface | KEEP, correlate durable work with Runs |
| chat-completions API | compatibility interface | KEEP, route through Conduit/Persona/Run as appropriate |
| WebSocket/SSE | event/progress transport | KEEP, consume canonical events |

## Engineering/platform matrix

| Existing subsystem | Plane | Action |
| --- | --- | --- |
| maistro-bootstrap installer/materializer | platform/install | KEEP; audit mixed Builders/runtime responsibilities before any split |
| maistro-registry ADR/SPEC validator/DAG | engineering governance | KEEP; physical rename is only a candidate |
| CI workflows | engineering control | KEEP |
| formal conformance | engineering control | KEEP and add canonical architecture invariants |
| mutation testing | engineering control | KEEP |
| security scans | engineering control | KEEP |
| quality reachability baseline | engineering control | KEEP and use as island burn-down metric |
| radon/vulture/enumeration baselines | engineering control | KEEP |
| repo-native `.claude`/`.cursor`/AGENTS/CONTRIBUTING guidance | engineering-agent control | UPDATE after vocabulary is locked |

## Registry/catalog family

Do not create one generic `Registry` abstraction just because the repository has many registries.

| Registry/catalog | What it indexes | Canonical meaning |
| --- | --- | --- |
| CapabilityRegistry | Capability Providers | capability infrastructure |
| ProviderRegistry | LLM Providers | model provider infrastructure |
| DAG registry | Graph/GraphTemplate definitions | graph catalog/repository helper |
| AgentCatalog | Agent definitions/templates | template catalog |
| Skill registry/catalog | Skills | reusable package/catalog |
| CodeRegistry | trusted code/provenance | trust resource |
| IntentRegistry | classifier intent definitions | routing configuration |
| maistro-registry | ADR/Spec documents | engineering governance |

`Registry` is a storage/indexing pattern. The thing being registered determines domain ownership.

## Approval family

Do not merge domain state machines merely because they all need a human decision.

Canonical split:

```text
Domain workflow
  -> ApprovalRequest payload
      -> human Approval Capability / Binding
          -> ApprovalDecision
              -> domain-specific transition
```

Examples:

- irreversible/reversible tool plan approval
- prompt version promotion
- learning promotion
- HITL question/review/edit
- self-repair action approval
- governance human review
- future template/evolution promotion

Share the human fulfillment mechanism, event/correlation IDs, actor identity, timeout/escalation mechanics and audit trail. Preserve each domain's transition rules.

## Identity and token family

Keep these distinctions explicit:

- Principal: authenticated human/service actor.
- Agent identity: cryptographic/runtime identity of an Agent entity.
- DID/signing key: proof material.
- CapabilityToken: delegated authorization credential.
- Permission: allowed action scope inherited through hierarchy.
- Policy: contextual/stateful decision inside that scope.
- Credential: secret/resource needed by a Binding.
- Capability: semantic ability.

A `CapabilityToken` authorizes; it is not a Capability and it is not a Binding.

## Optimization and learning family

Current improvement mechanisms include GraphOptimizer prompt rewriting, memory learnings/promotion, repertoire, Evolve mutation/crossover/tournament, Persona scoring/golden records, Agent feedback and RSI hypotheses.

Canonical direction:

```text
observations / outcomes / traces
  -> evaluation
      -> proposed definition change
          -> approval/policy
              -> new NodeTemplate / GraphTemplate / Persona/domain-asset version
```

Do not mutate completed Run history. Do not silently rewrite existing instantiated Graph/Node objects unless the product explicitly asks for live mutation. Learning should normally promote a reusable definition/version that future instances or Runs can choose.

## State vocabulary guardrail

Several unrelated things are currently called state:

- generic SQLite `State` writer infrastructure
- Workspace/domain object persistence
- GraphExecutionState/blackboard
- Run lifecycle state
- NodeRun state
- Session continuity state
- policy sequence state
- provider health/circuit state
- evolution population state
- frontend/UI state

Do not unify these into one `State` object. Normalize identity/ownership and persistence boundaries, not the data itself.

## Duplicate-ownership families to eliminate

1. **Execution lifecycle**: GraphRun, DurableRunRecord, Task status, A2A task status, Builders RunStatus, RSI/Hive run state -> Run/NodeRun/Attempt.
2. **Delegation lifecycle**: direct Agent delegation, A2A broker/lifecycle, guest peers, remote-delegation Node -> Agent-backed Binding + child Run.
3. **Fulfillment**: tool, harness, HTTP, MCP, sandbox, renderer, delegated Agent, human -> Capability/Provider/Binding/Invocation.
4. **Definitions**: AgentIdentity/Card/recipes, Persona spawns, DAG configs, PM roles, Builders definitions, imported formats -> NodeTemplate/GraphTemplate/domain assets.
5. **Events/correlation**: graph events, core events, Builders StageEvent, task progress, Hive streams, audit/observability -> canonical event envelope/IDs.
6. **Permissions/trust**: auth scopes, Project roles, collaboration roles, trust tiers, tool allowlists, delegation modes, approvals, promotion gates -> hierarchical Permission ceiling + Policy/security mechanisms.
7. **Product identity**: Project use_case/UI/profile and Persona workspace semantics -> Workspace ownership versus Persona purpose/surfaces/templates.
8. **Product-shell state**: Hive/server local stores duplicating core domain ownership -> transport/application adapters.
9. **Approval fulfillment**: multiple human decision plumbing implementations -> one approval capability with domain-specific adapters/state machines.
10. **Improvement mutation**: graph optimizer, memory learning, Evolve/RSI promotion -> versioned template/domain-definition promotion rather than hidden live mutation.

## Distinctions that must survive convergence

- User != Workspace
- Workspace != filesystem workdir
- Workspace != Persona
- Persona != Agent
- Template != instantiated mutable object
- Graph != Run
- Node != NodeRun
- Run != Attempt
- Session != Run
- Schedule != Run
- WorkRequest != Run
- Capability != Provider
- Provider != Binding
- Binding != Invocation
- CapabilityToken != Capability
- Permission != Policy
- Credential != Binding
- Event != Artifact
- approval fulfillment != domain approval workflow
- graph semantics != runtime mechanics
- persistence `State` != execution state
- evolution population state != Run state
- product/domain packages != engineering control plane

## Implementation sequence

1. Lock vocabulary and object ownership in ADR/spec after the inventory stops producing new universal concepts.
2. Preserve `Project`/`project_id` compatibility while introducing Workspace-facing naming and a first-class link to the existing Persona system.
3. Extend/converge existing `PersonaTemplate`; add NodeTemplate/GraphTemplate ownership and provenance semantics.
4. Define canonical Run/NodeRun/Attempt schema, persistence, terminalization, parent/child, cancellation, timeout, retry and pause/resume.
5. Put durable graph execution behind ExecutionRuntime only after interruption terminalization is safe.
6. Write behavior-parity tests for legacy GraphRun versus durable traversal before deleting either path.
7. Route Schedule -> Run launcher and Task WorkRequest -> admission -> Run.
8. Convert delegation to Agent-backed Bindings and child Runs.
9. Normalize Agent -> Genome + authorized Bindings/ToolExposure + Permission/Policy + Memory configuration.
10. Add explicit Binding/Invocation around existing CapabilityProvider machinery.
11. Converge human approval fulfillment while preserving prompt/tool/learning/HITL/self-repair domain transitions.
12. Make Builders UI/CLI/RSI Persona surfaces over canonical Graph/Node/Run objects.
13. Route RSI/Evolve/Turing/self-repair periodic or proactive work through Schedule/Event -> Run.
14. Converge event/correlation IDs and attach artifacts/memory/observability/quota to canonical ownership.
15. Implement hierarchical Permission evaluation and route real Binding/Invocation paths through security/policy/credential resolution.
16. Thin Hive and maistro-server duplicate lifecycle/storage wrappers.
17. Burn down the existing reachability baseline as formerly disconnected features gain real product entry points.
18. Update ADR/SPEC governance, formal invariants, architecture fitness rules and repo-agent guidance to the locked vocabulary.
19. Remove compatibility adapters only after parity and migration tests are green.

## Exit criteria for this matrix

For every meaningful subsystem, the repository should be able to answer:

```text
thing
-> canonical concept
-> parent/owner
-> lifecycle owner
-> persistence owner
-> permission scope
-> product entry point
-> keep / split / merge / rehome / remove
```

The architecture is converged when a Persona-authorized surface reaches the same objects everywhere:

```text
User
 -> Workspace
 -> Persona
 -> Graph / Node
 -> Run / NodeRun / Attempt
 -> Binding / Invocation
```

with one execution identity model, one permission hierarchy, one event/correlation model, shared resources, and specialized packages contributing domain semantics without creating parallel universal runtimes.
