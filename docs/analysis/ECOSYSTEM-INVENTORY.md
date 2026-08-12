# MAIstro Ecosystem Inventory

Status: working inventory for architecture convergence. This is descriptive, not yet normative.

Purpose: identify everything that exists in the MAIstro ecosystem, place it in the canonical product/domain hierarchy where possible, and explicitly separate product objects, execution infrastructure, specialized product packages, interfaces, and developer/governance tooling. This prevents the convergence effort from either missing subsystems or flattening legitimate boundaries.

## 1. Canonical product/domain hierarchy

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
    └── Run[]
        ├── graph/node snapshot or reference
        ├── NodeRun[]
        ├── Attempt[]
        ├── Events
        ├── Artifacts
        └── Outputs
```

Underlying primitives:

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
Artifact
Event
```

Execution relationship:

```text
Run
└── NodeRun[]
    └── Attempt[]
         ↓
ExecutionRuntime
         ↓
Binding / Provider / executor implementation
```

## 2. Repository package ecosystem

### maistro-core

Role: shared platform/domain library and the largest source of architectural primitives.

Current families include:

- agents
- agent catalog/cards/identity
- A2A/delegation
- auth and identity
- builders
- capabilities/providers/slots
- classifier/routing
- CLI
- code registry and codebase indexing
- collaboration/session co-ownership
- config/model resolution
- credentials
- delivery
- events and triggers
- feedback/outcomes/learnings
- graph/DAG/nodes/durable runs
- HTTP/provider adapters
- integrations
- memory
- observability/replay/tracing
- persistence
- policy
- portability/import-export
- prompts
- quota/billing
- resilience/recovery/circuit breakers
- scheduling
- security/Warden/Sentinel
- sessions
- skills/marketplace/import/forge/fixer/canary
- task queue/runner/lanes/checkpoints
- tools/browser/git/sandbox/approval/etc.
- types/contracts shared across these systems

Canonical role: authoritative home for reusable MAIstro domain concepts and generic platform mechanisms. It should not become the home of app-specific UX semantics that belong to a Persona or specialized product package.

### hive-conductor

Role: household/personal application backend, not a generic runtime package.

Current surfaces include product routes and app-level services for:

- chat/sessions
- agents
- memory
- DAG/graph execution
- projects/workspaces
- schedules
- CLI exposure
- MCP servers/tools
- harness sessions
- RSI service
- evolution service
- integrations
- audit/security/admin surfaces
- persistence stores

Canonical role: one product/app consuming the MAIstro domain model. Its custom lifecycle and graph execution paths should converge onto core contracts, while app-specific routes/UI behavior remain here.

### maistro-server

Role: generic FastAPI server for MAIstro.

Current responsibilities include task APIs, websocket task progress, chat-completions compatibility, health/readiness, lifecycle wiring, PM-fleet seeding and core container wiring.

Canonical role: generic transport/interface adapter over canonical Workspace/Persona/Graph/Run objects. It should not own a second domain model.

### maistro-canvas

Role: reusable canvas engine plus a separate book-maker frontend/application.

Library capabilities include:

- canvas tool/executor
- compositor/RGBA assembly
- canvas store
- routes
- image-generation client protocol
- compositor protocol
- export paths

The package guidance explicitly distinguishes the reusable canvas ability from the book-maker frontend consumer.

Canonical mapping:

- canvas execution/composition primitives -> specialized NodeTypes/Bindings
- book-maker -> Persona/product surface
- canvas documents/projects -> specialized workspace objects/artifacts, not a separate universal execution hierarchy

### maistro-design

Role: composable design skills, design systems and canvas composition.

Current first-class concepts include:

- DesignEngine
- DesignProject
- DesignSkill
- DesignSystem
- design skill/system registries
- renderer registry/discovery
- render slots/providers
- HTML/SVG/typography renderers
- discovery results
- artifact nodes/kinds
- trust tiers/review queue/banish list
- design-system import/catalog/bundles
- scanners
- persisted design project store

Canonical mapping:

