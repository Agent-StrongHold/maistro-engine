# MAIstro Package Ownership Decisions

Status: architecture convergence working decisions

This document records package-level decisions that emerged while validating the ecosystem inventory against the actual repository tree. These decisions are descriptive enough to guide the remaining inventory work and specific enough to prevent package names from dictating incorrect domain ownership.

## Naming and ownership rule

A package name should communicate the domain or product responsibility it owns. Historical implementation location does not define canonical architecture.

The canonical runtime spine remains:

```text
Workspace -> Run -> ExecutionRuntime -> Capabilities
```

with the richer domain model:

```text
User -> Workspace -> Persona -> Graph/Node -> Run -> NodeRun -> Attempt
Capability -> Provider -> Binding -> Invocation
```

## Package decisions

| Package | Current reality | Canonical role | Disposition |
|---|---|---|---|
| `maistro-core` | Shared domain/runtime/platform primitives | Authoritative reusable MAIstro domain semantics and generic platform mechanisms | KEEP; move duplicated domain ownership here only when semantics are truly generic |
| `maistro-server` | Generic FastAPI/API surface including tasks, agents, Canvas, chat compatibility, webhooks, websocket progress, health | Transport/application adapter over canonical Workspace/Persona/Graph/Run services | KEEP; remove independent lifecycle truth |
| `hive-conductor` | Product backend with app-specific routes, orchestration, task adapter, telemetry, UI assets and integrations | Hive product/application consuming canonical core services | KEEP; progressively remove duplicate orchestration/lifecycle ownership |
| `maistro-canvas` | Large reusable canvas/composition library plus standalone book-builder frontend, persistence, agents, image pipeline and export | Specialized product/domain package providing Persona surfaces, NodeTypes, capabilities, artifacts and app-specific UI | KEEP/SPLIT BY RESPONSIBILITY; do not flatten into core |
| `maistro-design` | Design engine, projects, skills, systems, renderers/providers, trust/review, persistence | Design domain package above the universal runtime model | KEEP; map renderers/providers to capability layer and design execution to Nodes/Runs |
| `maistro-evolve` | Evolutionary optimization/evaluation domain | Optimization/evaluation graphs, nodes, policies and template promotion behavior | KEEP; remove private execution lifecycle where present |
| `maistro-rsi` | Recursive self-improvement product/domain with sandbox, git, evaluation and autorun | Persona capability + Graph/Node definitions + canonical Runs | KEEP; converge execution semantics |
| `maistro-turing` | Self-model, personality/drives, proactive producers, cognition, memory bridge, actor/chat runtime, providers/tools | Persona/Agent semantic extensions plus capabilities/triggers; runtime-facing behavior must create canonical Runs | KEEP; do not misclassify as merely evaluation tooling |
| `maistro-bootstrap` | Installer/materializer plus Builders agent loop, model selector, sandbox/container execution, credentials, delivery and sessions | Bootstrap/install tooling plus misplaced runtime/Builders responsibilities | SPLIT; retain installation/materialization here, migrate runtime-like pieces to canonical Builders/runtime/capability owners |
| `maistro-registry` | ADR/spec parser, linker, DAG, generator, validator and CLI | Architecture/spec governance tooling | RENAME to `maistro-arch-governance` |

## `maistro-arch-governance`

The current `maistro-registry` name is misleading because the package does not own MAIstro runtime registries. It owns architecture/specification governance tooling.

Target naming:

```text
Distribution/package: maistro-arch-governance
Python import:         maistro_arch_governance
CLI:                   maistro-arch
```

Target responsibilities:

- ADR/spec parsing
- architecture dependency/DAG analysis
- link/reference validation
- schema validation
- architecture linting
- architecture fitness rules
- conformance checks
- documentation/code architecture governance

This intentionally leaves `Registry` terminology available for semantically specific runtime/domain concepts such as:

- `NodeTypeRegistry`
- `TemplateRegistry`
- `CapabilityRegistry`
- `ProviderRegistry`
- `ModelRegistry`
- `ArtifactRegistry`

Do not introduce one generic runtime `Registry` abstraction merely because several catalogs exist.

## `maistro-bootstrap` split

The package currently mixes deployment/bootstrap concerns with actual user-work execution concerns. Treat the split as conceptual first, then migrate code behind parity tests.

Remain in bootstrap:

- installer/wizard
- platform detection
- plan/resolver/materialization
- environment/provider initialization
- bootstrap configuration/schema
- bootstrap-specific credential acquisition required only for installation

Migrate or converge elsewhere:

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

Do not move these app-specific concepts into `maistro-core` merely to reduce package count.

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

## Physical rename timing

Record the `maistro-registry` -> `maistro-arch-governance` decision now. Perform the physical package/import/CLI rename in the convergence branch before architecture fitness rules start depending on package names, but keep it as a mechanically isolated commit so compatibility issues are easy to identify.

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
