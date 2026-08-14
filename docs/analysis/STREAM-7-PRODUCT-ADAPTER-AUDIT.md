# Stream 7 Product Adapter Audit

Status: pre-migration audit only. This document does not redefine canonical objects, state machines, persistence, permissions, or Binding/Invocation contracts.

Baseline: `develop` at `ea6f0850323eedc7ff4c421cbf92d2617b347dbb`.

## Purpose

Stream 7 owns migration of product/application packages after the canonical execution spine is consumable. Its rule is:

> Preserve specialized domain behavior. Replace specialized universal lifecycle behavior.

The immediate job while upstream streams are still converging is therefore to identify, package by package:

1. domain behavior that must survive;
2. duplicate universal lifecycle behavior that must move onto canonical Workspace/Project, Graph/Node, Run/NodeRun/Attempt, Event/Checkpoint, and Binding/Invocation contracts;
3. entry points and persistence that require adapters;
4. upstream contracts that block implementation;
5. behavior-parity tests required before old paths are removed.

## Upstream gates for Stream 7

### Stream 1: canonical domain spine

Stream 7 needs the following stable and available from its base branch:

- Project/Workspace ownership and project scope/tree semantics;
- Graph/Node identity and template provenance;
- Run/NodeRun/Attempt lifecycle and persistence;
- Run reconciliation after Attempt completion/failure/cancellation/timeout;
- the real Attempt -> ExecutionRuntime entry point.

The open convergence PR currently contains these canonical model/spec files, but they are not yet on `develop`. Product migration code should not copy or shadow them locally.

### Stream 2: Event + Checkpoint

Required before product producer migration:

- canonical Event envelope and correlation IDs;
- stable sequencing/store semantics;
- canonical Checkpoint/resume references;
- producer-facing append contract.

The first Event slice can be consumed once merged, but Stream 7 should not migrate package-specific checkpoint/recovery behavior until the checkpoint contract lands.

### Stream 3: authorization/resources

Required before product entry points become canonical production entry points:

- repository-backed membership/project ancestry integration;
- project/workspace resource visibility;
- Binding/credential/policy scope resolution;
- Invocation enforcement seam.

Product adapters may be structurally migrated before final enforcement, but they must not bypass authorization to become reachable.

### Stream 4: reachability audit

Continuous input, not a hard merge gate. Stream 7 should consume its findings as preservation/deletion evidence.

### Stream 5: Graph + durable convergence

Required for product adapters that rely on graph traversal, pause/resume, fan-out/fan-in, conditional routing, durable recovery, or HITL. In particular, Builders, RSI, Evolve, Canvas pipelines, and portions of Hive must not choose between old GraphRun and durable execution themselves.

### Stream 6: Capability execution

Required for product adapters that invoke tools, models, providers, sandboxes, MCP/HTTP, harnesses, or delegated agents through canonical execution. Stream 6 currently has an audit branch but no implementation delta from `develop`, so Stream 7 must not invent interim Binding/Invocation APIs.

## Merge/base strategy

For implementation, upstream canonical-contract work should normally merge back to `develop` before Stream 7 begins consuming it.

A temporary stacked/integration branch is technically possible, but it would couple product migrations to unstable branch SHAs and create unnecessary conflict churn across the widest package surface in the repo. Stream 7 is intentionally a consumer stream, so its implementation branches should be cut from a `develop` that already contains the contracts they consume.

Audit-only work can proceed safely from current `develop` because it changes no canonical interfaces.

## Product-by-product audit

### Builders (`maistro.builders`)

Current package evidence shows Builders owns its own contracts, graph representation/executor, orchestrator, pipeline, logger and runtime dispatcher.

Current duplicate universal lifecycle concepts include:

- `RunStatus` with queued/running/passed/failed/blocked;
- `RunRequest` carrying its own `run_id` and workspace reference;
- `RunResult` carrying terminal workflow status;
- `StageEvent` as a package-specific durable event;
- `ArtifactRef` as a package-specific artifact reference;
- `BuildersRuntime.execute()` as a stage-dispatch execution boundary;
- Builders graph/orchestrator/pipeline execution paths.

Behavior to preserve:

- Frank/Mason/Auditor roles and stage-specific behavior;
- prompts and prompt versions;
- stage-specific allowed-tool configuration;
- spec/claim/audit behavior;
- Builders workflow semantics and UX/CLI/RSI surfaces;
- specialized artifact types and stage outputs.