- DesignSkill -> likely NodeTemplate/Capability package-specific specialization
- DesignSystem -> reusable domain asset/template, potentially Persona-scoped
- DesignProject -> specialized editable workspace object or graph-owned artifact set
- Renderer/RenderProvider -> Provider/Binding
- RenderSlot -> Capability slot
- DesignEngine -> domain adapter/orchestrator, not universal ExecutionRuntime
- trust/review -> package-specific policy layered under canonical permissions/policy

### maistro-evolve

Role: evolutionary evaluation/optimization package.

Current concepts include:

- genome/population
- mutation/crossover
- evolution cycle
- tournament/Elo
- fitness
- reflection/self-improvement
- evaluation harness
- benchmark adapters and official/heuristic graders
- promotion/rollback/audit trail

Canonical mapping:

- Genome -> primitive/composite reusable definition, especially for Agent NodeTemplates
- population/tournament -> optimization state, not Run lifecycle
- EvolutionCycle -> executable graph/node workload producing Runs
- benchmark adapters/eval harness -> Eval NodeTypes/Bindings
- promotion -> template/object governance operation
- rollback -> template/genome selection operation

### maistro-rsi

Role: recursive self-improvement over the MAIstro codebase.

It composes:

- isolated sandbox/microVM protocol
- self-branch/git workflow
- benchmark/tournament stack from evolve
- hypothesis tree/coordinator
- quota-burn/model scheduling
- autorun/CLI
- self-modification PR workflow

Canonical mapping:

- RSI product behavior -> Persona capability/surface
- an RSI cycle -> Graph/Run
- hypothesis nodes -> RSI domain objects or graph planning data, not universal Node by default
- sandbox -> Binding/Provider
- self-branch operations -> Nodes/Bindings
- benchmark/eval -> Eval NodeTypes
- autorun/quota burn -> scheduling policy creating Runs

### maistro-turing

Role: autonoetic/self-model extension for agents.

Current concepts include:

- self model
- mood/personality/drives
- proactive producers
- actor/chat runtime
- cognition stages
- Turing-specific memory extensions
- providers
- tool/schema surfaces
- adapters into core memory/security

Canonical mapping:

- self model/personality/drives -> Persona and/or Agent Genome extensions depending scope
- proactive producer -> schedule/event trigger or NodeTemplate
- actor/chat runtime -> product/domain adapter that should create Runs rather than own an independent execution ontology
- memory extensions -> memory scoped under Persona/Agent/Session
- providers/tools -> canonical Provider/Binding/Capability

### maistro-bootstrap

Role: installer/bootstrap tooling for feature slices and templates.

Canonical role: developer/deployment tooling. Do not force into Workspace/Graph/Run. It may create templates/configuration but is outside the runtime domain hierarchy.

### maistro-registry

Role: ADR/spec registry CLI for walk/validate/lint/link checking.

Canonical role: governance/developer tooling. Not runtime/domain architecture.

## 3. Product objects and current implementations

### User

Existing pieces:

- auth providers and principals
- user_id fields across tasks, runs, memory and collaboration
- user-scoped agent catalog entries
- user schedules
- collaboration members

Convergence:

- KEEP identity/auth mechanisms.
- Establish one canonical UserRef/subject identifier contract used everywhere.
- User owns one or more Workspaces at product level.

### Workspace

Existing pieces:

- `project_id` on durable runs
- project/workspace concepts in Hive
- task `workspace` currently often means a filesystem path
- builder `workspace_ref`
- graph blackboard `workspace`
- sandbox workspace path

Conflict: "workspace" currently means both product ownership container and filesystem work directory.

Convergence:

- canonical Workspace = product/domain ownership boundary
- introduce `workspace_id` for product identity
- use `workdir`, `workspace_path`, or sandbox-specific names for filesystem roots
- preserve existing Project storage through compatibility adapters/migrations

### Persona

Existing pieces that partially approximate it:

- AgentIdentity/AgentCard defaults
- PM fleet definitions
- recipes
- builder worker/stage configuration
- Turing personality/self-model config
- design systems/skills in domain-specific packages
- feature/surface gating in apps

Convergence:

- INTRODUCE as first-class object.
- Persona owns purpose/theme/defaults and controls available surfaces, templates, defaults, policy and permissions.
- Persona does not execute work itself.

### NodeTemplate

Existing candidates:

