# MAIstro Ecosystem Map

Status: working architecture inventory for the post-sprawl convergence effort.

This document identifies the major product, domain, execution, capability, security, data, interface, platform, and engineering-control components already present in MAIstro. It is intentionally descriptive before it is normative. The purpose is to understand what exists well enough to stitch the system together without deleting useful semantics or creating another parallel abstraction layer.

The guiding product model is derived from the intended UX, not from current package boundaries.

## 1. Canonical product hierarchy

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
    └── Run[]
        ├── graph reference/snapshot
        ├── NodeRun[]
        ├── Attempt[]
        ├── Events
        ├── Artifacts
        ├── Checkpoints
        └── Outputs
```

Template and object semantics are deliberately distinct:

```text
NodeTemplate  -> instantiate -> Node  -> mutate -> optionally save as new NodeTemplate
GraphTemplate -> instantiate -> Graph -> mutate -> optionally save as new GraphTemplate
```

The instantiated workspace object is independent from the template after creation. It keeps provenance to the source template/version, but template edits do not silently mutate existing workspace objects.

## 2. Lower-level vocabulary

### Definition primitives

- Model
- PromptTemplate
- ParameterSet
- Schema
- Protocol
- Credential reference
- Permission declaration
- Policy
- Predicate
- Transform

### Intelligence composition

```text
Genome
├── Model
├── PromptTemplate
└── ParameterSet

