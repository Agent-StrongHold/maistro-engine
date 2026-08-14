# MAIstro Ecosystem Inventory

Status: working inventory for architecture convergence. Descriptive where the repository is being mapped; normative only where a decision is explicitly marked **Working decision**.

Purpose: identify everything that exists in the MAIstro ecosystem, place it in the intended product/domain hierarchy, separate legitimate specialization from duplicate ownership, and expose the seams that let the repository be stitched together cleanly.

This inventory is not trying to minimize class count. It is trying to make each concept have one clear owner and make every subsystem either reachable through the product model or intentionally outside it as platform/control-plane infrastructure.

## 1. Canonical product/domain hierarchy

**Working decision:** a User owns one or more Workspaces. A Workspace owns one Persona. The Persona owns the reusable NodeTemplate and GraphTemplate library for that Workspace and defines the Workspace's purpose/theme/surfaces/defaults. The Workspace owns mutable Graph objects and execution history.

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
    │   │   ├── source_template_id/version?
    │   │   ├── NodeType
    │   │   ├── Parameters
    │   │   ├── Bindings
    │   │   ├── Permissions
    │   │   └── Policy
    │   └── Edge[]
    │
    ├── Session[]
    ├── Artifact[]
    └── Run[]
        ├── graph snapshot/reference
        ├── NodeRun[]
        │   └── Attempt[]
        ├── Events
        ├── Artifacts
        ├── Checkpoints
        ├── child Run[]
        └── Outputs
```

### Template semantics

```text
NodeTemplate  -> instantiate -> Node  -> mutate -> optionally save as new NodeTemplate
GraphTemplate -> instantiate -> Graph -> mutate -> optionally save as new GraphTemplate
```

Instantiation is copy plus provenance, not live inheritance. A template can be edited/versioned without silently changing existing Workspace objects. A mutated Node or Graph can be promoted/saved as a new template version or a new template.

### Single-node graphs

**Working decision:** a one-node Graph is valid and is the normal simplifier for work that otherwise looks like an AgentRun, HarnessRun, EvalRun, HITLRun, API run, etc.

```text
Graph
└── Node(type=agent)

Run
└── NodeRun(type=agent)
```

The top-level lifecycle therefore does not need AgentRun/HarnessRun/EvalRun/HITLRun classes as independent architectural roots. Type-specific behavior lives in Node/NodeRun details.

## 2. Lower-level vocabulary

### Reusable primitives

```text
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
ArtifactRef
Event
```

### Intelligence composition

```text
Genome
├── Model
├── PromptTemplate
└── ParameterSet

Agent
├── Genome
├── authorized Bindings / ToolExposure
├── Permission ceiling
├── Policy
└── Memory configuration
```

An Agent is a reusable executable definition/behavior, not a top-level process lifecycle.

### Capability fulfillment

```text
Capability
    ↓
Provider
    ↓
Binding
    ↓
Invocation
```

- **Capability**: semantic ability that may be requested.
- **Provider**: available implementation candidate, including health/fallback/selection concerns.
- **Binding**: consumer-specific configured and authorized route from a Persona/Node to a fulfiller.
- **Invocation**: one actual call/turn through a Binding.
- **ToolExposure**: model-visible name/schema for an allowed Binding/capability.

This supports agents-as-tools naturally. If Agent A is not permitted/configured to fulfill capability X, Agent A may have a Binding to Agent B, and Agent B can fulfill X under its own narrower configuration/permissions.

## 3. Permission model

**Working decision:** permission constrains downward.

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

A child can narrow authority but cannot widen authority granted by an ancestor. Policy evaluates contextual/stateful rules inside that ceiling. Credentials are resolved only after the effective permission/policy path permits the Binding/Invocation.

## 4. Ecosystem planes

MAIstro is not one class tree. It is several planes around one product spine.

### Product ownership plane

- User / Principal
- Workspace
- Persona
- NodeTemplate
- GraphTemplate
- Graph
- Node
- Run
- NodeRun
- Attempt

### Definition and knowledge plane

- Agent definitions / genomes
- prompts
- models/parameters
- agent recipes
- Persona templates
- skills
- repertoire
- memory
- codebase index
- code registry
- design systems/domain assets
- portability/import-export

### Capability and fulfillment plane

- capability slots
- providers
- bindings
- tools
- integrations
- delivery
- harnesses
- HTTP/MCP
- credentials
- sandboxes/processes
- delegated agents
- human interaction

### Execution plane

- Run / NodeRun / Attempt
- ExecutionRuntime
- graph traversal
- task ingress/admission
- schedules
- checkpoints/pause/resume
- retry/recovery
- cancellation/deadlines
- concurrency/backpressure

### Security and trust plane

- authentication/principals
- agent identity lifecycle
- hierarchical permissions
- policy engine
- Warden
- Sentinel
- Gate
- approvals
- delegability
- reversibility
- elevation/strikes
- sandbox/network/filesystem restrictions
- provenance/signatures/trust

### Resource/data plane

- memory
- sessions
- collaboration/presence
- artifacts/files
- events
- quota/accounting
- persistence
- observability/replay

### Product/persona application plane

- Builders
- Builders RSI
- PM Fleet
- Canvas/book maker
- Design
- Turing
- RSI/Evolve

### Interface plane

- Hive Conductor UI/API
- maistro-server API
- chat-completions compatibility
- WebSocket/SSE
- Builders CLI/TUI
- Builders RSI
- maistro-rsi CLI
- MCP
- harness session API
- imported/external agent interfaces

### Platform/install plane

- maistro-bootstrap
- process/deployment configuration
- migrations
- install/upgrade/release artifacts

### Engineering control plane

- maistro-registry
- ADR/SPEC lifecycle
- CI
- quality/reachability ratchets
- formal conformance
- mutation testing
- security scans
- release promotion
- repo-native agent rules/skills

## 5. Existing Workspace and Persona anchors

This is the most important repository discovery from the inventory pass.

### `maistro.projects.Project` is already Workspace in all but name

Its source explicitly calls Project a per-user workspace and says it scopes outcomes, DAGs, integration resources, optimizer settings and durable runs through `project_id`.

Existing Project responsibilities include:

- project/workspace identity
- owner and member roles
- profile/context
- Jira/Airtable/repository resource bindings
- DAG/run scoping
- outcomes/memory scoping
- optimizer/evaluation settings
- budget-like settings
- use-case/UI selection

Canonical split:

```text
Project today
   ↓
