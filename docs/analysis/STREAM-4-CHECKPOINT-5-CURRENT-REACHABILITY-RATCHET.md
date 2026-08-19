# Stream 4 Checkpoint 5: Current Reachability Ratchet Revalidation

Date: 2026-08-14
Source audited: `develop`
Evidence source: `quality/reachability-baseline.json`

This checkpoint revalidates historical #357/#363 reachability findings against the current CI ratchet rather than carrying old verdicts forward unchanged.

## Method

The current reachability baseline is generated from process entry points and ratcheted in CI. A module remaining in the baseline has no import path from a process entry point under the checker.

This is strong evidence of structural unreachability, but not proof that a module is useless: maistro-core is also a library. Conversely, absence from the baseline only proves structural reachability, not that every advertised behavior is exercised.

Those limits are important. Stream 4 uses the baseline to classify candidates, then separately traces behavioral call paths where architecture decisions depend on them.

## 1. Builders remains structurally unreachable on current develop

The current baseline still includes the entire Builders subsystem, including:

- `maistro.builders`
- contracts
- dag
- graph
- graph_executor
- logger
- orchestrator
- pipeline
- runtime
- services
- spec coverage/emitter/templates
- verifier

Therefore the Builders behavior inventoried in Checkpoint 4 is currently **library/island behavior**, not production process behavior.

### Consequence

Stream 7 should treat Builders migration as a deliberate product-adapter activation, not as preserving an already-live runtime path.

Its gate/revision/artifact semantics are valuable source behavior, but canonical Graph/Run integration is also the act that will make the subsystem truly reachable.

Classification: `unreachable behavior source -> migrate/wire selectively`.

## 2. Legacy `maistro.projects` is not on the unreachable baseline

The current baseline does not list `maistro.projects` or its model/store modules.

That materially strengthens the earlier conclusion: the core legacy Project implementation is not a dead island. It has a rooted production path and must be handled as live compatibility/persistence surface.

Do not delete or rename it solely because Hive also has a different `Project` noun.

Classification: `live compatibility surface`.

## 3. Hive deployment Project island remains unreachable, including supporting services

The current baseline includes:

- `routes.projects`
- `services.onboard_db`
- `services.pipeline_orchestrator`
- `services.repo_scanner`

This confirms Checkpoint 1's manual entrypoint trace and extends it: the repository onboarding / scan / deploy route is not merely unmounted; its primary backing services are also unrooted.

### Stream 7 decision

This is now a strong delete-or-revive decision boundary:

- if repository onboarding/deployment is a desired product capability, explicitly migrate/wire it under a correctly named product domain concept;
- otherwise the whole island can become a deletion candidate after data/schema/operator dependency checks.

Classification: `closed unreachable product island`.

## 4. Duplicate Hive credential_store_v2 remains unreachable

`services.credential_store_v2` is still in the current baseline.

The mounted credential routes use core `UserCredentialStore`, as documented in Checkpoint 3.

This strengthens its deletion classification.

Remaining prerequisite before deletion: verify no external deployment/migration/operator script imports the module outside the checker roots and verify whether the `hive_credentials_v2` table contains data that requires migration/retention.

Classification: `strong delete-after-data-audit candidate`.

## 5. Hive tool_binding remains unreachable

`services.tool_binding` remains in the baseline.

So the sticky Persona-workspace AgentToolBinding resolver is not currently part of a production dispatch path, matching the module's own statement that it was built ahead of dispatch wiring.

### Stream 6 / 7 consequence

Do not wire this legacy resolver just to make the old abstraction live. Use its desired override semantics as input while implementing canonical Binding/Invocation and product projections.

Classification: `unreachable behavior source -> supersede during migration`.

## 6. Core scheduling remains unreachable while Hive scheduler is live-but-disconnected

The baseline still includes:

- `maistro.scheduling`
- `maistro.scheduling.store`

Checkpoint 2 separately proved Hive's own `services.scheduler` is started by lifespan but does not launch a Mission/Task/Run when schedules fire.

Therefore the current system has both failure modes simultaneously:

- a richer core schedule store that is structurally unreachable
- a reachable Hive scheduler whose execution edge is behaviorally disconnected

This is a clean convergence opportunity, not two systems to preserve.

Target remains: one canonical Schedule -> Run handoff.

Classification: `merge + wire`.

## 7. Durable graph execution is still structurally unreachable

