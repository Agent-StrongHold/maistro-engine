# Stream 4: Legacy Project + Reachability Migration Audit

Checkpoint: 2026-08-14

Source branch audited: `develop`

## Purpose

Stream 4 is the continuous migration/reachability lane for the architecture convergence program. It does not own canonical object definitions. It identifies legacy semantics, real callers, unreachable systems, duplicate abstractions, migration ownership, and deletion prerequisites so the canonical streams do not rediscover these facts while implementing.

The governing rule for this stream is:

> Preserve useful behavior. Stop preserving accidental ownership, duplicate lifecycle models, and misleading reachability.

## Checkpoint 1 findings

### 1. `maistro.projects.Project` is a composite legacy object, not a simple rename candidate

Current owner:

`packages/maistro-core/src/maistro/projects/`

The current Project model combines several concerns that should not be migrated as one indivisible object:

- membership and role assignment
- descriptive/product-purpose fields (`name`, `description`, `use_case`, tags)
- external resource references
- graph/DAG references (`meta_dag_id`, `agent_dag_ids`)
- optimizer/evaluation settings
- enabled skill and MCP-server defaults
- metadata and timestamps

The model explicitly documents `enabled_skills` and `enabled_mcp_servers` as product defaults rather than security boundaries. This distinction must survive migration. They must not become authorization grants merely because they are currently stored on Project.

The Project store is real persistence, not a throwaway DTO. It owns persisted project records plus membership and quota-related behavior. Do not delete it before canonical ownership/scoping migration has a compatibility path.

#### Handoffs

| Existing Project concern | Migration owner | Direction |
|---|---|---|
| members / roles / visibility | Stream 3 | Move into canonical Workspace/Project membership + authorization semantics |
| resource references | Streams 1 + 6 | Rebind to canonical resource ownership and Capability/Binding model where applicable |
| `enabled_skills`, `enabled_mcp_servers` | Streams 6 + 7 | Treat as availability/product defaults, not authorization |
| `use_case` | Stream 7 | Product/surface intent; evaluate against Persona/surface model |
| `meta_dag_id`, `agent_dag_ids` | Streams 1 + 5 + 7 | Preserve provenance/composition behavior while converging onto Graph/Node |
| optimizer/evaluation settings | Streams 5 + 7 | Classify by domain owner before migration; do not copy wholesale into canonical Project |
| persistence/membership compatibility | Streams 1 + 3 | Must precede deletion of legacy Project store |

### 2. There are at least two unrelated `Project` concepts

Hive Conductor contains:

`packages/hive-conductor/backend/routes/projects.py`

This `Project` is not the same semantic object as `maistro.projects.Project`. It represents repository onboarding and deployment:

- repository URL + branch + Dockerfile
- scan lifecycle
- build/deploy lifecycle
- Launch deployment data
- project-specific Redis/SSE events

Its lifecycle includes states such as `created`, `scanning`, `scan_passed`, `building`, `live`, and failure variants. Those are application/deployment states, not canonical Project or Run states.

**Migration direction:** do not map this object directly onto canonical Project. Treat it as an application/source/deployment domain concept and either rename it or expose it as a projection owned by the product-adapter stream.

### 3. Hive's deployment `projects.py` route is currently unreachable from the production FastAPI entry point

`packages/hive-conductor/backend/main.py` mounts the active Hive route families explicitly and mounts several optional feature slices through `_include_optional_router`.

It does not import or mount `routes.projects`.

Therefore the current classification of Hive's deployment Project API is:

**implemented, but unreachable from the production Hive entry point**

This makes the route module a migration/deletion candidate, but not yet a deletion approval. Its `onboard_db`, scanner, pipeline-orchestrator, and deployment behavior still require caller/reference checks before removal.

#### Handoff

- Stream 7 decides whether repository onboarding/deployment remains a supported product feature and, if so, what canonical product concept exposes it.
- Stream 2 should not inherit the route's private Redis event envelope. If the feature survives, its events should project into the canonical Event contract.
- Stream 4 continues tracing the underlying services before declaring them dead.