Workspace
├── ownership/membership
├── resources/integration bindings
├── workspace context/data
├── Graph objects
├── Run history
├── Sessions/Artifacts
└── Persona reference
```

Fields that describe product identity/purpose/UI belong conceptually to Persona rather than Workspace. Storage/API compatibility can preserve `Project`/`project_id` during migration while the domain vocabulary becomes Workspace.

### `maistro.personas` already implements the Persona concept

Do not introduce a second Persona model.

Current `PersonaTemplate` supports:

- kinds including `workspace`
- brand
- voice
- UI scope
- onboarding interview
- eval rubrics
- spawns
- tools and skills per spawned agent
- reasoning strategy
- hard gates
- scoring/evaluation relationships

The Persona expander already maps spawn declarations to AgentRecipe records and governance state. The persona package also includes rubric/scoring, golden records, checklists, vocabulary and template loading.

Canonical evolution:

```text
Persona
├── purpose / brand / voice
├── allowed surfaces
├── onboarding/interview
├── evaluation definitions
├── permissions/policies/defaults
├── NodeTemplate[]
├── GraphTemplate[]
└── default capability/binding exposure
```

**Working decision:** one Workspace owns one Persona. If multiple modes are later desired, model that intentionally rather than letting Workspace and Persona both independently carry `use_case`/UI-purpose state.

## 6. Repository package ecosystem

### `maistro-core`

Role: shared domain/platform library and main home for reusable MAIstro semantics.

Major families present:

- agents, recipes, PM fleet, specialist agents, strategies, feedback
- A2A delegation/broker/lifecycle/guest peers
- auth and identity lifecycle
- builders
- capabilities/providers/slots/discovery/harness manager
- classifier, router and Conduit
- codebase and code registry
- collaboration
- config/model resolution
- credentials
- delivery
- events/triggers/invocations/durable log
- graph/DAG/nodes/durable runs/harness adapters
- integrations
- memory/learnings/outcomes
- observability/replay/tracing/metrics
- orchestrator/planner/hierarchy/waves
- personas
- projects
- persistence
- policy
- portability
- prompts
- providers/LLM routing
- quota/billing
- repertoire
- resilience/recovery/circuit breakers
- scheduling
- security/Warden/Sentinel/Gate
- sessions
- skills/marketplace/import/forge/fixer/canary
- task queue/runner/lanes/checkpoints/replay
- tools/browser/git/sandbox/approval/etc.
- shared types/protocols

Canonical role: authoritative home for reusable concepts/services. App-specific UX semantics should remain in product packages or Persona definitions.

### `hive-conductor`

Role: main Mission Control/product shell with frontend and backend routes/services.

Current app surfaces cover:

- workspaces/projects
- chat/sessions
- agents
- memory
- DAG execution
- schedules
- CLI exposure
- MCP servers/tools
- harness sessions
- RSI/evolution
- integrations
- providers
- audit/security/admin
- files/containers/settings
- app-specific stores/services

Canonical direction: keep product/UI behavior, but consume canonical Workspace/Persona/Graph/Run/resource services rather than owning parallel lifecycle/stores where core already has them.

### `maistro-server`

Role: generic FastAPI transport shell.

Current responsibilities include task APIs, task WebSocket progress, chat-completions compatibility, health/readiness, lifecycle wiring, PM-fleet seeding and core container wiring.

Canonical direction: interface adapter over the same Workspace/Persona/Graph/Run model. Avoid a second task/run/domain model.

### `maistro-canvas`

Role: reusable canvas/compositor/image pipeline plus book-maker frontend/application.

Useful domain semantics include:

- canvas tool/executor
- compositor/RGBA assembly
- canvas store
- image-generation protocol/client
- export
- book-maker UI/domain flow

Canonical mapping:

- compositor/image operations -> specialized NodeTypes/Bindings
- book maker -> Persona/product surface
- canvas documents/assets -> Workspace/domain artifacts
- execution -> canonical Graph/Run/NodeRun

### `maistro-design`

Role: composable design engine, design skills/systems, renderer/provider ecosystem and persisted design projects.

Current concepts include DesignEngine, DesignProject, DesignSkill, DesignSystem, renderer registry/discovery, render slots/providers, HTML/SVG/typography renderers, trust/review/scanners, catalog/import/bundles and artifact node/kinds.

Canonical mapping:

- DesignSkill -> domain NodeTemplate/Capability asset
- DesignSystem -> Persona-scoped reusable domain asset/template
- DesignProject -> Workspace domain object/artifact set
- Renderer/RenderProvider -> Provider/Binding
- RenderSlot -> Capability
- DesignEngine -> domain adapter/orchestrator, not ExecutionRuntime
- package trust/review -> domain Policy under canonical Permission ceiling

### `maistro-evolve`

Role: evolution/optimization semantics.

Current concepts include genome/population, mutation/crossover, EvolutionCycle, fitness, tournament/Elo, reflection, evaluation harnesses, benchmark adapters, promotion/rollback and audit trail.

Canonical mapping:

- genome -> reusable definition composition
- population/tournament -> evolution domain state
- EvolutionCycle -> Graph/Node workload producing a Run
- eval harness/benchmarks -> Eval NodeTypes/Bindings
- promotion -> template/version governance
- rollback -> selection/governance, not execution rollback

Do not conflate Evolve domain `Genome` with an Agent Genome blindly. Normalize shared model/prompt/parameter primitives while preserving pipeline/evolution-specific fields.

### `maistro-rsi`

Role: recursive self-improvement over the MAIstro codebase, composing sandboxing, git/self-branch flow, Evolve benchmarks/tournament, hypotheses, quota/model scheduling and PR workflow.

Canonical mapping:

- Builders RSI / RSI behavior -> Persona-exposed surface/capability
- RSI cycle -> Graph/Run
- sandbox -> Provider/Binding
- git/self-branch operations -> Nodes/Bindings
- eval -> Eval Nodes
- autorun/quota burn -> scheduling policy creating Runs

### `maistro-turing`

Role: autonoetic/self-model extension with self model, mood/personality/drives, proactive producers, actor/chat runtime, cognition stages, memory extensions and providers/tools.

Canonical mapping:

- persona-level personality/purpose -> Persona
- agent-specific cognition/personality -> Genome/Agent definition
- proactive producer -> Schedule/Event trigger/NodeTemplate
- actor/chat work -> canonical Graph/Run
- memory extensions -> Memory scoped to Persona/Agent/Session
- providers/tools -> Capability/Provider/Binding

### `maistro-bootstrap`

Installer/bootstrap/materialization tooling. Keep outside product runtime ontology.

### `maistro-registry`

ADR/SPEC dependency/lifecycle registry and governance CLI. Keep in engineering control plane, distinct from runtime capability/agent registries.

## 7. Conduit, classifier, router and providers

### Conduit

The current source explicitly calls Conduit the request pipeline through which requests flow and states that it decides/delegates rather than executing tasks directly.

Current flow:

```text
Gate
 -> classify intent
 -> resolve specialist Agent
 -> select execution tier
 -> dispatch