Agent
├── Genome
├── authorized Bindings
└── Permission/Policy constraints
```

An Agent is not a special top-level execution lifecycle. It is one possible Node payload/type.

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

- Capability: what can be requested.
- Provider: an available implementation, including selection, health, and fallback concerns.
- Binding: a consumer-specific configured and authorized route to a provider, agent, human, harness, process, API, or other fulfiller.
- Invocation: one runtime request through a binding.
- ToolExposure: the model-visible representation of an allowed capability/binding.

This model naturally supports agents-as-tools. An Agent without direct permission to invoke a capability can hold a Binding to another Agent that is configured and authorized to fulfill it.

## 3. Permission hierarchy

Permissions constrain downward through the object hierarchy:

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

A lower level can narrow authority but cannot widen an ancestor's authority. Policy evaluates the permitted action in context; Permission determines whether the action is in scope at all.

## 4. Ecosystem planes

MAIstro is easier to understand as several cooperating planes rather than one giant class tree.

### A. Product ownership plane

Owns durable user-facing objects and their relationships:

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

### B. Definition and knowledge plane

Reusable descriptions and learned context:

- Genome
- prompts
- models and parameters
- agent recipes
- skills
- persona templates
- repertoire
- memory
- codebase index
- code registry
- portability/import-export

### C. Capability and fulfillment plane

Ways work can be fulfilled:

- capabilities and slots
- providers
- bindings
- tools
- integrations
- delivery
- harnesses
- HTTP/MCP
- credentials
- sandboxes/processes
- agent delegation
- human interaction

### D. Execution plane

Owns execution facts and replaceable mechanics:

- Run / NodeRun / Attempt
- ExecutionRuntime
- graph traversal
- task ingress/admission
- scheduler trigger-to-run launch
- pause/resume/checkpoint
- retries/recovery
- cancellation/deadlines
- bounded concurrency/backpressure

### E. Security and trust plane

- principal/authentication
- identity lifecycle
- hierarchical permission evaluation
- policy engine
- Warden threat detection
- Sentinel policy enforcement
- Gate input processing
- approvals
- delegability
- reversibility
- credential access
- sandbox requirements
- elevation and strike tracking
- provenance/signature checks

### F. Resource and data plane

- memory
- sessions
- collaboration/presence
- artifacts/files
- events
- quota/accounting
- persistence adapters
- observability records

### G. Product application/persona plane

Specialized product experiences built on the shared substrate:

- Builders
- Builders RSI
- PM Fleet
- Canvas
- Design
- Turing
- RSI/Evolve

### H. Interface plane

How humans and external systems reach the same domain objects:

- Hive Conductor UI/API
- maistro-server API
- WebSocket/SSE
- Builders CLI
- Builders RSI surface
- MCP
- harness session API
- service-to-service API

### I. Platform/install plane

- maistro-bootstrap
- package/config loading
- deployment images
- migrations
- install/upgrade tooling

### J. Engineering control plane

- maistro-registry
- ADR/SPEC lifecycle and dependency graph
- CI
- quality ratchets
- reachability analysis
- formal conformance
- mutation testing
- security scanning
- release promotion
- repo-native agent instructions/skills

These controls govern the product but are not children of Workspace, Persona, Graph, or Run.

## 5. Package-level map

| Package | What it really is | Canonical relationship | Direction |
| --- | --- | --- | --- |
| `maistro-core` | Shared domain, capability, security, memory, execution, routing, and resource substrate | Houses canonical primitives and services | KEEP, converge internal ownership |
| `hive-conductor` | Mission-control product shell with frontend, API routes, stores/services, DAGs, integrations, schedules, settings | Primary UI over Workspace/Persona/Graph/Run | CONVERGE shell onto core domain objects |
| `maistro-server` | API/service shell with agents, auth, graph, memory, sessions, schedules, tools, workspaces | Interface adapter over same core objects | KEEP interface, remove duplicate domain ownership |
| `maistro-bootstrap` | Installation/bootstrap/state materialization | Platform plane | KEEP |
| `maistro-canvas` | Specialized book/illustration application | Persona/domain app using canonical Graph/Node/Run/Artifact | REHOME lifecycle onto shared substrate |
| `maistro-design` | Specialized design generation/rendering application | Persona/domain app, renderer providers as bindings | REHOME lifecycle onto shared substrate |
| `maistro-turing` | Specialized conversational/proactive agent harness with memory and producers | Persona + Agent/Nodes + scheduled/event-triggered Runs | REHOME execution identity, preserve Turing semantics |
| `maistro-rsi` | Builders recursive self-improvement domain engine | Builders Persona capability/workload producer | CONVERGE private run lifecycle into canonical Run |
| `maistro-evolve` | Evolution algorithms, genome population, scoring, tournaments, eval harnesses | Domain semantics invoked by RSI/Evolve Nodes/Runs | KEEP semantics, converge execution/audit ownership |
| `maistro-registry` | ADR/SPEC dependency graph and governance validator | Engineering control plane | KEEP separate from product runtime |

## 6. Existing Workspace and Persona are already close to the target

### `projects` is already Workspace in all but name

Current `Project` explicitly describes itself as a per-user workspace. It already scopes:

- members/roles
- outcomes
- DAGs/durable runs through `project_id`
- integration resource bindings
- profile/context
- optimizer settings
- budget-like settings
- use-case selection

Target split:

```text
Project today
  ↓
Workspace
├── membership / ownership
├── resources and integration bindings
├── graphs
├── runs
├── artifacts
├── workspace context
└── Persona reference
```

Some current Project fields are actually Persona concerns, particularly `use_case`, UI-selection behavior, and some purpose/profile semantics. Preserve storage compatibility during migration, but stop allowing Project and Persona to independently describe the same product identity.

### `personas` already implements much of the intended Persona layer

Current `PersonaTemplate` supports:

- `kind: workspace`
- brand
- voice
- UI scope
- spawn declarations
- tools and skills per spawn
- eval rubrics
- hard gates
- onboarding interview

The existing expander converts Persona spawns into AgentRecipe records and governance/eval bindings.

Target evolution:

```text
Persona
├── purpose / brand / voice
├── allowed UI and CLI surfaces
├── onboarding behavior
├── permissions/policies
├── NodeTemplate[]
├── GraphTemplate[]
├── working Graph[] visibility/ownership relationship
├── evaluation definitions
└── default capability/binding exposure
```

Do not create another Persona abstraction. Extend/converge the existing persona system.

## 7. Core subsystem map

### `agents`

Contains specialized agent implementations, base Agent, catalog, factory, context builder, conductor, strategies, recipes, feedback, PM fleet, and specialist families such as Artificer/Auditor.

Canonical decomposition:

```text
Agent definition
├── Genome
├── authorized bindings/tool exposure
├── permissions/policy
└── optional domain-specialization metadata

