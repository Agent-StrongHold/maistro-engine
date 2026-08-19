# MAIstro Package Ownership Working Map

Status: architecture convergence working hypotheses. Package ownership conclusions may guide mapping work, but physical package renames/moves are not approved merely by appearing here.

This document records package-level observations that emerged while validating the ecosystem inventory against the actual repository tree. The goal is to prevent historical package names from dictating incorrect domain ownership while avoiding premature churn before the canonical vocabulary is locked.

## Naming and ownership rule

A package name should eventually communicate the domain or product responsibility it owns. Historical implementation location does not define canonical architecture, but naming cleanup follows semantic convergence rather than preceding it.

The canonical runtime spine remains:

```text
Workspace -> Run -> ExecutionRuntime -> Capabilities
```

with the richer domain model:

```text
User -> Workspace -> Persona -> Graph/Node -> Run -> NodeRun -> Attempt
Capability -> Provider -> Binding -> Invocation
```

## Package map

| Package | Current reality | Canonical role | Working disposition |
|---|---|---|---|
| `maistro-core` | Shared domain/runtime/platform primitives | Authoritative reusable MAIstro domain semantics and generic platform mechanisms | KEEP; move duplicated domain ownership here only when semantics are truly generic |
| `maistro-server` | Generic FastAPI/API surface including tasks, agents, Canvas, chat compatibility, webhooks, websocket progress, health | Transport/application adapter over canonical Workspace/Persona/Graph/Run services | KEEP; remove independent lifecycle truth |
| `hive-conductor` | Product backend with app-specific routes, orchestration, task adapter, telemetry, UI assets and integrations | Hive product/application consuming canonical core services | KEEP; progressively remove duplicate orchestration/lifecycle ownership |
| `maistro-canvas` | Large reusable canvas/composition library plus standalone book-builder frontend, persistence, agents, image pipeline and export | Specialized product/domain package providing Persona surfaces, NodeTypes, capabilities, artifacts and app-specific UI | KEEP/SPLIT BY RESPONSIBILITY; do not flatten into core |
| `maistro-design` | Design engine, projects, skills, systems, renderers/providers, trust/review, persistence | Design domain package above the universal runtime model | KEEP; map renderers/providers to capability layer and design execution to Nodes/Runs |
| `maistro-evolve` | Evolutionary optimization/evaluation domain | Optimization/evaluation graphs, nodes, policies and template promotion behavior | KEEP; remove private execution lifecycle where present |
| `maistro-rsi` | Recursive self-improvement product/domain with sandbox, git, evaluation and autorun | Persona capability + Graph/Node definitions + canonical Runs | KEEP; converge execution semantics |
| `maistro-turing` | Self-model, personality/drives, proactive producers, cognition, memory bridge, actor/chat runtime, providers/tools | Persona/Agent semantic extensions plus capabilities/triggers; runtime-facing behavior must create canonical Runs | KEEP; do not misclassify as merely evaluation tooling |
| `maistro-bootstrap` | Installer/materializer plus Builders agent loop, model selector, sandbox/container execution, credentials, delivery and sessions | Bootstrap/install tooling plus runtime/Builders responsibilities that may belong elsewhere | KEEP package during audit; candidate responsibility split after parity mapping |
| `maistro-registry` | ADR/spec parser, linker, DAG, generator, validator and CLI | Architecture/spec governance tooling | KEEP during audit; naming cleanup is a candidate, not a decision |

## `maistro-registry` naming candidate

The current `maistro-registry` name can be confused with runtime registries even though the package owns architecture/specification governance tooling.

A future naming cleanup could use a more explicit name such as:

```text
Distribution/package: maistro-arch-governance
Python import:         maistro_arch_governance
CLI:                   maistro-arch
```

This is **not approved for physical rename by this audit**. The repository should first lock the ontology, references, compatibility requirements and package ownership boundaries.

Current responsibilities to preserve regardless of final name:

- ADR/spec parsing
- architecture dependency/DAG analysis
- link/reference validation
- schema validation
- architecture linting
- architecture fitness rules
- conformance checks
- documentation/code architecture governance

Keep `Registry` terminology available for semantically specific runtime/domain concepts such as:

- `NodeTypeRegistry`
- `TemplateRegistry`
- `CapabilityRegistry`
- `ProviderRegistry`
- `ModelRegistry`
- `ArtifactRegistry`

Do not introduce one generic runtime `Registry` abstraction merely because several catalogs exist.

## `maistro-bootstrap` responsibility candidate

The package currently mixes deployment/bootstrap concerns with user-work execution concerns. Treat the split as conceptual during the audit, then migrate only where code-level evidence and parity tests justify it.

Likely bootstrap-owned responsibilities:

- installer/wizard
- platform detection
- plan/resolver/materialization
- environment/provider initialization
- bootstrap configuration/schema
- bootstrap-specific credential acquisition required only for installation

Responsibilities to map against canonical owners before moving:

- Builders agent loop -> Builders Agent Node/NodeTemplate execution
- model selector -> model Provider/Binding selection policy
- sandbox/container execution -> sandbox Capability/Provider/Binding
- runtime session state -> canonical Session where product continuity is intended, otherwise execution-local state
- delivery -> Artifact/delivery capability
- execution credentials -> canonical Credential/Binding resolution

Bootstrap itself is not a Run lifecycle. If bootstrap tooling is intentionally invoked as user workload later, that invocation may be represented by an ordinary Node/Run without changing package ownership.

## `maistro-canvas` boundary

Canvas is intentionally not treated as "just UI". The repository contains both a reusable library and a substantial book-making application surface.

Reusable MAIstro-facing candidates:

- canvas/compositor execution -> specialized NodeTypes
- image generation -> Capability/Provider/Binding
- asset composition -> NodeType + Artifact output
- export/PDF composition -> NodeType/Capability + Artifact output
- persisted generated assets -> canonical Artifact references plus Canvas domain metadata
- reusable agents -> Agent NodeTemplates
- reusable pipelines/templates -> GraphTemplates

Remain Canvas/book-product specific unless reuse proves otherwise:

- book/order/customer/product-format domain objects
- book workspace/wizard UX
- Lulu publishing integration behavior specific to the product
- story/character/page-layout domain semantics
- Canvas-specific frontend state and editing UX

Target product expression:

```text
Workspace
└── Persona: Book Builder
    ├── GraphTemplates
    ├── Agent NodeTemplates
    ├── image-generation bindings
    ├── compositor/export bindings
    └── Canvas/book UI surface
```

Do not move app-specific concepts into `maistro-core` merely to reduce package count.

## `maistro-turing` boundary

Turing is a cognition/self-model extension, not an evaluation package.

Map its responsibilities as follows:

- self-model/personality/drives -> Persona and/or Agent Genome extension, final split to be locked by ADR
- proactive producers -> Event/Schedule triggers or NodeTemplates depending behavior
- cognition/reactor stages -> Agent Node behavior/internal strategy unless independently executable
- actor/chat runtime -> adapter that creates canonical Runs
- Turing memory bridge -> canonical memory service integration
- providers/tools -> Capability/Provider/Binding/ToolExposure
- Turing backend/API -> product surface, not lifecycle authority

## Physical package-change rule

Do not physically rename or split packages during the inventory phase solely to make names match the emerging ontology.

A physical package move/rename requires:

1. canonical semantic owner is locked;
2. dependency/import impact is known;
3. compatibility plan is explicit;
4. behavior/reachability tests exist;
5. the change is mechanically isolated enough to diagnose regressions.

## Inventory completion gate

The ecosystem inventory is complete only when every meaningful subsystem can answer:

```text
thing
-> current owner
-> canonical concept
-> dependencies
-> lifecycle owner
-> persistence owner
-> permission scope
-> product entry point
-> keep/split/merge/remove
```

No ADR should treat vocabulary as final until the remaining package/subsystem audit shows no missing universal concept.