```

Canonical role: front-door request routing into the active User/Workspace/Persona context, then Graph/Run creation or another appropriate Persona-authorized interaction flow. Do not merge Conduit with ExecutionRuntime.

### Classifier

Intent/complexity/multi-intent/keyword/fallback decision service. It interprets requests but does not own Run lifecycle.

### `router` and `providers`

- `router`: selection/scoring/scarcity/speed mechanisms.
- `providers`: LLM provider registry/config/protocols/router/types.

Canonical role: model/provider selection when resolving a Model/Binding for a Node/Attempt. Provider choice should not become Workspace/Persona ownership state unless explicitly pinned.

### `config`

Loader, settings, presets, model resolver, rate limits and config models.

Canonical role: deployment/default configuration. Config/presets may seed Persona/Template defaults, but mutable Workspace objects should not be aliases to process config.

## 8. Agent ecosystem

### `AgentIdentity`

Current definitions combine model, prompt refs/fallbacks, constraints, tools, skills, rules, trust, delegation, strategies, memory, phases and provenance/review metadata.

Canonical decomposition:

```text
Agent definition / Agent NodeTemplate
├── Genome
│   ├── Model
│   ├── PromptTemplate
│   └── ParameterSet / model constraints
├── Capability/Binding exposure
├── Permission/Policy
├── Memory configuration
└── provenance/review metadata
```

### `AgentCard`

Portable catalog/interoperability projection. Keep as representation of an Agent definition/NodeTemplate, not authoritative execution state.

### `Agent`

Agent behavior over definition/genome and authorized bindings. It is not a separate top-level runtime.

### `AgentSpec`

Currently mixes reusable definition fields with task/subtask/attempt/execution context. Split reusable definition from NodeRun/Attempt context.

### Recipes, PM fleet and specialist agents

- recipes may map to NodeTemplate or GraphTemplate depending shape;
- PM fleet/named roles map naturally to Persona-owned Agent NodeTemplates/GraphTemplates;
- Artificer/Auditor/etc. remain useful specialized Agent/Node behavior;
- reasoning strategies remain Agent Node execution policy/behavior, not separate runtimes.

## 9. Capability and fulfillment ecosystem

### `capabilities`

Existing subsystem already provides capability slots, provider registry, discovery, health/fallback, harness manager, HTTP seams and provider implementations.

This is the base for canonical Capability/Provider.

Add/normalize the missing consumer-specific layer:

```text
Capability
 -> Provider
    -> Binding scoped to Persona/Node
       -> Invocation