Agent Node
└── references/embeds an Agent definition for execution
```

Action:
- keep Agent behavior and specialist implementations;
- extract reusable definition from execution/spawn context;
- map recipes toward NodeTemplate/Agent definition;
- avoid Agent-specific Run lifecycle;
- use canonical NodeRun/Attempt for execution.

### `a2a`

Contains broker, delegate, guest peers, and a dedicated lifecycle implementation.

Canonical decomposition:

- routing/trust/transport: KEEP
- remote-agent binding: KEEP
- independent A2A task lifecycle: MERGE into child Run/NodeRun
- guest peer identity/trust: KEEP under Binding/security

Target:

```text
Agent A NodeRun
  -> Agent-backed Binding
      -> child Run / child NodeRun for Agent B
```

### `graph`

Contains graph definition/validation, NodeRun, traversal, concurrency, events, harness adapters, durable runs, optimization-related helpers, and node implementations.

Preserve:
- graph topology/edge meaning
- conditional/cyclic/parallel semantics
- node type semantics
- DAG validation
- graph-specific state/checkpoint payloads

Converge:
- generic concurrency into ExecutionRuntime where behavior-equivalent
- generic cancellation/deadline mechanics into ExecutionRuntime
- graph-local lifecycle/events onto Run/NodeRun + canonical event stream
- durable run records onto canonical Run persistence

Do not replace rich GraphRun traversal with durable traversal until parity tests cover conditions, parallel branches, cycles, retries, cancellation, and events.

### `orchestrator`

Contains planner, validation, hierarchy/master coordination, and waves.

Classification:
- planner/validation: graph construction/domain semantics
- hierarchy: coordination semantics
- waves/fan-out/fan-in: partly graph semantics, partly generic runtime mechanics

Keep Python/domain decisions. Move only proven generic scheduling/concurrency mechanics behind ExecutionRuntime.

### `conduit`

Current Conduit explicitly acts as the request pipeline:

```text
Gate -> classify -> resolve agent -> determine tier -> dispatch
```

It says it decides/delegates and does not execute tasks directly.

Target role: front-door request routing into the active Workspace/Persona and then Graph/Run creation or an appropriate interaction flow. Do not merge Conduit into ExecutionRuntime.

### `classifier`

Intent and complexity classification, keyword routing, multi-intent logic, LLM fallback.

Target: request interpretation/planning service used by Conduit/Persona or graph-construction flows. It does not own Runs.

### `router` and `providers`

Two related but distinct selection layers already exist:

- `router`: general selection/scoring/scarcity/speed logic
- `providers`: LLM provider registry/config/router/protocols/types

Target: model/provider selection service used when resolving a Model or model Binding. Avoid leaking provider choice into Persona/Graph ownership.

### `config`

Loader, model resolver, settings, presets, rate limits, config models.

Target: deployment/default configuration plane. Persona or NodeTemplate defaults may be seeded from config/presets, but runtime Workspace objects should not become mutable aliases of process config.

### `capabilities`

Contains capability protocols, slots, provider registry, discovery, harness manager, HTTP seams, providers, and self-repair governance.

This is the strongest existing basis for canonical Capability/Provider.

Target addition is the consumer-specific layer MAIstro currently lacks consistently:

```text
Capability
  -> selected Provider
      -> Binding scoped to Workspace/Persona/Node
          -> Invocation
