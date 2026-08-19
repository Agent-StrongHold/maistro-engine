# Stream 7 Product Adapter Audit

Status: pre-migration audit and behavior-locking work only. This document does not redefine canonical objects, state machines, persistence, permissions, or Binding/Invocation contracts.

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

Stream 7 needs stable Project/Workspace ownership, Graph/Node identity, Run/NodeRun/Attempt lifecycle and persistence, reconciliation/terminalization, and the real Attempt -> ExecutionRuntime entry point available from its base branch.

Product migration code must not copy or shadow those contracts locally.

### Stream 2: Event + Checkpoint

Required before product producer migration:

- canonical Event envelope/correlation;
- sequence/store semantics;
- canonical Checkpoint/resume references;
- producer-facing persistence/outbox contract.

### Stream 3: authorization/resources

Required before migrated product entry points become canonical production entry points:

- repository-backed membership/project ancestry integration;
- project/workspace resource visibility;
- Binding/credential/policy scope resolution;
- Invocation enforcement seam.

Persona remains product taste/style/purpose, not an authorization actor.

### Stream 4: reachability audit

Continuous evidence input, not a hard merge gate.

### Stream 5: Graph + durable convergence

Required for product paths using graph traversal, pause/resume, fan-out/fan-in, conditional routing, durable recovery, or HITL. Product adapters must not choose among competing graph runtimes themselves.

### Stream 6: Capability execution

Required for product adapters invoking tools, models, providers, sandboxes, MCP/HTTP, harnesses, or delegated agents. Stream 7 must not invent interim Binding/Invocation APIs.

## Merge/base strategy

Implementation should normally consume canonical contracts after they merge to `develop`. A stacked integration branch is technically possible but is not the default because Stream 7 spans the widest package surface and would otherwise multiply upstream churn into product-package conflicts.

Audit and characterization work can proceed safely against current `develop` because it changes no canonical interfaces.

## Product-by-product audit

### Builders (`maistro.builders`)

Current duplicate universal lifecycle concepts include package-local Run status/request/result, StageEvent, ArtifactRef, RunState, retries, runtime-version state, BuildersRuntime, and private graph/orchestrator/pipeline execution ownership.

Behavior to preserve:

- Frank/Mason/Auditor role semantics;
- stage ordering and gates;
- prompts/prompt versions;
- stage-specific tools;
- claim/spec/audit behavior;
- artifacts and stage outputs;
- revision loops;
- CLI/UI/RSI product surfaces.

Target mapping:

- workflow -> GraphTemplate/Graph;
- worker/stage -> NodeTemplate/Node;
- logical execution -> Run/NodeRun;
- physical retry -> Attempt;
- StageEvent -> canonical Event payload;
- private ArtifactRef -> canonical Artifact reference;
- runtime registration/dispatch -> specialized Node/Binding behavior rather than lifecycle ownership.

Stream 7 coverage now added in `packages/maistro-core/tests/builders/test_migration_parity.py` pins:

- artifact handoff across stages/workers;
- failure terminalization without accidental advance;
- retry preserving the same logical Builders run/stage;
- review -> implementation revision under the same logical workflow.

These characterize product semantics. They do not endorse the private lifecycle as canonical.

### RSI (`maistro-rsi`)

Current private lifecycle ownership includes cycle run IDs/results, sandbox lifetime, autonomous loop execution, wall-clock stopping, HTR snapshots acting as resumability, JSONL execution audit, direct model/provider selection, and direct sandbox/git/test/eval execution.

Behavior to preserve:

- HTR hypothesis/frontier semantics;
- proposer fallback/circuit breaking;
- branch/patch/test experiments;
- quarantine/Warden fail-closed behavior;
- differential probes;
- benchmark/Elo evidence;
- retained learnings;
- repository identity and experiment lineage;
- promotion behavior.

Target mapping:

- cycle -> Graph/Run;
- experiment steps -> Nodes/NodeRuns;
- sandbox/git/model/eval -> Bindings/Invocations;
- physical retry -> Attempt;
- HTR tree -> RSI domain state referenced by canonical Checkpoint/Artifact;
- execution audit -> canonical Event stream plus domain projection if useful;
- autonomous repetition -> Schedule/policy -> Run.

Existing RSI tests already strongly cover migration-sensitive semantics: per-cycle snapshots, atomic writes, resume without seed duplication, explicit fresh start, retained learnings, corruption tolerance, Warden scan on append/recall, circuit breaking, and failed experiments continuing as dead ends. Stream 7 should avoid redundant RSI tests until an adapter seam exists.

### Evolve (`maistro-evolve`)

Preserve populations, mutation/crossover, fitness, tournaments/Elo, benchmark fidelity, candidate promotion/rollback governance, and audit evidence.

Converge private cycle/timer/retry/execution identity onto Graph/Run/NodeRun/Attempt, Schedule, Event, and Binding/Invocation. Do not blindly collapse evolution Genome into Agent Genome; normalize only genuinely shared primitives.

### Canvas (`maistro-canvas`)

Canvas contains legitimate product/domain semantics plus a private generation-job lifecycle.