```

Provider is not Binding.

### Tools

Current tools include approval, Atlassian, browser, git, media, network guards, PM stubs, reversibility and sandbox families.

Canonical mapping:

- concrete tool executor -> Provider/Binding implementation
- model-facing schema/name -> ToolExposure
- approval/reversibility/sandbox requirements -> Binding/Invocation policy metadata
- tool result -> Invocation/NodeRun output/artifact

### Skills

Parser/loader/catalog/registry/connectors/marketplace/importers/import pipeline/forge/fixer/canary.

Skill is a reusable product/package concept that may contain several canonical pieces:

- prompt/instructions -> PromptTemplate or NodeTemplate fragment
- parameters/schema -> Schema/ParameterSet
- advertised ability -> Capability/ToolExposure
- endpoint/connector -> Binding hints
- trust/source -> provenance/policy

Do not force Skill itself to be a primitive.

### Portability

Imports external agent/skill formats and exports compatible representations. It should translate external definitions to canonical templates/capabilities and retain provenance. Transport formats are never authoritative internal ontology.

### Harnesses

Existing HarnessRunner slot, SafeHarnessRunner, HarnessSessionManager, subprocess harnesses, microVM/container sandbox backends, inbound harness route, Graph HarnessNodeExecutor and durable harness concepts.

Canonical mapping: foreign-executor Provider/Binding with sessionful or durable Invocation semantics. Node/Run owns work identity; harness session/handle owns protocol continuity only.

### MCP / HTTP

Protocols and interoperability layers, not Run types. MCP tool exposure becomes ToolExposure/Binding. HTTP remains a transport used by providers/integrations.

### Delivery and integrations

Delivery registry/protocols and integrations such as Home Assistant, CoinSwarm, Turing, ntfy, Jira/Confluence/git/browser should become Provider/Binding families plus Event producers/handlers where appropriate.

## 10. Graph and orchestration ecosystem

### Graph

Current graph package includes definition/types, validators/registry, NodeRun, traversal, concurrency, depth/compaction, events, harness adapters, durable runs and many concrete Node kinds.

Canonical Graph owns:

- Nodes
- Edges
- topology
- conditions/predicates
- graph-domain state

Graph does not own universal execution lifecycle.

### Node

Existing Node families include:

- agent
- harness
- HITL approval/question/review/edit/delegate
- remote agent delegation
- tool/API-backed work
- polling/wait
- transforms/evaluators
- design/render/image
- potential subgraph/graph-as-node

Node is the universal executable position in a Graph. NodeType defines its protocols, parameters, bindings, permissions and behavior.

### Edge

Keep as graph composition primitive. Conditions/routing semantics remain graph-domain meaning. Learned trust/weights/staleness can remain graph optimization metadata.

### `NodeExecutor`

Useful seam proving graph position and fulfillment backend are orthogonal. Keep as a domain adapter seam unless a cleaner Binding-based name emerges after convergence.

### `orchestrator`

Planner, validation, hierarchy/master coordination and waves/fan-out/fan-in.

- planning/validation/hierarchy are domain semantics;
- generic concurrency/fan-out mechanics may delegate to ExecutionRuntime;
- do not move orchestration meaning into runtime.

## 11. Execution ecosystem

### Run

Competing lifecycle owners currently include:

- GraphRun
- DurableRunRecord
- task lifecycle
- A2ATask/AgentTask lifecycle
- Builders RunRequest/RunResult
- RSI run/cycle state
- schedule TaskExecution
- Hive DAG run state

Target: one canonical Run identity/lifecycle owned by Workspace.

Run owns logical execution history:

- workspace/persona context
- graph snapshot/reference
- parent/child relationships
- lifecycle state
- timestamps
- provenance
- output/artifact references
- event correlation

### NodeRun

Converge graph NodeRun, DurableNodeRecord, Builders worker/stage results, delegated agent execution, harness/HITL/eval execution into one NodeRun envelope with NodeType-specific detail.

### Attempt

One physical execution attempt. Retry/recovery creates attempts without necessarily creating a new logical Run.

### GraphRun

Conceptually a projection of Run plus GraphExecutionState, not a sibling primitive to Run. Graph-specific traversal/checkpoint state remains separate from the universal Run lifecycle.

### ExecutionRuntime

Mechanics only:

- bounded concurrency
- cancellation propagation
- deadlines/timeouts
- event sequencing mechanics
- slot/backpressure mechanics
- runtime health/metrics

It does not own graph meaning, Run persistence, Node types, capability semantics, permissions, tools or business policy.

## 12. Tasks, queues, schedules and recovery

### Tasks

Current task package contains models/status, queue, lanes, runner, checkpoints, replay, recovery and progress webhooks.

Decompose:

```text
WorkRequest / ingress
├── requested executable/capability
├── inputs/context
└── scheduling hints