Target mapping:

- Builders workflow -> GraphTemplate/Graph;
- worker/stage -> NodeTemplate/Node;
- `RunRequest` -> adapter/projection over canonical Run + NodeRun inputs;
- `RunResult` -> NodeRun result/output projection;
- `StageEvent` -> canonical Event payload;
- Builders `ArtifactRef` -> canonical Artifact reference;
- `BuildersRuntime` registration/dispatch -> NodeType/Binding registry behavior, not lifecycle owner;
- Builders CLI/UI/RSI -> Persona-exposed surfaces over the same canonical objects.

Parity tests required before removal:

- stage ordering and dependency behavior;
- unsupported worker/stage failure semantics;
- prompt version resolution;
- allowed-tool resolution per worker/stage;
- claim/spec validation behavior;
- artifact production and provenance;
- failure/blocking behavior;
- CLI/UI/RSI producing equivalent workflow outcomes.

### RSI (`maistro-rsi`)

RSI already composes many useful subsystems rather than rebuilding them, but it still owns a private execution lifecycle.

Current lifecycle ownership observed in `RsiCycle` / autorun:

- generates its own `run_id`;
- creates and destroys per-cycle workspaces/sandboxes;
- performs branch -> patch -> test -> evaluate -> tournament inside one private cycle;
- owns terminal `RsiCycleResult`;
- owns an autonomous multi-cycle loop with wall-clock stopping;
- owns resumability through an HTR tree snapshot;
- owns append-only audit JSONL and learnings JSONL;
- directly discovers/selects models and constructs gateway calls;
- directly executes sandbox/git/test/eval operations;
- directly loops over cycles rather than receiving Schedule/Run triggers.

Behavior to preserve:

- hypothesis tree and frontier selection;
- proposer/fallback/circuit-open behavior;
- branch/patch/test experiment semantics;
- quarantine/Warden gating before PR escape;
- differential workspace probes;
- benchmark evaluation and Elo comparison;
- best-candidate/improvement semantics;
- retained learnings and tree-domain state;
- quota-aware model-selection policy where still useful;
- PR promotion behavior.

Target mapping:

- one RSI experiment/cycle -> Graph/Run;
- hypothesis/branch/patch/test/evaluate/battle -> Nodes/NodeRuns;
- sandbox/git/model/eval calls -> Bindings/Invocations;
- physical retries -> Attempts;
- HTR tree -> RSI domain artifact/state, not Run lifecycle;
- tree snapshot -> domain artifact/checkpoint payload referenced by canonical Checkpoint where resumability requires it;
- audit log -> canonical Events plus retained RSI-specific audit projection if useful;
- learnings ledger -> canonical Memory/artifact service projection;
- autonomous repetition -> Schedule/policy -> Run, or an explicit controller Graph, not a private timer/execution universe.

Parity tests required:

- failed patch becomes a pruned experiment, not whole-program failure;
- quarantine remains fail-closed;
- proposer circuit-breaker behavior;
- tree resume across process restart;
- retained-learning recall and Warden filtering;
- differential benchmark/tournament winner semantics;
- cleanup of sandbox/workspace resources;
- open-PR gating and provenance.

### Evolve (`maistro-evolve`)

Preserve as a domain optimization/evolution subsystem, not an execution root.

Behavior to preserve:

- genome/population representations;
- mutation/crossover;
- fitness/evaluation semantics;
- tournaments/Elo;
- benchmark harnesses and real/proxy fidelity distinctions;
- promotion/rollback governance;
- audit evidence around candidate selection.

Lifecycle to replace where present:

- private evolution-cycle execution;
- private periodic/timer loops;
- package-owned retries/cancellation where equivalent to Attempt mechanics;
- package-specific run/event identity.

Target mapping:

- evolution cycle -> Graph/Run;
- candidate evaluations -> evaluation Nodes/NodeRuns;
- model/tool/benchmark fulfillment -> Bindings/Invocations;
- periodic evolve -> Schedule -> Run;
- candidate outputs -> NodeTemplate/GraphTemplate candidates plus domain evidence/artifacts;
- promotion/rollback remains template/version governance, not Run rollback.

Parity tests:

- deterministic mutation/crossover invariants;
- fitness scoring and tournament outcome equivalence;
- benchmark fidelity guarantees;
- promotion threshold and rollback rules;
- scheduled repetition produces the same candidate/evidence sequence as the old loop.