The current baseline includes:

- `maistro.graph.durable_runs`
- executor
- protocol
- stores
- types

This is particularly important because those modules contain the strongest pause/resume/checkpoint behavior found in the repo, but they are not currently rooted in a production process path according to the ratchet.

### Stream 5 consequence

Durable execution should be treated as tested architecture source code that still needs real canonical wiring, not as an already-live production execution spine.

The GraphRun vs durable parity work is therefore also a reachability activation task.

Classification: `unreachable architecture source -> merge/wire into canonical spine`.

## 8. Some graph-node capabilities remain unreachable individually

The baseline includes several node modules, including:

- `agent_delegate_remote`
- `agent_synth_dag`
- HITL nodes
- Jira/Airtable waits
- compliance block
- transforms
- summarization

Not every node is listed. This means the catalog/import topology has become partially rooted, but specific node implementations still lack a process-entry path under the checker.

Do not infer that “graph nodes are live” as a class. Stream 5/6/7 should verify the exact nodes needed by migrated products and remove or wire intentionally.

## 9. Historical credential pool finding remains current

The baseline still includes:

- `maistro.credentials.pool`
- `maistro.credentials.rotation`
- `maistro.credentials.types`
- credential protocols

This matches #363's warning that credential pool/rotation was not the same path as the working UserCredentialStore master-key rotation.

### Stream 6 consequence

Provider-key pooling/fallback is useful behavior source, but wiring it must happen as part of Provider/Invocation convergence. Do not describe it as currently active provider fallback until that path is rooted.

Classification: `unreachable runtime mechanic source`.

## 10. Historical closed-island systems remain present

Current baseline still includes examples from #357/#363 such as:

- delivery
- code_registry
- collaboration
- integrations
- ontology
- orchestrator waves
- portability
- repertoire
- sandbox
- session search
- approval gates
- reversibility
- shadow git
- governance conformance
- episodic ranking/retrieval
- task recovery/replay

The ratchet is doing its job: these islands have not silently become reachable without shrinking the baseline.

However, the convergence program should not bulk-delete them merely because they are unreachable. Several contain behavior that maps directly to active streams.

## 11. Product packages with currently unreachable execution modules

The current baseline also flags product-specific modules relevant to Stream 7, including:

### Canvas

- asset compositor/executor/routes/store/tool
- canvas runner/store/tool

### Evolve

- architecture_fit
- executable_terminal_runner
- providers, including codex_cli/openai_compatible
- serialization pieces

### RSI

- apply_agents
- autorun
- harness_adapter
- rate_pacer

### Turing

- memory
- producers
- providers
- schema
- tools

This does not mean the entire products are dead. It means these specific advertised/runtime components have no rooted path and must be checked against the live product entrypoint before migration.

## Priority deletion/migration queue after revalidation

### Strong deletion candidates, subject to data/operator audit

1. Hive deployment Project island if product no longer wanted:
   - `routes.projects`
   - onboard_db
   - repo_scanner
   - pipeline_orchestrator
2. `services.credential_store_v2`
3. legacy tool-binding resolver if canonical Binding supersedes it before it is ever wired

### High-value unreachable behavior sources to migrate, not delete blindly

1. durable graph pause/resume/checkpoint
2. Builders gate/revision/artifact semantics
3. credential pool fallback/cooldown mechanics
4. task recovery/replay semantics
5. selected approval/reversibility/security controls
6. product-specific RSI/Evolve/Canvas execution behavior where still desired

## Stream handoffs

### Stream 1

`maistro.projects` is structurally live. Treat migration as compatibility work, not dead-code cleanup.

### Stream 5

Durable runs are still structurally unreachable. Canonical convergence must create the real rooted execution path.

### Stream 6

Credential pool mechanics remain unreachable; integrate intentionally under Provider/Invocation. Legacy Hive credential v2 and tool-binding modules should not be selected merely because code exists.

### Stream 7

Builders remains wholly unreachable and several RSI/Evolve/Canvas/Turing execution modules are individually unreachable. Product migration is partly a reachability activation effort, not just API renaming.

## Next audit slices

1. inspect the flagged RSI/Evolve/Canvas execution modules and identify behavior worth preserving vs obsolete islands
2. inspect task recovery/replay and approval/reversibility islands for canonical Run/Invocation handoffs
3. finish privilege/governance overlap map for Stream 3