Admission policy
├── lane
└── priority

Run
└── canonical execution lifecycle
```

Task lane reservations are real policy and must not be flattened into a generic semaphore. Task status should stop being terminal execution truth after Run migration.

### Scheduling

Schedule owns cadence/trigger/target/default inputs/policy. Firing a Schedule creates a Run.

```text
Schedule -> Run launcher -> Run
```

Historical TaskExecution-like records converge to Run references.

### Resilience/recovery

Keep circuit breakers, retry/backoff, error classification, crash-loop policy, checkpoint compatibility and provider fallback where semantically correct.

Canonical separation:

- Policy decides eligibility
- Attempt records physical retry
- Run owns logical terminal state
- Checkpoint stores resumable state
- ExecutionRuntime performs mechanics
- Provider fallback belongs capability selection

## 13. Delegation and A2A

Existing broker, delegator, A2A task lifecycle, guest peers, direct Agent delegation and `agent.delegate_remote` overlap substantially.

Canonical model:

```text
Agent NodeRun
 -> authorized Agent-backed Binding
    -> child Run / NodeRun for target Agent
       -> parent waits/resumes
```

Keep peer trust/routing/transport. Replace duplicate delegated-task lifecycle with child Runs after behavior parity.

## 14. Human-in-the-loop

Existing human approval/question/review/edit/delegate nodes and durable pause/resume are already useful.

Canonical mapping:

- Node(type=human/HITL)
- human interaction Protocol/Binding
- request/response schemas
- timeout/escalation Policy
- permissions
- pause/resume/checkpoint in Run/NodeRun

HITL is not a separate runtime.

## 15. Auth, identity, permissions, policy and security

### Authentication and identity

`maistro.auth` handles service-key/OAuth/principal/scope concerns. `maistro.identity` handles agent identity lifecycle/capability tokens. `maistro.security` handles threat/policy runtime controls.

Do not merge them blindly. Standardize the handoff:

```text
Authentication
 -> Principal / Identity
    -> PermissionContext
       -> hierarchical permission evaluation
          -> Policy/Security decision
```

### Security

Warden, Sentinel, Gate, dangerous-tool classification, delegability, external-content defenses, DAG-shape controls, approvals, strikes/elevation, sandbox/network/filesystem restrictions all survive as real security mechanisms.

The convergence requirement is reachability: every relevant Binding/Invocation must actually pass through the configured security path.

### Policy

Sequence policy/rules remain context-sensitive decision machinery under the Permission ceiling. Policy can require approval/limit budgets/order/velocity, but cannot grant authority forbidden above it.

### Credentials

Credential providers/pools/stores/rotation remain resource/security infrastructure.

- Workspace owns/binds logical credential references.
- Persona/Graph/Node/Binding permissions constrain use.
- Binding declares credential requirements.
- material resolves at Invocation time only.

## 16. Memory, repertoire, code knowledge and learning

### Memory

Current memory includes context assembly, episodic stores, exposure modes, learnings, mutations, outcomes, scopes and persistence.

Target scopes include:

- Run-local working context
- Workspace knowledge
- Persona context
- Agent-specific memory
- Session continuity
- reusable learned patterns

Existing org/team/global scopes may remain useful enterprise-ready infrastructure and should not be deleted for aesthetic symmetry.

### Repertoire

Reuse-first recall/rehearse/compose strategy. Its `run.py` is a vocabulary collision, not another Run lifecycle. Keep the algorithm in memory/learning/planning space; rename only if canonical Run causes confusion.

### Codebase

Python parser/index/violations knowledge resource. Workspace/Builders Personas can expose it to Nodes through context/Bindings.

### Code registry

Trusted code registry/verification/provenance resource. Attach to executable definitions, capabilities and artifacts; feed security/trust checks.

### Learning/promotion

Learning/evolution should create/promote new template versions rather than silently mutate active Workspace Nodes/Graphs. This aligns memory, Evolve and template provenance.

## 17. Sessions and collaboration

Session is continuity/conversation scope and can span Runs. It is not Run.

Collaboration provides session co-ownership, viewer/editor/owner roles, presence, membership changes, message feed/history and live events.

Canonical direction:

- keep Session and Presence distinct;
- integrate identities/roles under Workspace permission ceiling;
- correlate collaboration/session events with canonical Event infrastructure where useful;
- do not replace Run lifecycle with Session lifecycle.

## 18. Events

Existing events subsystem already provides EventBus, durable log, triggers, handler invocation records, processing and recipes.

Other event models exist in graph callbacks, Builders StageEvent, collaboration, task progress/webhooks, Hive streams, audit and observability.

Use existing core events as the canonical base rather than inventing another event package.

Target envelope:

```text
DomainEvent
├── workspace_id
├── persona_id?
├── run_id?
├── node_run_id?
├── attempt_id?
├── invocation_id?
├── session_id?
├── actor
├── type
├── sequence
├── timestamp
└── payload
```

Specialized events can remain typed projections if they correlate to canonical ownership IDs.

## 19. Artifacts/files

Current artifacts include Builders ArtifactRef, graph/node outputs, git branches/commits/files, Canvas/Design output, generated images/documents, sandbox files, eval results and replay records/logs.

Canonical Artifact is first-class and owned by Workspace and/or Run. NodeRuns produce artifact references. Domain packages can add richer metadata/types without inventing a separate run-result ontology.

## 20. Observability/replay

Logging, metrics, tracing, middleware, replay, recording clients, sensitivity/PII tiers and external telemetry adapters remain projections of canonical activity.

Observe/correlate on:

```text
workspace_id
persona_id
run_id
node_run_id
attempt_id
invocation_id
session_id
```

Replay is diagnostics/provenance, not a second Run lifecycle.

## 21. Quota/accounting

Quota/billing/rate profiles/reconciliation/usage records/verifiers remain accounting and entitlement services.

- accounting records actual usage;
- Permission may deny based on entitlement;
- Policy may enforce run/session budgets;
- Run/NodeRun/Invocation IDs provide chargeback correlation.

## 22. Persistence

Current Postgres/SQLite stores mirror many domain subsystems directly.

Keep persistence as adapters. Over time repositories should persist canonical domain objects/projections rather than defining parallel lifecycle truth.

Migration rule: preserve old storage/API shapes behind compatibility adapters until parity tests and migrations prove safe.

## 23. Builders ecosystem

Current Builders concepts include Frank/Mason/Auditor, stages, BuildersRuntime handler dispatcher, prompt registry, allowed-tool registry, RunRequest/RunResult, ArtifactRef, StageEvent, pipeline/orchestrator/graph, CLI/TUI and Builders RSI.

Canonical target:

```text
Persona: Builders
├── surfaces
│   ├── UI
│   ├── Builders CLI
│   └── Builders RSI (when allowed)
├── Agent NodeTemplates
│   ├── Frank
│   ├── Mason
│   └── Auditor
├── GraphTemplates: builder workflows
└── capability/binding/policy defaults