### Canvas (`maistro-canvas`)

Canvas must not be flattened into generic core. It contains a real book/canvas product plus reusable image/composition mechanics.

Behavior to preserve:

- book-building domain state and UX;
- canvas/compositor behavior;
- RGBA/image assembly;
- image-generation integration;
- export behavior;
- human review/edit flow;
- application-specific persistence where it represents book-domain state.

Target mapping:

- book maker -> Persona/product surface;
- book pipeline -> GraphTemplate/Graph;
- agent/image/compositor/review/export stages -> specialized Nodes;
- image/model/tool calls -> Bindings/Invocations;
- generated images/files/exports -> canonical Artifacts with Canvas/book metadata;
- execution history -> canonical Run/NodeRun/Attempt;
- Canvas domain documents remain Canvas domain objects.

Parity tests:

- page/scene ordering;
- compositor output equivalence;
- image-generation request/response behavior;
- review/edit persistence;
- export reproducibility;
- existing frontend/API book workflow remains usable while execution moves underneath it.

### Turing (`maistro-turing`)

The package contains bridge/runtime modules, cognition/reactor behavior, producers, self-model types, providers/tools, and memory extensions. This is a domain/cognition extension, not a second universal runtime.

Behavior to preserve:

- self-model and autonoetic domain state;
- cognition/reactor stages;
- proactive producer semantics;
- mood/personality/drives where agent-specific;
- Turing memory extensions;
- Turing-specific tools/providers.

Target mapping:

- Workspace purpose/taste/style portions -> Persona where applicable;
- agent-specific cognition/personality -> Agent/Genome/Node definition;
- actor/chat/cognition execution -> Graph/Run/NodeRuns;
- proactive producers -> Schedule/Event trigger -> Run;
- providers/tools -> Capability/Provider/Binding/Invocation;
- memory -> canonical memory scopes with Turing-specific payload/schema.

Parity tests:

- cognition stage ordering;
- self-model state transitions;
- producer trigger behavior;
- memory recall/update semantics;
- actor/chat observable behavior.

### Hive Conductor

Hive is the broadest adapter surface and should migrate late enough that canonical services are real, not mocked by another local store.

Behavior to preserve:

- Mission Control UX;
- chat/session workflows;
- workspace/persona presentation;
- DAG editing/inspection;
- scheduling UI;
- agent/tool/integration surfaces;
- security/admin/audit surfaces;
- files/container/settings product behavior.

Lifecycle/ownership to replace:

- app-local workspace/project models that conflict with canonical ownership-root Workspace/Project semantics;
- app-local DAG/run execution semantics;
- app-local scheduler execution paths;
- app-local agent dispatch that bypasses canonical Binding/Invocation;
- app-local execution/event identities where canonical IDs now exist.

Target mapping:

- Hive routes/services become application adapters over canonical core services;
- Workspace/Persona UI reads/writes canonical ownership objects;
- DAG UI edits canonical Graph/Node objects;
- launch actions create canonical Runs;
- live inspection consumes canonical Events/NodeRuns/Attempts;
- tool/integration invocation resolves canonical Bindings;
- schedules create Runs rather than execute workloads directly.

Parity tests:

- existing major user flows end-to-end;
- workspace/persona isolation;
- DAG create/edit/activate/run;
- chat/session continuity;
- schedule creation/trigger behavior;
- agent invocation;
- tool/integration invocation;
- live and historical run inspection;
- security/elevation behavior at production entry points.

### Design (`maistro-design`)

Preserve as a specialized design domain and provider ecosystem.

Behavior to preserve:

- DesignProject domain state;
- DesignSkill and DesignSystem assets;
- renderer discovery/registry;
- HTML/SVG/typography rendering;
- trust/review/scanning specific to design assets;
- catalog/import/bundle behavior.

Target mapping:

- DesignProject -> Workspace-owned domain object/artifact set;
- DesignSkill -> NodeTemplate and/or Capability asset depending semantics;
- DesignSystem -> Persona/workspace-scoped reusable domain asset;
- RenderSlot -> Capability;
- renderer -> Provider;
- consumer configuration -> Binding;
- render call -> Invocation;
- DesignEngine remains a domain service/adapter, not ExecutionRuntime.

Parity tests:

- renderer selection;
- render output equivalence;
- trust/review rules;
- catalog/import behavior;
- persisted design-project behavior.

### Bootstrap (`maistro-bootstrap`)

Bootstrap is not a normal Stream 7 runtime migration target.

Preserve:

- installation/materialization;
- environment/provider initialization;
- migrations/configuration;
- release/bootstrap behavior.

Rule:

- keep bootstrap in the platform/install plane;
- connect it to canonical registries/default seeding only where needed;
- do not force installation/bootstrap activity into Run unless it is explicitly user work executed by the product runtime.

### Registry (`maistro-registry`)

The ADR/SPEC registry is engineering control-plane infrastructure and should remain outside canonical product execution. It may be used by Builders/RSI as a capability, but it should not itself become a product Run ontology.

## Cross-package duplicate families Stream 7 must eliminate

1. **Run identity/status**
   - Builders `RunStatus` / run IDs;
   - RSI cycle run IDs/results;
   - app/package run concepts.
   - Target: canonical Run/NodeRun/Attempt.

2. **Events/audit logs**
   - Builders `StageEvent`;
   - RSI JSONL audit;
   - package/app-specific progress callbacks.
   - Target: canonical Event envelope, retaining domain payload projections where useful.

3. **Artifacts**
   - Builders `ArtifactRef`;
   - Canvas generated/exported files;
   - RSI snapshots/diffs/evidence;
   - Design render artifacts.
   - Target: canonical Artifact ownership/provenance plus domain metadata.

4. **Execution dispatchers/runtimes**
   - BuildersRuntime;
   - RSI private cycle orchestration;
   - Turing runtime/actor execution;
   - app-local graph/run dispatch.
   - Target: domain adapter -> Graph/Node -> Run/NodeRun/Attempt -> ExecutionRuntime mechanics.

5. **Timers/autonomous loops**
   - RSI autorun/evolve loops;
   - proactive producers where timer-backed.
   - Target: Schedule/Event trigger -> Run, while preserving domain controller state.

6. **Tool/provider execution**
   - direct gateway/model/tool/sandbox/provider calls in product packages.
   - Target: Capability/Provider/Binding/Invocation after Stream 6.

## Safe work Stream 7 can do before upstream merges

- add behavior characterization tests around current product-domain behavior;
- document old-to-canonical mapping;
- identify direct provider/tool/model/sandbox calls that will need Bindings;
- identify package-specific run IDs/status/event/artifact/checkpoint types;
- identify app-local stores that own universal execution state;
- mark deletion candidates but do not delete them;
- define adapter seams/interfaces in tests or analysis without importing unstable canonical types;
- create fixture sets that can later be run against both legacy and canonical paths.

## Work Stream 7 must not do yet

- define another Run/NodeRun/Attempt model;
- define another Event envelope;
- define temporary Binding/Invocation contracts;
- choose a winner between GraphRun and durable execution;
- migrate checkpoint/resume semantics before Stream 2/5 contracts;
- bypass authorization to make a migrated path reachable;
- delete legacy behavior before parity tests exist.

## Recommended migration order inside Stream 7

1. Builders characterization + adapter, because its duplicate lifecycle is explicit and its mapping is clean.
2. RSI characterization + adapter, preserving HTR/evaluation/quarantine as domain behavior.
3. Evolve scheduled-run conversion.
4. Canvas execution adapter while preserving Canvas domain/UI.
5. Turing execution/producer adapter.
6. Design provider/binding adapter.
7. Hive product-shell convergence after the underlying adapters and live Run inspection APIs exist.
8. Bootstrap/Registry only for narrow integration changes, not ontology migration.

## Ready-to-code gate

Stream 7 product migration can start when the branch it is based on exposes stable, tested versions of:

- canonical Workspace/Project scope IDs;
- Graph/Node definitions;
- Run/NodeRun/Attempt lifecycle + reconciliation + stores;
- Attempt -> ExecutionRuntime entry point;
- canonical Event producer/store contract;
- canonical Checkpoint reference contract for resumable products;
- authorization resource-scope adapter;
- Capability/Provider/Binding/Invocation contract;
- Graph/durable parity adapter for products requiring graph traversal/recovery.

Not every product needs every item. Builders can start after Run + Event + Binding + Graph seams stabilize. RSI/Evolve require Run + Event + Binding and scheduler/recovery decisions. Canvas/Turing/Hive should wait for the broader set.