- AgentIdentity / AgentCard
- agent.yaml definitions
- recipes/phases
- graph node specs/configs
- SkillDefinition-like assets
- Builders worker/stage definitions
- design skills
- PM role definitions
- imported portable agent definitions

Convergence:

- introduce canonical template provenance/version semantics
- template instantiation produces independent mutable Node objects
- templates are reusable assets, not live parents

### GraphTemplate

Existing candidates:

- GraphConfig/DAG files
- recipes/workflows
- PM DAG definitions
- Builders graph/pipeline definitions
- domain-specific graph definitions

Convergence:

- reusable immutable-ish graph definition
- instantiate into editable Graph
- object retains source_template_id/version only as provenance
- save customized Graph as a new GraphTemplate

### Graph

Existing pieces:

- `GraphConfig`
- Hive DAG definitions
- GraphBuilder/DAG builder paths
- graph edge types
- PM-as-DAG
- Builders dependency graph

Important existing behavior: graph types already accept arbitrary node kinds in addition to AgentRole values.

Convergence:

- Graph = editable composition of Nodes + Edges
- a single-node Graph is valid
- Graph does not own a separate execution ontology
- a Run snapshots/references Graph state

### Node

Existing node/executable families:

- agent node
- arbitrary graph node kind
- harness node
- HITL approval/question/review/delegation nodes
- remote agent delegation node
- tool/API-backed work
- Jira polling/wait nodes
- transforms/evaluators
- design/render nodes
- potential graph-as-node/subgraph composition

Convergence:

- Node is universal executable position in a Graph
- NodeType defines protocols/configuration/bindings/permissions
- Node itself remains editable workspace state
- Node may originate from NodeTemplate

### Edge

Existing pieces:

- GraphEdge from/to role/node aliases
- conditions
- parallel flag
- learned weight/trust/sign/staleness data

Convergence:

- KEEP as graph composition primitive
- separate routing predicate/condition semantics from runtime mechanics
- learned optimizer metadata can remain graph-domain state

## 4. Agent ecosystem

### AgentIdentity

Currently contains model, prompt reference, fallbacks, constraints, tools, skills, rules, trust, priority, delegation, sub-agents, strategy, memory config, phases and review/provenance metadata.

Canonical decomposition:

```text
Agent NodeTemplate / Agent definition
├── Genome
│   ├── Model
│   ├── PromptTemplate
│   └── ParameterSet / model constraints
├── Capability/Binding exposure
├── Permission/Policy
├── Memory configuration
└── provenance/review metadata
```

### AgentCard

Portable projection of agent identity, including tools/skills, trust, model, delegation and scope.

Canonical role: import/export/catalog representation of an Agent NodeTemplate, not the sole authoritative in-memory definition.

### Agent

Source explicitly states: "An agent is data, not a process. The runtime is shared."

Canonical role: Agent NodeType behavior over an Agent definition/genome and authorized bindings.

### AgentSpec

Current code uses it for spawn/execution context in several paths.

Convergence: split reusable agent definition from per-run NodeRun/Attempt context. Do not let task IDs/attempt data leak into templates.

### Reasoning strategies

Existing examples include direct, ReAct, plan/execute, builders learning, HTTP tool strategy, Artificer-style multi-phase logic.

Canonical role: Agent Node behavior/strategy parameter. Not separate runtimes.

### PM fleet / named roles

Current PM roles and engineering roles are encoded in AgentRole and PM-fleet definitions.

Canonical mapping: Persona-provided Agent NodeTemplates and GraphTemplates. Named role labels are product vocabulary, not primitive execution classes.

## 5. Capability and fulfillment ecosystem

### Capability

Existing capability registry defines named slots and provider selection/fallback/health.

Canonical meaning: a declared ability/contract that can be fulfilled.

### Provider

Existing `CapabilityProvider` implementations are installed/selected/health-checked implementations of slots.

Canonical meaning: implementation candidate for a capability. Provider is not authorization and not Invocation.

### Binding

Currently implicit across many systems:

- selected capability provider
- tool executor registration
- HTTP client endpoint/config
- MCP server/tool
- harness session manager
- agent delegation target
- sandbox backend
- credential-backed integration
- renderer provider
- model endpoint/provider

Canonical meaning: consumer-specific configured/authorized route from a Node to fulfillment.

