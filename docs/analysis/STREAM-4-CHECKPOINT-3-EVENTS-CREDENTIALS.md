# Stream 4 Checkpoint 3: Events, Credentials, and Binding Islands

Date: 2026-08-14
Source audited: `develop`

This checkpoint records migration constraints for Stream 2 (events/checkpoints) and Streams 3/6 (authorization, credentials, capability execution).

## 1. The existing event subsystem has strong delivery machinery but a non-canonical envelope

`maistro.events.bus.Event` currently carries:

- `event_id`
- category
- `event_type`
- source
- payload
- timestamp
- one `correlation_id`

The durable log is a separate persisted shape with:

- monotonically increasing integer `id`
- `event_type`
- `entity_type`
- `entity_id`
- payload
- source
- created_at

`append_from_bus_event()` currently maps:

- bus category -> durable `entity_type`
- bus `correlation_id` -> durable `entity_id`

and the durable store assigns a different integer row ID.

That mapping does not preserve a rich execution identity spine. It cannot directly encode canonical Workspace/Project/Graph/Run/NodeRun/Attempt relationships without overloading payload or the generic entity fields.

Classification: existing envelope = `migration source`, not canonical Event.

## 2. Event delivery semantics are valuable and should be preserved

The existing durable processing path already implements several semantics Stream 2 needs:

- append-only durable ordering
- monotonically increasing sequence/cursor
- replay after restart
- at-least-once processing
- idempotent trigger invocation keyed by `(trigger_id, event_id)`
- bounded retry attempts
- terminal success/failure state for handler invocations
- explicit `handler.failed` events after retry exhaustion

These mechanics are more mature than the current event identity model.

### Stream 2 handoff

Preserve the delivery machinery while replacing the envelope/correlation model with canonical identifiers and provenance. Do not rebuild retries/replay/idempotency from scratch merely because the Event DTO changes.

Likely migration direction:

- canonical Event sequence should preserve the durable monotonic ordering property
- event identity should remain distinct from persistence row/sequence identity
- run/node/attempt/project correlation should be explicit fields or canonical references, not overloaded into one `correlation_id`
- old EventBus category/entity mappings should become projections/compatibility fields where still useful

## 3. Private event islands should converge onto canonical Event rather than survive alongside it

Already identified elsewhere in this audit:

- `GraphRun` has its own `GraphEvent` callback mechanism
- Hive's unreachable deployment Project API publishes a private Redis/SSE envelope
- Task progress uses queue notifications / polling and optional progress webhooks
- Hive DAG-run product surfaces have their own event bridge

These are all evidence that event production already exists in several domains. Stream 2 should provide the common persistence/correlation substrate rather than forcing product code to keep inventing parallel envelopes.

Classification: `merge producers onto canonical Event`.

## 4. Active Hive credential API uses the core UserCredentialStore

Mounted Hive `routes/credentials.py` imports `services.user_credentials`, which wraps `maistro.credentials.UserCredentialStore`.

The active API:

- derives user identity from authenticated request state
- lists configured providers for that user
- writes secrets by `(user_id, provider_id)`
- deletes secrets by `(user_id, provider_id)`
- never returns stored secret values through list responses
- stores non-secret provider config separately under a user/provider key

This is the credential path to preserve and migrate, not `credential_store_v2.py` by default.

Classification: `live`.

## 5. `credential_store_v2.py` is a separate duplicate credential implementation

`packages/hive-conductor/backend/services/credential_store_v2.py` implements a PostgREST/Fernet store with credential IDs, user IDs, types, names, metadata, and encrypted secrets.

Its read/write methods after creation are primarily keyed by credential ID:

- `get(cred_id)`
- `get_secret(cred_id)`
- `update(cred_id, ...)`
- `delete(cred_id)`

Those operations do not themselves require a user scope parameter.

The active Hive credential routes do not import this service; they use `UserCredentialStore` through `services.user_credentials`.

### Classification

`credential_store_v2.py`: `duplicate / candidate after caller audit`.

Do not make it the basis of canonical credential scope merely because it is PostgreSQL-backed.

## 6. Core UserCredentialStore contains security behavior worth preserving

`maistro.credentials.store.UserCredentialStore` provides:

- Fernet encryption at rest
- deployment master-key handling
- atomic writes
- interrupted rotation repair
- master-key rotation
- per-user storage
- server-side secret use rather than returning values to clients

This is substantive security behavior and should survive migration.

Classification: `preserve mechanics; migrate scope model`.

## 7. Existing credential `workspace_id` scope uses the legacy Persona-Workspace noun

The core credential store already supports a key shape documented as:

`(user_id, provider, workspace_id, connection_name)`

The comment identifies this as part of the existing Persona/Workspace system. In current Hive vocabulary, Workspace is the adopted-Persona tab object, not the convergence program's canonical ownership root.

Therefore the field name cannot be assumed to already satisfy canonical resource scope.

### Streams 3/6 handoff

Credential resolution needs an explicit migration decision:

- what scope is owned by canonical Workspace
- what scope is owned by Project
- whether a connection belongs to Project, Workspace, or a resource subtree
- how user-owned credentials can be granted to a Project without duplicating secret material
- what Binding references at invocation time

Do not infer authorization from the current legacy `workspace_id` key.

## 8. Provider credential pools are a different concept from user credential ownership

`maistro.credentials.types.CredentialRecord` describes provider/API-key pool mechanics:

- key ID
- provider
- raw API key
- priority
- cooldown/block state
- usage/error counters
- selection strategies such as fill-first, round-robin, random, least-used

It has no user/project/workspace ownership fields.

This looks like runtime provider-fallback / key-pool behavior rather than project resource authorization.

### Stream 6 handoff

Preserve pool selection, cooldown, health, and fallback behavior as provider runtime mechanics, but do not treat pool membership as a grant of Project access.

Classification: `runtime provider mechanic`.

## 9. Hive AgentToolBinding is configuration, not canonical Binding

`services/tool_binding.py` resolves a tool list and prompt fragment for one materialized Persona agent in one legacy Hive Workspace.

Resolution order is:

1. sticky workspace override for the agent
2. Persona template `spawns[].tools`
3. empty list

The module explicitly notes that this was built ahead of full dispatch wiring.

This object does not identify a Capability provider, credential, authorization grant, project resource, attempt, or Invocation.

### Stream 6 handoff

Treat current `AgentToolBinding` as product configuration input that can help construct canonical Binding/ToolExposure state. Do not rename it to canonical Binding and preserve its current semantics wholesale.

### Stream 3 invariant

An empty or narrowed tool list is an availability/configuration choice, not a permission algorithm. Persona remains outside authorization resolution.

## Current replacement candidates

### Strong candidate after caller verification

- `hive-conductor/backend/services/credential_store_v2.py`

Reason: duplicate credential persistence path; active mounted credentials API uses core UserCredentialStore instead.

### Keep and migrate

- `maistro.credentials.UserCredentialStore` security/rotation mechanics
- credential provider catalog
- provider pool fallback/cooldown mechanics
- event durable-log sequencing/replay/idempotency machinery

### Replace / project

- EventBus single `correlation_id` as the execution correlation model
- durable log's category -> entity-type and correlation -> entity-id mapping
- Graph/private Redis/task callback event envelopes once canonical Event is wired
- legacy Persona Workspace `workspace_id` as credential resource scope
- Hive `AgentToolBinding` as the universal Binding abstraction

## Next audit slices

1. Builders private graph/runtime reachability
2. delegation/harness execution duplicates
3. security/policy/privilege overlap beyond credentials
4. historical zero-importer and closed-island findings against current `develop`