Workspace
└── instantiated Builder Graph
    └── Nodes

Run
└── NodeRuns
```

BuildersRuntime becomes a specialized node/handler adapter, not a universal runtime. Builders RunRequest/RunResult and StageEvent become projections/adapters over canonical Run/NodeRun/Event.

## 24. PM Fleet ecosystem

Current PM Fleet and role definitions are another Persona/use-case already riding on core.

Canonical direction:

- PM Fleet -> Persona
- named PM roles -> Agent NodeTemplates
- PM DAGs -> GraphTemplates
- Project `use_case` switch -> Persona reference
- current tools/resource bindings -> Persona/Workspace Binding defaults

## 25. Canvas/Design ecosystem in Persona terms

Potential Personas:

- Book Builder
- Design/Presentation
- specialized brand/design Personas

Each Persona can expose its own UI scope, NodeTemplates, GraphTemplates, design systems, image/render providers and export permissions while using the same Workspace/Graph/Run ownership model.

Canvas/Design domain objects that are truly editable artifacts/projects can remain domain assets under Workspace rather than being forced into Graph.

## 26. Turing ecosystem in Persona terms

Turing can enrich Persona/Agent rather than create a second root hierarchy:

```text
Persona
├── purpose/theme
├── voice/personality defaults
├── proactive producers/triggers
├── memory policy
├── Agent NodeTemplates
├── GraphTemplates
└── allowed Bindings/surfaces
```

Agent-specific self-model/cognitive details can remain inside Agent definition/Genome extensions where they do not belong at Persona scope.

## 27. RSI/Evolve ecosystem in Persona terms

- RSI UI/CLI/autorun -> Persona surface/trigger
- hypothesis/planning -> RSI domain data / Graph planning
- evolve cycle -> Graph/Run
- benchmarks/evals -> Eval Nodes/Bindings
- sandboxes/git -> Bindings
- population/tournament -> evolution state
- promotion/rollback -> template/version governance

A private background loop or private RunState should disappear once Schedule/Event -> Run gives equivalent behavior.

## 28. Developer/governance ecosystem

Intentionally outside product runtime ontology:

- maistro-bootstrap
- maistro-registry
- ADR/SPEC lifecycle tooling
- lifecycle linters
- architecture fitness checks
- CI workflows
- formal conformance and generated models
- mutation testing
- security scans
- release/promotion topology
- repo mining/backfill
- benchmark provenance
- `.claude` repo skills/settings
- `.cursor` agents/rules/skills
- AGENTS/CLAUDE/CONTRIBUTING guidance

These constrain, validate or build the ecosystem. They become Persona-accessible tools only when intentionally invoked as product capabilities.

## 29. Existing engineering quality plane

Current CI/control workflows include:

- CI
- quality
- security
- mutation
- formal conformance
- formal nightly
- registry validation
- release installer
- cage guard
- RSI harvest

Current quality baselines include:

- reachability
- vulture/dead-code classifications
- radon complexity
- mutation
- enumeration coverage

The reachability baseline is directly useful to this convergence effort. Each wanted subsystem that becomes callable from a real product entry point should reduce unreachable debt rather than add a permanent allowlist exception.

## 30. Interfaces/surfaces

Current/possible surfaces:

- Hive web UI/backend API
- maistro-server generic API
- chat-completions compatible API
- WebSocket/SSE
- Builders CLI/TUI
- Builders RSI
- maistro-rsi CLI
- harness session API
- MCP
- Canvas/book-maker frontend
- Design consumers
- imported/external agents/tools

Canonical rule: surfaces expose Persona-authorized operations over the same domain objects. A surface should not require its own Workspace/Graph/Run model.

## 31. Primary duplicate/overlap families

### Execution lifecycle

- TaskStatus
- GraphRun/GraphPhase
- DurableRunRecord status
- A2ATask/AgentTask status
- Builders RunStatus
- schedule TaskExecution
- RSI cycle/run state
- Hive DAG run status

Target: Run/NodeRun/Attempt.

### Definition/template

- AgentIdentity
- AgentCard
- reusable portions of AgentSpec
- recipes
- Persona spawns
- GraphConfig/DAG files
- PM roles
- Builders worker/stage definitions
- skills
- imported external definitions
- Design skills/systems

Target: Persona-owned NodeTemplate/GraphTemplate plus explicit domain assets.

### Fulfillment

- tool executor
- capability provider
- harness runner
- HTTP API client
- MCP tool
- sandbox executor
- renderer/image provider
- delegated agent
- human interaction

Target: Capability/Provider/Binding/Invocation with protocol-specific adapters.

### Correlation/events

- task IDs
- graph run IDs
- durable run IDs
- builder run IDs
- A2A task IDs
- trace IDs
- session IDs
- event/audit sequence IDs

Target: canonical ownership IDs and explicit relationships. Do not collapse Session or event/audit sequence concepts where they are legitimately independent.

### Permission/trust

- auth scopes
- Project member roles
- collaboration roles
- trust tiers
- tool allowlists
- delegation modes
- peer trust
- approval gates
- design trust
- Evolve promotion approvals

Target: hierarchical Permission ceiling plus composable Policy/trust/security mechanisms.

### Product identity

- Project `use_case`/profile/UI selection
- Persona `kind=workspace` brand/UI/voice/spawns
- app-specific page/surface gates

Target: Workspace owns durable user objects/resources; Persona owns purpose/brand/behavior/surfaces/templates.

### Product-shell stores/services

Hive and maistro-server contain app/service stores and lifecycle wrappers that overlap core. Keep transport/UI-specific adapters, converge duplicate domain ownership into core canonical services.

## 32. Things that must remain distinct

- User vs Workspace
- Workspace vs filesystem workdir
- Workspace vs Persona
- Persona vs Agent
- Template vs mutable object
- Graph vs Run
- Node vs NodeRun
- Run vs Attempt
- Session vs Run
- Schedule vs Run
- Capability vs Provider
- Provider vs Binding
- Binding vs Invocation
- Permission vs Policy
- Credential vs Binding
- Event vs Artifact
- graph traversal semantics vs ExecutionRuntime mechanics
- evolution domain state vs execution state
- product/domain packages vs generic platform primitives
- engineering governance/control plane vs runtime domain

## 33. Canonical end-state ecosystem

```text
USER / OWNERSHIP
User
└── Workspace
    └── Persona