Behavior to preserve:

- book/canvas/layer state;
- compositor/image assembly;
- generate/refine/reference/composite/text actions;
- layer placement, pose, visibility, masks and regions;
- image generation and export behavior;
- image version history;
- BookLayer retry/upgrade invariants;
- lease recovery semantics needed to recover lost physical work.

Private lifecycle to converge:

- GenerationJobRecord status as universal execution state;
- CanvasJobRunner;
- worker leases;
- job attempt counters;
- bounded retry terminalization;
- direct executor/provider ownership.

Target mapping:

- Canvas workflow -> Graph/Run;
- generation/composition action -> Node/NodeRun;
- physical provider try -> Attempt;
- lease/reaper recovery -> canonical scheduler/recovery mechanics compatible with Attempt ownership;
- provider execution -> Binding/Invocation;
- generated/exported output -> canonical Artifact carrying Canvas domain metadata.

Stream 7 coverage now added in `packages/maistro-canvas/tests/test_migration_parity.py` pins:

1. A transient provider failure retries the same logical generation job. Job/canvas/layer identity, action, model, prompt and generation parameters survive unchanged while only the physical attempt count advances. The successful retry clears the lease and produces the result path.
2. `BookLayer.retry()` and `BookLayer.upgrade()` preserve image history and placement/pose/mask metadata while replacing the active image, with upgrade moving quality to final.

This explicitly supports the eventual mapping: one logical Canvas generation -> one NodeRun, physical retries -> Attempts.

### Turing (`maistro-turing`)

Preserve self-model/autonoetic state, cognition/reactor stages, proactive producer semantics, agent-specific mood/personality/drives, memory extensions, and Turing-specific tools/providers.

Converge actor/chat/cognition execution to Graph/Run/NodeRun, proactive execution to Schedule/Event trigger -> Run, and direct provider/tool execution to Binding/Invocation. Persona-level taste/style/purpose belongs to Persona; agent-specific cognition remains Turing/Genome behavior.

### Hive Conductor

Preserve Mission Control UX, chat/session workflows, project navigation, DAG editing/inspection, scheduling UI, agent/tool/integration surfaces, audit/admin behavior, and useful isolation mechanics.

Converge app-local Workspace/Project collisions, private DAG/run execution, private scheduler execution, direct Agent/tool invocation, synthetic run state, and app-local lifecycle stores onto canonical core services.

### Design (`maistro-design`)

Preserve DesignProject, DesignSystem, DesignSkill, renderer behavior, design-specific trust/review/scanning, catalog/import, and output semantics.

Map RenderSlot -> Capability, renderer -> Provider, consumer configuration -> Binding, render call -> Invocation, execution -> NodeRun/Attempt, and output -> Artifact. DesignEngine remains a domain adapter, not ExecutionRuntime.

### Bootstrap (`maistro-bootstrap`)

Keep in the platform/install plane. It may seed or materialize canonical objects but should not become a product Run lifecycle owner.

### Registry (`maistro-registry`)

Keep ADR/SPEC lifecycle and conformance in the engineering control plane. Product Nodes may invoke it as a capability without folding Registry into the runtime ontology.

## Cross-package duplicate families

1. Run identity/status -> canonical Run/NodeRun/Attempt.
2. Package events/audit logs -> canonical Event plus domain projections where useful.
3. Package artifact references/files -> canonical Artifact ownership/provenance plus domain metadata.
4. Private dispatchers/runtimes -> domain adapters over canonical execution.
5. Timers/autonomous loops -> Schedule/Event trigger -> Run.
6. Direct tool/provider/model/sandbox calls -> Capability/Provider/Binding/Invocation.

## Safe work before upstream merges

- behavior characterization tests;
- old-to-canonical mapping;
- direct-call and reachability inventories;
- package-local identity/status/event/artifact/checkpoint inventory;
- deletion prerequisites;
- compatibility fixtures that can later exercise legacy and canonical paths.

## Work Stream 7 must not do yet

- define another Run/NodeRun/Attempt model;
- define another Event envelope;
- define temporary Binding/Invocation contracts;
- choose a winner between graph runtimes;
- migrate checkpoint/resume ahead of Stream 2/5;
- bypass authorization to make a migrated path reachable;
- delete legacy behavior before parity and data migration are established.

## Recommended migration order

1. Builders adapter.
2. RSI adapter preserving HTR/evaluation/quarantine domain behavior.
3. Evolve scheduled-run conversion.
4. Canvas execution adapter preserving Canvas domain/UI/recovery behavior.
5. Turing execution/producer adapter.
6. Design provider/binding adapter.
7. Hive shell convergence after underlying canonical services exist.
8. Bootstrap/Registry only for narrow integration changes.

## Ready-to-code gate

Product implementation begins when the shared base exposes stable, tested canonical Workspace/Project scope, Graph/Node, Run/NodeRun/Attempt + reconciliation/store, Attempt -> ExecutionRuntime, Event, Checkpoint where required, authorization resource scopes, Binding/Invocation, and graph/durable convergence for graph-dependent products.
