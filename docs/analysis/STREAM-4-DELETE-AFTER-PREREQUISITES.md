# Stream 4: Delete-After Prerequisites

Date: 2026-08-14
Source audited: `develop`

This document converts the strongest Stream 4 dead-island findings into explicit deletion prerequisites. It does not authorize deletion on the audit branch; owning streams should use these gates before removal.

## Candidate A: Hive repository onboarding/deployment Project island

### Current unreachable code

- `packages/hive-conductor/backend/routes/projects.py`
- `services/onboard_db.py`
- `services/pipeline_orchestrator.py`
- `services/repo_scanner.py`

The current reachability baseline independently lists all four as unreachable.

### Existing data contracts

`onboard_db.py` accesses three PostgREST tables:

- `onboard_projects`
- `onboard_scan_results`
- `onboard_deployments`

`onboard_projects` is soft-deleted via `deleted_at`.

### External integration contracts

`pipeline_orchestrator.py` depends on:

- Tork build/test submission
- callback URL under `/v1/projects/webhooks/tork`
- Launch deployment API
- deployment API key environment variables

Because `routes.projects` is not mounted, the expected Tork callback route is not available through the production Hive app.

### Deletion gate

Before deleting the deployment lifecycle island, verify all of the following:

1. Product decision: repository onboarding/deployment is no longer a supported/desired Hive capability, **or** its replacement product concept has landed.
2. Database audit: determine whether `onboard_projects`, `onboard_scan_results`, or `onboard_deployments` contain retained/user/operator data.
3. Schema decision: archive/export/drop/leave those tables intentionally; do not orphan unknown production data silently.
4. Deployment audit: verify no external Tork job/template still posts to `/v1/projects/webhooks/tork`.
5. Configuration audit: remove or reassign deployment-specific env vars only after confirming no other live feature uses them.
6. Test/docs cleanup: remove or reclassify specs/docs/tests that advertise the unreachable onboarding/deployment flow.
7. Reachability ratchet: deletion should shrink the current baseline entries rather than require an exclusion.

### Scanner carve-out

`repo_scanner.py` is useful independently of the dead deployment lifecycle. It performs static repository scanning with Bandit, Semgrep, and Trivy and summarizes blocking critical/high findings.

If repository security scanning is still desirable, move/rewire that capability under the appropriate canonical/product boundary before deleting the onboarding island.

Do not retain the old `Project` noun merely to save the scanner.

## Candidate B: Hive `credential_store_v2.py`

### Current state

- structurally unreachable in the current baseline
- not used by the mounted Hive credentials API
- mounted API uses core `UserCredentialStore` instead
- v2 uses PostgREST table `hive_credentials_v2`
- secrets are Fernet-encrypted under `HIVE_CREDENTIALS_MASTER_KEY`

### Deletion gate

1. Data audit: determine whether `hive_credentials_v2` exists and contains credential records in any deployed environment.
2. Secret migration: if records exist and are still needed, migrate them without exposing plaintext through logs/API responses.
3. Consumer audit: verify no operator script, migration, or deployment-specific extension imports `AgnosticCredentialStore` outside normal process roots.
4. Capability migration: ensure any unique multi-instance credential behavior (`name`, `type`, `api_base`, connection metadata) that is still desired is represented by canonical credential/resource/Binding design.
5. Security review: do not delete the only decryption path until retained ciphertext is either migrated or intentionally destroyed.
6. Schema/config cleanup: only then remove `hive_credentials_v2` table/config and dead service code.
7. Reachability ratchet: baseline entry should disappear through deletion, not be suppressed.

## Candidate C: Hive `services/tool_binding.py`

### Current state

- structurally unreachable
- module says it was implemented ahead of dispatch wiring
- resolves legacy Persona Workspace per-agent tool list + prompt overrides
- does not represent canonical Capability/Binding/Provider/Credential/Invocation

### Deletion/supersession gate

1. Stream 6 canonical Binding/Invocation contract exists.
2. Stream 7 has a replacement mapping for the desired sticky per-agent tool/prompt override UX, if that UX is retained.
3. Existing persisted Hive Workspace `tool_bindings` data is either migrated or explicitly deprecated.
4. Product tests verify explicit empty tool lists still narrow availability to zero when that behavior is retained.
5. Persona defaults remain availability/configuration, not authorization grants.
6. Remove resolver and legacy persistence fields only after migrated workspaces no longer need them.

## Candidate D: Hive `middleware.privilege`

### Current state

- unreachable in current baseline
- pass-through `dispatch()`
- no active privilege checks
- live Hive security behavior is in `AuthMiddleware`, not this class

### Deletion gate

1. Verify no downstream deployment imports `PrivilegeMiddleware` as a customization hook.
2. Verify no docs/spec claim it is the active authorization layer.
3. Remove dead tests/imports/configuration if present.
4. Do not replace it with another placeholder; canonical Project authorization belongs to Stream 3.

## Candidate E: private Task recovery/replay modules

These are **not deletion candidates until behavior is ported**.

Current modules are structurally unreachable but contain useful recovery semantics:

- crash-loop quarantine
- version compatibility
- checkpoint replay
- open tool call reconstruction
- wave-state reconstruction
- spend reconstruction
- pending approval reconstruction

### Delete-after gate

Only remove after equivalent behavior has acceptance coverage on canonical Run/Attempt/Event/Checkpoint/GraphExecutionState.

Classification: `port first, then delete`.

## Candidate F: Builders private lifecycle/executor

Builders remains structurally unreachable, but contains valuable domain behavior.

### Delete-after gate

Do not bulk-delete Builders merely because it is unreachable. First migrate/retain:

- stage vocabulary/templates
- quality gates
- revise targets/feedback loops
- artifacts
- completion criteria
- any required worker/runtime-version semantics

Then replace/remove:

- private RunState/RunStatus
- StageEvent durability
- GraphPipelineExecutor universal lifecycle/traversal mechanics
- private retries/persistence

Classification: `migrate domain behavior, then delete duplicate lifecycle`.

## Candidate G: Canvas private job runner

Canvas runner/store/tool modules are structurally unreachable, but generation domain invariants and lease/retry recovery are valuable.

### Delete-after gate

1. Canvas product migration decision is explicit.
2. layer/generation/refine/reference/variant invariants have canonical-product coverage.
3. claim/lease/retry/stale-worker behavior is represented in canonical Run/Attempt/recovery if required.
4. existing Canvas records/assets are migrated or retained intentionally.
5. only then remove the private Canvas JobStatus/runner lifecycle.

## General deletion standard

A Stream 4 candidate is safe to delete only when all relevant categories are resolved:

- **Reachability:** no production rooted caller depends on it.
- **Data:** persisted data has an explicit retain/migrate/destroy decision.
- **Behavior:** useful behavior has been migrated or intentionally retired.
- **External contracts:** callbacks, webhooks, CLIs, operators, and environment configuration are accounted for.
- **Docs:** ADR/SPEC/README status stops advertising removed behavior.
- **Tests:** tests are migrated to the canonical owner or deleted because the behavior is intentionally retired.
- **Ratchet:** reachability/quality baselines shrink rather than gain exceptions.

This standard prevents “dead code cleanup” from silently deleting the only implementation of behavior another convergence stream was supposed to preserve.