### 4. Current Hive `Workspace` conflicts with the canonical ownership-root noun

Hive currently defines:

`packages/hive-conductor/backend/models/workspace.py`

Its Workspace is a thin instance of a `PersonaTemplate` that behaves like a user-visible tab. It stores:

- `persona_template_id`
- members
- accepted capability checklist
- per-agent tool-binding overrides
- theme
- voice override
- active flag

This is useful product behavior, but it does not match the convergence program's canonical durable ownership-root Workspace semantics.

**Do not broaden this existing class into the canonical Workspace by accident.** Preserve the user-facing behavior while separating the product/surface/adopted-persona projection from the ownership root.

#### Handoff

- Stream 1 owns the canonical Workspace noun and durable ownership semantics.
- Stream 3 owns membership/authorization semantics.
- Stream 7 owns the existing Hive tab/adopted-persona UX and its migration.
- Stream 6 owns eventual tool/binding semantics now embedded as per-workspace overrides.

### 5. Current `PersonaTemplate` is also a composite migration source, not the canonical Persona object

`packages/maistro-core/src/maistro/personas/schema.py` supports template kinds `department`, `author`, `creator`, and `workspace`.

The `workspace` kind currently combines:

- voice
- evaluation rubrics
- spawned agent declarations
- brand
- UI scope
- onboarding interview script

This is valuable existing behavior and vocabulary, but it should not be treated as evidence that the new durable Persona object is already implemented.

#### Handoff

- Stream 7 preserves product voice/brand/UI/onboarding behavior.
- Streams 1/7 classify spawned agents into canonical templates/graphs/nodes.
- Evaluation rubric semantics should remain domain behavior rather than becoming universal Persona lifecycle state.

### 6. `maistro-server` currently has no Project or Workspace API surface

The `maistro-server/src/maistro_server/api/` tree exposes agents, auth, canvas, chat completions, health, metrics, models, tasks, webhooks, and websocket-related API modules, but no Project or Workspace route module.

For this checkpoint, the conflicting externally exposed ownership/product nouns are concentrated in Hive, while the older persistent Project domain lives in `maistro-core`.

## Current deletion classifications

### Do not delete yet

- `maistro.projects` model/store: real persisted semantics and compatibility surface
- Hive Workspace model/routes: live product semantics need migration even though the noun is wrong for the canonical ownership root
- Persona template schema: live reusable product behavior needs decomposition/preservation

### Candidate after caller audit

- `hive-conductor/backend/routes/projects.py`: not mounted by Hive production entry point
- its private project Redis/SSE envelope: replace if feature survives canonical-event migration
- duplicate deployment-specific `Project` naming: rename/remove once product ownership is decided

## Reachability methodology

A module is not considered live merely because it exists, has tests, or has an ADR/spec. A production reachability claim requires at least one real entry point or a verified production importer/caller.

Likewise, lack of GitHub code-search results is not sufficient evidence of dead code. This audit uses branch-pinned tree/file inspection and entry-point tracing because repository search indexing is incomplete for this repo.

For every candidate island:

1. identify definition and persistence owner
2. identify production entry points
3. trace direct callers/importers
4. identify tests that encode behavior worth preserving
5. classify canonical owner
6. mark `keep`, `split`, `merge`, `compatibility`, or `delete-after`
7. name the migration/deletion prerequisite

## Next audit slices

The next Stream 4 slices, in order, are:

1. `maistro.projects` store/domain callers and tests
2. Hive Workspace routes/store and their real UI/service callers
3. GraphRun vs durable graph execution behavior inventory for Stream 5
4. Task/queue/runner/recovery lifecycle duplication
5. Event/correlation islands for Stream 2
6. credential/security/tool-binding islands for Streams 3 and 6
7. Builders private graph/runtime reachability for Stream 7
8. delegation and harness execution duplicates
9. previously identified zero-importer/closed-island packages from reachability issues

## Stream rule

No canonical object model, lifecycle state machine, permission algorithm, Binding/Invocation contract, or persistence schema is defined by this audit branch. Stream 4 supplies evidence and migration constraints to the streams that own those choke points.