### Tool / ToolExposure

Current agents expose tool names/schemas separately from actual executors.

Canonical mapping:

- ToolExposure = model-visible description/schema of an authorized Binding
- Tool invocation = Invocation over that Binding
- avoid making every tool transport its own architecture

### Protocols

Existing protocol families include:

- Python/function
- HTTP
- MCP
- harness/session
- sandbox/process
- human interaction
- agent delegation/A2A
- renderer
- image generation
- credential provider
- stores/persistence

Canonical role: reusable primitive contract. Protocol alone does not confer permission.

### Harnesses

Existing:

- HarnessRunner slot
- SafeHarnessRunner
- HarnessSessionManager
- subprocess harness providers
- microVM/container sandbox backends
- inbound harness HTTP route
- HarnessNodeExecutor

Canonical mapping: Harness NodeType + Binding + sessionful Invocation. Keep session protocol/safety wrapper; remove duplicate execution lifecycle where Run/NodeRun can own it.

### MCP

Existing:

- server/tool routes
- MCP import/export portability
- skills exposed as MCP tools
- fastmcp-backed tools

Canonical mapping: transport/protocol plus ToolExposure/Binding. MCP itself is not a Run type.

### HTTP integrations

Existing integrations use HTTP transports for providers/services.

Canonical mapping: Binding protocol. Domain integrations may retain convenience clients.

## 6. Execution ecosystem

### Run

Current competing lifecycle objects include:

- GraphRun
- DurableRunRecord
- task API lifecycle
- A2ATask / AgentTask lifecycle
- Builders RunRequest/RunResult
- RSI local RunState/cycle state
- schedule TaskExecution
- app-specific DAG run records

Canonical action: CONVERGE to one Run lifecycle and identity.

Run owns:

- workspace_id
- persona_id context
- graph/node snapshot reference
- parent_run_id
- lifecycle status
- timestamps
- provenance
- output/artifact references
- event correlation

### NodeRun

Existing:

- graph `NodeRun`
- `DurableNodeRecord`
- Builders worker/stage result
- delegated agent execution
- harness node execution

Canonical action: converge to a generic NodeRun with type-specific state/details.

### Attempt

Existing retry/attempt concepts are scattered through:

- NodeRun retries
- durable `attempts`
- retry/backoff
- recovery
- RSI cycles
- provider retries

Canonical action: introduce explicit Attempt identity for one physical execution of a Run/NodeRun. Domain retry policy can create attempts without creating new logical Runs.

### GraphRun

Canonical interpretation: not a sibling primitive to Run. It is a Run whose executable definition is a Graph, with graph-specific execution state represented by graph snapshot/checkpoint and NodeRuns.

Do not require a separate top-level GraphRun class in the final ontology unless useful as a projection/view.

### ExecutionRuntime

Canonical responsibility is mechanics only:

- bounded concurrency
- cancellation propagation
- timeout/deadline enforcement
- event sequencing mechanics
- slot acquisition/backpressure
- runtime metrics/health

It does not own graph meaning, Run persistence, permissions, tools or policy semantics.

## 7. Task/queue/admission ecosystem

Existing `TaskCreate` combines:

- work request
- filesystem workspace path
- branch/constraints
- lane and priority
- task type
- agent/capability target
- program/session/user context

Existing TaskStatus mixes generic execution lifecycle with domain phases such as planning/coding/reviewing/testing.

Canonical decomposition:

```text
WorkRequest / ingress
├── requested executable/capability
├── inputs/context
└── scheduling hints

Admission/Scheduling policy
├── lane
└── priority

Run
└── canonical execution lifecycle
```

TaskRunner remains ingress/admission until migrated, but should stop owning a competing terminal execution truth.

## 8. Scheduling and automation ecosystem

Existing core scheduling stores `ScheduledTask` and `TaskExecution`. Hive also has scheduler/service behavior.

Canonical model:

```text
Schedule
├── trigger/cadence
├── target Graph/Node/Persona surface
├── input/defaults
└── policy
       ↓ fires
Run
```

Schedule owns recurrence metadata, not execution status. Historical TaskExecution records should converge to Run references.

## 9. Delegation and A2A ecosystem

Existing mechanisms:

- AgentTask
- A2ATask/A2ADelegator
- A2A broker/lifecycle manager/worker pool
- direct Agent delegation
- agent.delegate_remote graph node
- guest peers/cross-instance transport

Canonical model:

```text
Agent Node
  has authorized Binding to another Agent/Graph capability
        ↓ invocation/delegation
child Run
        ↓
parent waits/resumes through existing durable wait primitive
```

Keep trust/peer-routing/transport. Remove independent delegated-task lifecycle after child Runs provide equivalent behavior.

## 10. Human-in-the-loop ecosystem

Existing nodes include approvals, questions, review/edit, delegation to role, and pause/resume support.

Canonical mapping:

- Human NodeType
- human interaction Protocol/Binding
- schemas for request/response
- timeout/escalation Policy
- permissions
- durable pause/resume state in Run/NodeRun

Do not make HITL a separate runtime.

## 11. Session and collaboration ecosystem

Existing Session concepts are conversation/continuity scope, distinct from Run.

Collaboration adds:

- viewer/editor/owner roles
- view/edit/manage actions
- members
- presence
- live event stream
- last-owner invariant

Canonical mapping:

- Session = continuity/conversation container that can span Runs
- collaboration = permission/membership overlay on a Session or Workspace surface
- session roles are not the full hierarchical permission system, but should integrate with it

## 12. Permission, policy, trust and security ecosystem

### Hierarchical Permission

Target constraint chain:

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

A child can narrow but never widen parent authorization.

### Existing permission/trust systems

- auth scopes/service keys/JWT/cookies
- Agent trust tiers
- capability provider trust tiers
- collaboration roles
- A2A delegation modes/peer trust
- tool allowlists
- approval gates
- Warden ingress scanning
- Sentinel/audit/security controls
- design trust tiers/review/banish list
- evolve promotion approval gate
- sandbox/network/filesystem restrictions

Convergence rule: keep domain-specific security mechanisms, but make the canonical permission evaluator the common authorization envelope.

### Policy

Existing sequence policy models Action, Decision, PolicyVerdict and SequenceState for cumulative/ordered behavior.

Canonical role: Policy evaluates allowed behavior inside the permission ceiling. Permission answers "may this actor/object ever do this?" Policy answers "under current state/context, may it happen now?"

## 13. Credentials and secrets ecosystem

Existing:

- CredentialProvider protocol
- credential records/pools/stores/rotation
- secret/vault integrations
- provider-specific key acquisition/release

Canonical mapping:

- Credential = primitive secret reference/material
- Workspace/Persona/Node/Binding permissions determine availability
- Binding references required credentials by logical name/ref
- runtime receives only resolved credentials necessary for an Invocation

## 14. Memory and learning ecosystem

Existing scopes include global, organization, team, user and agent, with retrieval filters protecting cross-org leakage.

Additional families include episodic memory, outcomes, learnings, extraction/promotion, mutation, feedback and context building.

Canonical mapping:

- memory is scoped data, not execution owner
- introduce Workspace/Persona/Graph/Node/Run scopes where product semantics require them
- preserve User/Agent/Session scopes
- learning/promotion may produce new NodeTemplates/GraphTemplates rather than mutating active definitions silently

Potential tension: legacy org/team scope remains useful infrastructure even if the current MAIstro product hierarchy is User/Workspace/Persona. Do not delete it merely for symmetry.

## 15. Event ecosystem

Existing events subsystem includes:

- EventBus
- Event/EventCategory
- Trigger/TriggerCondition
- durable EventLog
- TriggerStore
- HandlerInvocation lifecycle
- HTTP handler caller
- idempotent processing loop

Other event models exist in graph callbacks, collaboration events, builders StageEvent, audit logs and app-specific streams.

Canonical target:

```text
Domain Event
├── workspace_id
├── run_id?
├── node_run_id?
├── invocation_id?
├── actor
├── type
├── sequence
├── timestamp
└── payload
```

Existing specialized events can remain projections, but should correlate to canonical IDs and avoid independent sequence authorities where unnecessary.

## 16. Artifact ecosystem

Existing artifacts include:

- Builders ArtifactRef
- graph/node outputs
- files changed/branches/commits
- canvas/design artifacts
- generated images/documents
- sandbox files
- evaluation results
- replay records/logs