```

Do not rename Provider to Binding. They are different concepts.

### `tools`

Concrete tool families plus approval, reversibility, network guard, sandbox, result types.

Target:
- concrete tools become Provider/Binding implementations;
- tool metadata becomes ToolExposure + capability metadata;
- approval/reversibility/sandbox requirements become Binding/Invocation policy attributes;
- all tool calls pass through one Invocation security/event/provenance path.

### `skills`

Catalog, loader/parser, forge, canary, marketplace, connectors, importers, fixer, import pipeline, registry.

Current Skill mixes several concerns. Decompose without deleting useful features:

- reusable capability description
- ToolExposure/schema
- Binding configuration hints
- prompt/instruction fragments
- trust/provenance
- import policy
- catalog/marketplace metadata

### `portability`

Imports external agent/skill formats and exports compatible representations.

Target: adapter at the definition boundary. External formats become canonical NodeTemplate/Agent/Capability definitions. Portability never owns execution.

### `delivery`

Dispatch/protocol/registry/types for outbound delivery.

Target: capability family whose providers are exposed via Bindings and invoked through canonical Invocation.

### `integrations`

Current integrations include Home Assistant, ntfy, CoinSwarm, and Turing.

Target: concrete Provider/Binding adapters plus event sources/sinks. They do not own execution lifecycle.

### `credentials`

Pool, provider protocols, providers, rotation, store, credential types.

Target:
- Workspace owns/binds credential references;
- Persona/Graph/Node/Binding permissions constrain use;
- credential material resolves only at Invocation time;
- rotation/store remains security/resource infrastructure.

### `identity` and `auth`

`auth` is primarily service-key/OAuth principal authentication and scope plumbing. `identity` contains agent identity lifecycle and capability-token behavior. `security` contains runtime threat/policy controls.

Target handoff:

```text
Authentication
  -> Principal / Identity
      -> PermissionContext
          -> hierarchical permission evaluation
              -> Policy/Security decision
```

Do not merge auth and security wholesale. Normalize the handoff between them.

### `security`

Warden, Sentinel, Gate, auth adapters, DAG-shape controls, delegability, dangerous-tool classification, external-content protection, guardrails, elevation/strike-related behavior.

Target: one mandatory security path at Binding/Invocation and appropriate input/output boundaries. Existing controls should become reachable, not reimplemented.

### `policy`

Sequence-aware policy engine, rules, gates, types.

Target: context-sensitive decision engine below hierarchical Permission. Policy can require approval, enforce budgets/sequences/velocity, etc., but cannot grant authority blocked by an ancestor Permission scope.

### `projects`

Rename/converge semantically to Workspace while preserving storage/API compatibility during transition.

### `personas`

Promote existing PersonaTemplate system to the canonical purpose/theme/configuration layer between Workspace and templates/graphs.

### `prompts`

Prompt storage/diff service. Canonical PromptTemplate primitive source.

### `memory`

Context assembly, episodic memory, exposure controls, learnings, mutations, outcomes, scopes, stores.

Target memory scopes:

- Run-local working state
- Workspace knowledge
- Persona context
- Agent-specific memory
- reusable learned patterns/repertoire

Memory is a runtime/resource service and event consumer, not an execution root.

### `repertoire`

Reuse-first recall/rehearse/compose algorithm. Its `run.py` is a vocabulary collision, not another Run lifecycle.

Target: learned-pattern retrieval/strategy under memory and graph/node planning. Consider renaming the operation later if canonical `Run` makes the filename/function confusing.

### `codebase`

Code parsing/index/violations knowledge resource.

Target: Workspace resource that Builders/engineering Personas expose to Nodes through context/bindings.

### `code_registry`

Registry/types/verification for trusted code artifacts.

Target: provenance/trust resource attached to capabilities, artifacts, and executable definitions. It should feed security checks and reusable knowledge.

### `sessions`

Session store/search for conversational continuity.

Session is not Run. A Session can span/reference multiple Runs and messages.

### `collaboration`

Session-scoped co-ownership, roles, presence, event/history behavior.

Keep as collaboration resource. Normalize member identities/permissions and event transport with shared systems, but do not collapse Presence/Session into Run.

### `events`

Already has bus, durable log, invocation events, processors, recipes, trigger store.

Use this subsystem as the base for canonical domain events. Converge graph events, task progress callbacks/webhooks, Builders StageEvent, Hive event stores, and observability correlation onto it rather than creating another event framework.

### `observability`

Logging, metrics, middleware, proxy, replay, tiers, tracing.

Target: consumer/projection of canonical Workspace/Run/NodeRun/Invocation IDs and canonical events. Observability must not define execution lifecycle.

### `quota`

Billing/rate profile/reconciliation/recording/tracking/usage verification.

Keep as accounting/enforcement service. Attribute consumption to canonical Workspace/Run/NodeRun/Invocation identifiers.

### `persistence`

Postgres and SQLite adapters for agents, audit, learnings, outcomes, prompts, quota, sessions, etc.

Keep as infrastructure adapters. Over time, repositories should persist canonical domain objects instead of package-specific parallel lifecycle models.

### `tasks`

Queue, lanes, models/status, runner, checkpoint/replay/recovery, progress webhook.

Decompose:

```text
WorkRequest / ingress
├── queue
├── priority
└── lane/admission policy