REUSABLE LIBRARY
Persona
├── NodeTemplate
├── GraphTemplate
├── PromptTemplate refs
├── domain assets/defaults
└── authorized capability/binding defaults

EDITABLE WORKSPACE OBJECTS
Workspace
├── Graph
│   ├── Node
│   └── Edge
├── Sessions
├── Artifacts/domain objects
└── resource/integration bindings

EXECUTION HISTORY
Workspace
└── Run
    ├── NodeRun
    │   └── Attempt
    ├── Event
    ├── ArtifactRef
    ├── Checkpoint
    └── child Run

FULFILLMENT
Node
└── Capability
    └── Provider selection
        └── Binding
            └── Invocation

CONTROL
User -> Workspace -> Persona -> Graph -> Node -> Binding -> Invocation
Policy evaluates state/context inside that ceiling
Credentials resolve only for permitted Bindings/Invocations

MECHANICS
ExecutionRuntime
  concurrency / cancellation / deadlines / sequencing mechanics / metrics

CONTINUITY
Session
  conversation/collaboration continuity spanning Runs

TRIGGERS
Schedule / Event Trigger
  creates or resumes Runs

SPECIALIZED PACKAGES
Builders / Canvas / Design / Turing / PM Fleet / RSI / Evolve
  provide Personas, NodeTypes, templates, bindings, policies and domain assets
  without parallel universal lifecycle models

SURFACES
Web UI / API / CLI / RSI / MCP / harness
  Persona-authorized views/controllers over the same objects

GOVERNANCE
Bootstrap / Registry / ADR/SPEC / CI/formal/security tooling
  validates/configures the ecosystem but remains outside runtime ontology