Canonical mapping:

- Artifact is a first-class output/reference owned by Workspace and/or Run
- NodeRuns produce ArtifactRefs
- domain packages can attach richer artifact metadata/types
- avoid embedding large artifact state into every specialized RunResult

## 17. Observability/replay ecosystem

Existing:

- tracing/logging/metrics
- recording/replay LLM clients
- recording/replay tool dispatchers
- TraceContext
- ReplaySession/events/store
- sensitivity/PII tiers
- Langfuse/OTel adapters in app/server layers

Canonical mapping:

- observe canonical IDs: workspace, persona, run, node_run, attempt, invocation
- replay records are diagnostics/provenance, not a second Run lifecycle
- runtime metrics remain ExecutionRuntime mechanics; business/domain metrics remain domain-owned

## 18. Resilience/recovery ecosystem

Existing:

- circuit breakers
- backoff/retries
- error classification
- task crash-loop policy
- checkpoint compatibility/version checks
- durable graph resume
- provider fallback

Canonical separation:

- Policy decides retry/recovery eligibility
- Attempt records physical retries
- Run owns logical terminal state
- checkpoint stores resumable domain state
- ExecutionRuntime performs mechanics
- Provider selection/fallback belongs capability layer

## 19. Sandbox/process ecosystem

Existing:

- Docker/container sandbox
- fake sandbox
- microVM backend/protocol
- subprocess harness
- workspace path validation
- env sanitation
- process execution

Canonical mapping: Provider/Binding implementations used by NodeTypes that require code/process execution. Sandbox instance/session lifecycle does not replace Run/NodeRun lifecycle.

## 20. Portability/import-export ecosystem

Existing portability can import multiple external agent/skill formats and export a narrower MCP/SKILL.md representation.

Canonical mapping:

- foreign Agent -> NodeTemplate/Agent definition
- foreign skill/tool -> Capability/Binding/ToolExposure/NodeTemplate depending semantics
- import retains provenance
- export serializes canonical objects without making transport formats authoritative

## 21. Skills ecosystem

Existing skills subsystem includes:

- parser/loader
- registry/catalog
- connectors
- marketplace
- importers/import pipeline
- forge
- fixer/security repair
- canary

Canonical decomposition needs case-by-case handling:

- instruction/prompt content -> PromptTemplate or NodeTemplate fragment
- parameter/schema declaration -> Schema/ParameterSet
- executable endpoint/connector -> Binding
- advertised ability -> Capability/ToolExposure
- package/source/trust metadata -> provenance/policy

`Skill` is therefore a product/reuse concept, not automatically a primitive.

## 22. Classifier/router/conduit ecosystem

Existing classifier and Conduit choose task type/model/agent/route based on intent, tier and configuration.

Canonical mapping:

- classifier = decision service/Node or product ingress component
- model resolver/router = Provider/Binding selection
- Conduit = facade/orchestration adapter that should launch canonical Graph/Run rather than own hidden execution semantics

## 23. Prompt ecosystem

Existing:

- prompt store/manager
- AgentIdentity soul prompt reference
- Builders prompt registry
- graph prompt builders/strategies
- design/Turing/domain prompts

Canonical mapping:

- PromptTemplate is primitive/reusable asset
- Persona/NodeTemplate may bind a version/default
- Node object may customize it independently
- Run snapshots effective prompt/version for provenance

## 24. Model ecosystem

Existing:

- model names/fallbacks/constraints in AgentIdentity
- model resolver
- LiteLLM gateway adapters
- PM/Conductor model tiers
- local fallback/emergency RSI pools
- provider health/fallback

Canonical mapping:

- Model = primitive logical model reference
- ModelProvider/endpoint = Provider
- configured access = Binding
- model selection policy = Policy/router
- effective model and parameters are snapshotted on NodeRun/Attempt

## 25. Quota/billing ecosystem

Existing quota subsystem tracks token usage/billing, while sequence policy also supports cumulative token/cost budgets.

Canonical separation:

- quota/billing = accounting/entitlement state
- permission may deny access based on entitlement
- policy may enforce per-run/session budgets
- observability records actual usage
- Run/NodeRun/Invocation carry correlation IDs for chargeback