Run
├── status
├── attempt
├── checkpoint
└── output/error
```

Task lanes are real scheduling policy and must not be flattened into a generic semaphore. Task status must stop being a competing execution lifecycle once Run is canonical.

### `scheduling`

Schedule definitions/history belong outside Run. A trigger creates a Run.

```text
Schedule -> Run launcher -> Run -> ExecutionRuntime
```

### `resilience`

Retry/circuit/recovery policy belongs around Attempt/Invocation mechanics and should not create another work identity.

## 8. Domain applications and Persona surfaces

### Builders

Current Builders has its own runtime/contracts, prompts/tools registry, orchestration, stages, CLI, and RSI integration.

Target representation:

```text
Builders Persona
├── surfaces: UI, Builders CLI, optional Builders RSI
├── GraphTemplate(s)
├── NodeTemplate: Frank
├── NodeTemplate: Mason
├── NodeTemplate: Auditor
└── capability/binding defaults
```

`RunRequest`/`RunResult` become adapter projections of canonical Run/NodeRun instead of separate lifecycle owners.

### PM Fleet

Existing agent fleet/use-case becomes a Persona plus templates/graphs. Project's current `use_case` behavior should become a Persona reference rather than a separate UI/domain switch.

### Canvas

Book/illustration pipeline becomes a specialized Persona with graph templates, rendering/image-generation Node types, artifact ownership, and UI surfaces. Preserve Canvas-specific data models and rendering semantics where they are true domain objects.

### Design

Design engine/renderers/providers become Node types and Provider/Binding implementations. Generated designs are workspace artifacts. Preserve design-specific semantics.

### Turing

Turing's actor/self-model/proactive producers are domain semantics. Turing should use Persona/Agent/Node templates, Session/Memory, scheduled/event-triggered Runs, and canonical events.

### RSI and Evolve

Evolution algorithms remain specialized domain logic. A cycle is represented as a Run/Graph/Node workload rather than an independent background lifecycle. Population/genome mutation/promotion/rollback remain Evolve domain state with existing safety/audit requirements.

## 9. Interface map

### Hive Conductor

Primary candidate for the workspace-centric UX. Existing routes/services already cover agents, audit, auth, chat, containers, DAGs, events, files, integrations, memory, MCP, providers, schedules, settings, tools, and workspaces.

Target: stop each route/service from owning separate domain state where core already provides the canonical object/service.

### maistro-server

Keep as a thinner API surface over the same canonical services. Avoid a second set of Workspace/Run/Task semantics.

### CLI

CLI is not a universal parallel MAIstro domain model. Builders CLI and Builders RSI are Persona-exposed interaction surfaces over the same underlying objects available in UI.

### MCP and harness APIs

Treat as protocol/interface adapters. They expose capabilities or allow an external orchestrator/harness to fulfill a Binding. They do not create a separate internal ontology.

## 10. Platform and engineering control plane

### `maistro-bootstrap`

Own install/bootstrap/materialization concerns only.

### `maistro-registry`

Own ADR/SPEC dependency graph, lifecycle validation, and generated governance views. It is an engineering governance system, not the product's capability registry.

### CI workflows

Separate workflows currently cover:

- standard CI
- quality
- security
- mutation
- formal conformance
- nightly formal conformance
- registry validation
- release installer
- cage guard
- RSI harvest

Keep these as control-plane enforcement.

### Quality ratchets

Existing baselines cover:

- reachability
- vulture/dead code
- radon complexity
- mutation
- enumeration coverage

The reachability ratchet is directly useful to this convergence program. Every subsystem stitched into a real product entry point should reduce the unreachable baseline rather than adding allowlist debt.

### Formal conformance

Keep property/state-machine verification for cross-cutting invariants such as permission monotonicity, run lifecycle, retry/recovery, RSI promotion/rollback, event ordering, and template provenance.

### Repo-native agent guidance

`.claude`, `.cursor`, AGENTS/CLAUDE/CONTRIBUTING and related repo guidance form the engineering-agent control plane. They should be updated after architecture is locked so automated contributors use the canonical vocabulary.

## 11. Major duplicate-ownership seams

These are the places most likely to produce real simplification.

### Execution identity/lifecycle

Current variants include:

- GraphRun
- durable run record
- task status/runner lifecycle
- A2A task/lifecycle
- Builders RunRequest/RunResult
- RSI RunState
- Hive DAG-run state
- scheduler execution history

Target: one Run / NodeRun / Attempt lifecycle with domain-specific projections.

### Node execution

Current NodeRun, durable node state, Builders stage execution, harness node execution, agent execution, HITL, eval and tool/harness paths should become NodeType-specific behavior under one NodeRun/Attempt identity.

### Delegation

Current Agent delegation, A2A broker/delegator/lifecycle, remote delegation nodes, and agent-as-tool behavior converge on Agent-backed Bindings plus child Runs.

### Tool / Skill / Capability overlap

Keep their useful distinctions but normalize ownership:

- Capability: semantic ability
- Provider: implementation availability
- Binding: configured/authorized consumer path
- ToolExposure: model-facing schema/name
- Skill: reusable/importable capability/instruction package or template metadata
- Invocation: runtime call

### Harness overlap

Sessionful harness manager, graph harness executor, durable harness dispatch, and foreign-harness APIs are lifecycle variants of a foreign fulfillment Binding, not separate top-level execution ontologies.

### Event fragmentation

Converge:

- graph events
- core EventBus/durable log
- task progress/webhooks
- Builders StageEvent
- Hive event stores/streams
- invocation events
- observability callbacks

onto one canonical event identity/schema with adapters/projections where necessary.

### Project / Persona overlap

Current Project owns some purpose/UI/use-case context that belongs conceptually to Persona. Current Persona `kind: workspace` already owns brand, voice, UI scope, tools/spawns/evals/interview.

Target boundary:

```text
Workspace = ownership, members, resources, objects, runs
Persona   = purpose, brand, behavior, templates, surfaces, defaults
```

### Auth / identity / security handoff

Do not merge packages blindly. Standardize the principal and permission context passed from authentication/identity into runtime security and Binding invocation.

### Product-shell stores/services

Hive and server should stop inventing parallel state owners where core stores/protocols already exist. Product shells adapt transport/UI to canonical services.

## 12. Important distinctions to preserve

Do not simplify these away:

- Session != Run
- Schedule != Run
- Attempt != Run
- Template != mutable workspace object
- Provider != Binding
- Capability != Binding
- Permission != Policy
- authentication != authorization/security policy
- graph semantics != runtime mechanics
- Persona != Workspace
- memory state != execution state
- artifact != event
- evolution domain state != execution lifecycle
- engineering control plane != product runtime

## 13. Target dependency direction

```text
Interfaces
  UI / API / CLI / MCP / harness
        ↓