```

## 34. Decisions resolved by the UX model

These are no longer open questions for this workstream unless implementation evidence forces reconsideration.

1. **Workspace has one Persona.**
2. **Persona owns NodeTemplates and GraphTemplates.**
3. **Templates instantiate independent mutable Workspace objects with provenance.**
4. **Single-node Graphs are valid and are the simplifier for single Agent/Harness/HITL/Eval/API work.**
5. **Run is the universal logical execution history.**
6. **NodeRun is the universal per-Node execution record.**
7. **Attempt is physical execution/retry identity.**
8. **ExecutionRuntime owns mechanics, never domain meaning.**
9. **Permissions narrow downward through User -> Workspace -> Persona -> Graph -> Node -> Binding -> Invocation.**
10. **Builders CLI and Builders RSI are Persona-exposed surfaces, not parallel domain models.**

## 35. Remaining architecture questions

1. Exact persisted schema/API migration from Project/project_id to Workspace/workspace_id while preserving compatibility.
2. Exact shape/version/provenance schema for NodeTemplate and GraphTemplate.
3. Exact persisted Run/NodeRun/Attempt schema and terminalization rules.
4. Exact NodeType registry/extension mechanism.
5. Binding persistence and whether Provider resolution is pinned when a Node is saved, when a Run starts, or per Attempt.
6. Hierarchical Permission representation/evaluation algorithm and relationship to legacy org/team scopes.
7. Which specialized events become canonical types versus projections over the canonical event envelope.
8. How Turing self-model/personality fields split between Persona and Agent Genome.
9. How Canvas/Design editable domain objects map to Workspace artifacts/domain assets versus Graph/Node definitions.
10. Which Builders stage concepts deserve Nodes versus internal steps within one Node implementation.
11. How Evolve/learning promotion writes new template versions and how rollback selects prior versions without mutating active objects.
12. Behavioral parity plan for legacy GraphRun versus durable graph traversal before consolidation.

## 36. Convergence workstreams

1. **Workspace/Persona boundary**
   - preserve Project compatibility;
   - make Project/Workspace reference existing Persona;
   - move duplicate use-case/UI-purpose semantics toward Persona;
   - establish template ownership/provenance.

2. **Canonical Run/NodeRun/Attempt**
   - terminalization;
   - parent/child;
   - retry/attempt;
   - cancellation/timeout;
   - pause/resume/checkpoint;
   - persistence/event IDs.

3. **Graph/runtime seam**
   - preserve graph meaning;
   - move generic mechanics behind ExecutionRuntime;
   - parity test legacy/durable traversal before deleting anything.

4. **Capability/Binding/Invocation**
   - extend existing capability/provider registry rather than replacing it;
   - normalize tools, harnesses, integrations, delivery, MCP/HTTP, agent delegation and human fulfillment.

5. **Hierarchical permissions/security**
   - standard Principal/PermissionContext;
   - monotonic narrowing;
   - credential resolution at Invocation;
   - Warden/Sentinel/Gate/approval/reversibility/sandbox on actual call paths.

6. **Canonical events/correlation**
   - use existing events subsystem as base;
   - unify IDs/envelope;
   - UI, audit, memory, recovery, notifications and observability consume it.

7. **Task/schedule/recovery**
   - Task -> WorkRequest/admission;
   - Schedule -> Run launcher;
   - Recovery -> persisted Run/Attempt/checkpoint.

8. **Builders Persona convergence**
   - Builders UI/CLI/RSI surfaces;
   - Frank/Mason/Auditor templates;
   - Builders runtime contracts become adapters.

9. **Domain application convergence**
   - PM Fleet, Canvas, Design, Turing, RSI/Evolve use shared ownership/execution/events/security while preserving domain semantics.

10. **Interface thinning**
    - Hive/maistro-server become adapters over canonical services rather than duplicate state owners.

11. **Reachability burn-down**
    - use existing reachability baseline as debt ledger;
    - wanted features get real product entry points;
    - unwanted islands are removed or documented honestly.

12. **Governance lock**
    - ADR/spec once evidence is sufficient;
    - acceptance criteria map directly to contract/integration tests;
    - update repo-agent rules and formal invariants to canonical vocabulary.

## 37. Exit condition

The ecosystem is stitched when any allowed Persona surface reaches the same underlying objects and histories:

```text
User
 -> Workspace
 -> Persona
 -> Graph / Node
 -> Run / NodeRun / Attempt
 -> Binding / Invocation
```

with one ownership model, one permission hierarchy, one execution identity model, one event/correlation model, shared memory/artifacts/credentials, and specialized packages that contribute domain semantics without creating parallel universal runtimes.

For every implementation change, require explicit answers to:

1. Which canonical object does this existing thing map to?
2. Is it a domain object, template, runtime record, Provider/Binding, resource, surface, or governance tool?
3. Who owns its lifecycle?
4. What permission scope applies?
5. Does another subsystem already own the same lifecycle/semantic responsibility?
6. What compatibility adapter allows migration without behavior loss?
7. What duplicate can be removed only after parity tests prove convergence?