## 26. Integrations ecosystem

Existing integrations include Home Assistant, CoinSwarm, Turing and external services, plus Jira/Confluence/git/browser/tool providers.

Canonical mapping:

- integration client = Provider/Binding implementation
- domain event adapters = Event handlers
- reusable operations can be surfaced as ToolExposure or NodeTemplates
- integration identity/config belongs Workspace/Persona scope

## 27. Builders ecosystem

Current Builders concepts:

- Frank, Mason, Auditor workers
- stages
- BuildersRuntime handler dispatcher
- prompt registry
- allowed tool registry
- RunRequest/RunResult
- ArtifactRef
- StageEvent
- pipeline/orchestrator/graph
- CLI/TUI
- Builders RSI

Canonical target:

```text
Persona: Builders
├── surfaces: UI, Builders CLI, Builders RSI
├── Agent NodeTemplates: Frank, Mason, Auditor
├── GraphTemplates: builder workflows
└── policy/tool bindings

Workspace
└── instantiated Builder Graph
    └── Nodes (Frank/Mason/Auditor/stages)

Run
└── NodeRuns
```

BuildersRuntime becomes a specialized node/handler adapter, not a second universal runtime. Builders prompt/tool registries migrate toward NodeTemplate/Binding configuration.

## 28. Canvas/design ecosystem in Persona terms

Potential Persona examples:

- Book Builder Persona
- Presentation/Design Persona
- General Design Persona

Each Persona can expose appropriate UI surfaces, GraphTemplates, NodeTemplates, design systems, image-generation/render bindings and export permissions.

This lets canvas/design remain strong specialized packages while fitting the same product ownership/execution model.

## 29. Turing ecosystem in Persona terms

Potential Persona composition:

```text
Persona
├── purpose/theme
├── self-model/personality defaults
├── proactive producers
├── memory policy
├── Agent NodeTemplates
├── GraphTemplates
└── allowed bindings/surfaces
```

Turing should enrich Persona/Agent semantics rather than create a second root object hierarchy.

## 30. Developer/governance ecosystem

These are intentionally outside the product runtime ontology:

- maistro-bootstrap
- maistro-registry
- ADR/spec lifecycle tooling
- lifecycle linters
- architecture fitness checks
- quality baselines (radon/vulture/reachability)
- formal conformance tests
- mutation testing
- security scans
- release/promotion branch topology
- repo mining/backfill tools
- benchmark provenance tooling

They constrain and validate the architecture but are not Workspace children or NodeTypes unless explicitly invoked as tools by a Persona.

## 31. Interfaces/surfaces

Current/possible interaction surfaces include:

- Hive web UI/backend APIs
- generic maistro-server API
- chat-completions compatible API
- WebSocket/SSE streams
- Builders CLI/TUI
- Builders RSI CLI/autorun
- maistro-rsi CLI
- harness session API
- MCP surfaces
- canvas/book-maker frontend
- design consumers
- external imported agents/tools

Canonical rule: surfaces expose Persona-authorized operations over the same underlying objects. A surface should not require a parallel domain model.

## 32. Primary duplicate/overlap families

### Execution lifecycle duplicates

- TaskStatus
- GraphPhase/GraphRun
- DurableRunRecord status
- A2ATask status
- AgentTask status
- Builders RunStatus
- schedule TaskExecution
- RSI run/cycle status
- app-specific DAG run status

Target: canonical Run/NodeRun/Attempt with specialized projections only where UX requires them.

### Definition/template duplicates

- AgentIdentity
- AgentCard
- AgentSpec portions
- recipes
- GraphConfig/DAG files
- PM role definitions
- Builders worker/stage definitions
- skills
- imported agent/skill formats
- design skills/systems

Target: NodeTemplate/GraphTemplate plus domain-specific reusable assets.

### Fulfillment duplicates

- tool executor
- capability provider
- harness runner
- HTTP API client
- MCP tool
- sandbox executor
- renderer
- image generation provider
- delegated agent

Target: Capability/Provider/Binding/Invocation with protocol-specific adapters.

### Correlation/event duplicates

- task_id
- run_id variants
- graph run IDs
- A2A task IDs
- trace IDs
- session IDs
- builder run IDs
- event sequences
- audit sequence IDs