Conduit / product application services
        ↓
User -> Workspace -> Persona
                 ├── Templates
                 ├── Graphs -> Nodes
                 └── Runs -> NodeRuns -> Attempts
                              ↓
                       ExecutionRuntime
                              ↓
                         Bindings
                              ↓
              Capability -> Provider -> Invocation
                              ↓
                external/internal fulfiller
```

Cross-cutting services surround this flow rather than becoming alternate roots:

```text
Security / Permissions / Policy
Memory / Sessions / Collaboration
Events / Artifacts / Observability
Quota / Credentials / Provenance
Persistence
```

## 14. Practical convergence workstreams

1. **Workspace/Persona split**
   - preserve Project persistence compatibility;
   - move use-case/brand/UI/purpose semantics toward existing Persona;
   - link Workspace to one active Persona initially;
   - define NodeTemplate/GraphTemplate provenance.

2. **Canonical execution identity**
   - Run, NodeRun, Attempt;
   - terminalization, parent/child, cancellation, timeout, retry, pause/resume;
   - persistence and event IDs.

3. **Graph/runtime seam**
   - preserve graph meaning;
   - move generic mechanics behind ExecutionRuntime;
   - parity-test legacy/durable execution before consolidation.

4. **Capability fulfillment normalization**
   - add Binding/Invocation around existing CapabilityProvider machinery;
   - normalize tools, harnesses, integrations, delivery, MCP/HTTP, agent delegation.

5. **Hierarchical permissions**
   - standard Principal/PermissionContext;
   - monotonic narrowing User -> Workspace -> Persona -> Graph -> Node -> Binding;
   - route every Invocation through security/policy.

6. **Event convergence**
   - adopt existing events subsystem as canonical base;
   - standard IDs and event schema;
   - UI stream, audit, memory extraction, recovery and observability consume it.

7. **Builders/RSI Persona convergence**
   - Builders CLI/RSI become surfaces;
   - Builders runtime contracts become Run/NodeRun adapters;
   - Frank/Mason/Auditor become reusable NodeTemplates/Agent definitions.

8. **Task/schedule/recovery convergence**
   - Task becomes ingress/admission;
   - Schedule launches Run;
   - recovery operates on persisted Run/Attempt/checkpoint.

9. **Domain-app convergence**
   - Canvas, Design, Turing, PM Fleet, RSI/Evolve use shared ownership/execution/events/security while preserving domain semantics.

10. **Interface thinning**
    - Hive and maistro-server become adapters over canonical services;
    - eliminate shell-local duplicate stores/lifecycles.

11. **Reachability burn-down**
    - use existing `quality/reachability-baseline.json` as the measurable debt ledger;
    - every wanted implemented subsystem gets a real product entry point;
    - unwanted islands are removed or documented honestly.

12. **Engineering-control update**
    - once vocabulary is locked, update ADR/SPECs, repo-agent guidance, architecture fitness tests and formal invariants.

## 15. Exit condition

The ecosystem is coherently stitched when a user can enter through any allowed Persona surface and the same underlying objects are visible everywhere:

```text
User
 -> Workspace
 -> Persona
 -> Graph / Node
 -> Run / NodeRun / Attempt
 -> Binding / Invocation
```

with one permission hierarchy, one event/correlation model, one execution identity model, shared memory/artifacts/credentials, and product shells that no longer expose backend package boundaries as separate concepts.

The goal is not to make every class disappear. It is to ensure each concept has one owner, each specialized subsystem has an explicit place in the hierarchy, and every implemented capability is either reachable through the product spine or intentionally outside it as platform/control-plane infrastructure.