Target: canonical ownership IDs with explicit relationships, while Session and audit/event sequences remain separate concepts where necessary.

### Permission/trust duplicates

- auth scopes
- trust tiers
- tool allowlists
- delegation modes
- collaboration roles
- peer trust
- approval gates
- design trust
- promotion approval

Target: hierarchical Permission ceiling + composable Policy/trust mechanisms.

## 33. Things that should remain distinct

Convergence should not collapse these merely to reduce noun count:

- User vs Workspace
- Workspace vs filesystem workdir
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
- Graph traversal semantics vs ExecutionRuntime mechanics
- product packages vs generic platform primitives
- developer/governance tooling vs runtime domain

## 34. Canonical end-state ecosystem

```text
USER / OWNERSHIP
User
└── Workspace
    └── Persona

REUSABLE LIBRARY
Persona
├── NodeTemplate
├── GraphTemplate
├── PromptTemplate
├── DesignSystem / other domain assets
└── authorized capability/binding defaults

EDITABLE WORKSPACE OBJECTS
Workspace
├── Graph
│   ├── Node
│   └── Edge
├── domain artifacts/projects
└── Sessions

EXECUTION HISTORY
Workspace
└── Run
    ├── NodeRun
    │   └── Attempt
    ├── Event
    ├── Artifact
    └── child Run

FULFILLMENT
Node
└── Capability
    └── Provider selection
        └── Binding
            └── Invocation

CONTROL
User -> Workspace -> Persona -> Graph -> Node -> Binding -> Invocation
  permission ceiling
Policy evaluates state/context inside that ceiling
Credentials are resolved only for permitted Bindings/Invocations

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
Canvas / Design / Turing / Builders / RSI / Evolve
  provide Personas, NodeTypes, templates, bindings, policies and domain assets
  without inventing parallel universal execution lifecycles

SURFACES
Web UI / API / CLI / RSI / MCP / harness endpoints
  Persona-authorized views/controllers over the same objects

GOVERNANCE
Bootstrap / Registry / ADR/SPEC / CI/formal/security tooling
  validates and configures the ecosystem but stays outside runtime ontology
```

## 35. Convergence questions that remain open

1. Exact persisted shape and naming for Workspace while retaining Project compatibility.
2. Whether a Workspace has exactly one active Persona at a time or can contain multiple Persona objects with one selected/active context.
3. Whether NodeTemplate/GraphTemplate catalogs are Persona-owned only, Workspace-owned with Persona visibility, or support global/user catalogs with inheritance.
4. How template versions and provenance are represented and promoted from mutable objects.
5. Exact canonical Run/NodeRun/Attempt persistence schema.
6. Whether every execution is normalized to a Graph, including single-node graphs, or whether Run may directly reference a Node while the UX treats it equivalently to a single-node Graph.
7. Exact NodeType registry/extension mechanism.
8. Binding persistence and whether Provider selection happens when the object is saved or when an Attempt starts.
9. Hierarchical permission representation and evaluation algorithm.
10. How legacy org/team scopes map around User/Workspace/Persona without losing enterprise-ready primitives.
11. Which current event models become canonical events versus projections.
12. How Turing self-model/personality splits between Persona and Agent Genome.
13. How DesignSystem/CanvasProject/DesignProject map to Workspace assets versus specialized Graph/Node objects.
14. Which Builders stage concepts are Nodes versus merely internal steps inside one Node implementation.
15. How evaluation/evolution promotion creates new template versions without mutating active workspace objects.

## 36. Immediate use of this inventory

Use this document together with `ARCHITECTURE-CONVERGENCE-MATRIX.md` and `EXECUTION-RUNTIME-SEAM-MAP.md` to drive the next architecture-locking pass.

For every implementation change, require an explicit answer to:

1. Which canonical object does this existing thing map to?
2. Is it a domain object, reusable template, runtime record, binding/provider, specialized package concept, surface, or governance tool?
3. Who owns its lifecycle?
4. What permission scope applies?
5. Does another subsystem already own the same lifecycle or semantic responsibility?
6. What compatibility adapter allows migration without behavior loss?
7. What existing duplicate can be removed after parity tests prove convergence?
