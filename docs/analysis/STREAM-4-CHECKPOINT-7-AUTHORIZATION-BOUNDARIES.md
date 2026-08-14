# Stream 4 Checkpoint 7: Authorization and Governance Boundaries

Date: 2026-08-14
Source audited: `develop`

This checkpoint isolates the currently live authorization-like behavior from unreachable placeholders and adjacent security/policy systems so Stream 3 can converge Project authorization without conflating unrelated gates.

## 1. Hive PrivilegeMiddleware is not current authorization infrastructure

`packages/hive-conductor/backend/middleware/privilege.py` is a pass-through placeholder. Its dispatch method always calls the next middleware and performs no privilege check.

The current reachability baseline also lists `middleware.privilege` as unreachable.

Classification: `unreachable no-op placeholder`.

It can be removed once no integration/tests intentionally depend on the adapter seam. It should not influence the canonical permission model.

## 2. Hive AuthMiddleware is the live compatibility authorization layer

`packages/hive-conductor/backend/middleware/auth.py` is mounted by the production Hive app and currently owns:

- session/bearer principal resolution
- authentication requirement for `/v1/*`
- public route exceptions
- admin break-glass restrictions
- global permission names
- task-scoped elevated permissions
- method/path -> permission mapping
- route-specific exemptions
- a special admin-only persona-wide feedback rule

Examples of current permission names include:

- `config.write`
- `credentials.write`
- `dags.write`
- `schedules.write`
- `workspaces.write`
- `harness.execute`
- `rsi.execute`
- `pm.execute`
- `audit.write`

This is real security behavior and must not simply disappear during Project authorization migration.

Classification: `live compatibility authorization`.

## 3. Current Hive authorization is path/global-scope, not canonical resource authorization

The current middleware decides authorization from:

- HTTP method
- route prefix
- a principal's global permission list
- task-scoped elevation list

It does not resolve:

- canonical Workspace membership
- canonical Project membership
- Project resource tree ownership
- credential ownership/grants
- Binding ownership/grants
- resource inheritance / explicit deny precedence

Some individual routes, such as Hive Workspace routes, perform additional object membership checks themselves.

### Stream 3 migration direction

Preserve the working outer compatibility boundary while introducing canonical resource authorization beneath it:

1. authenticate principal
2. resolve canonical Workspace/Project/resource
3. evaluate canonical membership/grant/deny rules
4. apply runtime elevation/approval policy where the action requires it
5. invoke capability/product handler

As product routes migrate, global path permission checks can become coarse outer guards or be retired where canonical resource checks fully express the rule.

## 4. Task-scoped elevation is useful but belongs above Project authorization

Current `principal_has_permission()` requires both:

- the permission in the user's configured permission list
- the same permission in `elevated_permissions`

unless the user is admin.

This makes elevation temporary and task-scoped by surrounding Hive auth/session behavior.

That is a useful break-glass/high-risk-action concept, but it should not become the ownership model for resources.

### Stream 3/6 handoff

Keep distinct:

- Project authorization: may this principal access this resource?
- elevation/approval: may an otherwise-authorized principal perform this high-risk action right now?

## 5. Existing Hive Workspace route-level membership checks are behavioral source material

Checkpoint 2 identified the active Workspace routes' object-level rules:

- members can view
- owner/editor/viewer roles
- owner-only member changes
- self-removal
- final-owner protection
- owner-only destructive/settings operations

These are closer to canonical resource authorization than the path-level middleware and should be used as acceptance-test input when canonical Workspace/Project membership is implemented.

However, they currently apply to the adopted-Persona Workspace noun, so the behavior must be remapped to the correct canonical ownership object rather than copied mechanically.

## 6. Governance ConformanceEngine is not user authorization

`maistro.governance.conformance.ConformanceEngine` checks candidate policy decisions against precedence layers:

1. ADR invariants
2. Spec invariants
3. prior policy decisions

and can require human review for prose-only invariants.

The current reachability baseline marks governance/conformance unreachable.

This is architecture/policy conformance logic, not principal-resource access control.

Classification: `unreachable governance policy source`, not authorization engine.

## 7. Input security Gate remains separate

`maistro.security.Gate` handles:

- sanitization
- Warden content scanning
- strike escalation / account lockout
- request sufficiency checks
- supervised-mode clarification

It answers whether an input is safe/sufficient to enter the execution system, not whether the principal owns or may use a Project resource.

Do not merge with canonical permission resolution.

## 8. SequencePolicyEngine / PolicyActionGate remain runtime policy

The policy engine tracks cumulative action state per key and returns allow / deny / require-approval verdicts. PolicyActionGate adapts foreign harness action envelopes into that engine.

This is runtime action/budget/approval policy.

It should run after resource authorization and before/during Invocation as appropriate.

## 9. A2A peer allowlists are delegation-specific policy

`GuestPeerManager.PeerTrust.allowed_agents` constrains which agent IDs may use a registered external peer.

That is a provider/delegation rule. Canonical Project authorization must still decide whether the principal/project may access the peer/Binding at all.

Do not substitute agent allowlists for resource authorization.

## Canonical boundary map for Stream 3/6

The existing code supports a clean layered model:

### Layer 1: Authentication

Who is the principal?

Current source: Hive AuthMiddleware/session resolution and core auth implementations.

### Layer 2: Resource authorization

May the principal access this canonical Workspace/Project/resource?

Current source material: legacy Project membership + Hive Workspace membership behavior.

Canonical owner: Stream 3.

### Layer 3: Input safety

Is the user-provided content safe/sufficient to process?

Current source: security Gate/Warden/strikes.

### Layer 4: Runtime action policy / elevation

May this authorized action execute now, given risk, budget, impact, approval, and temporary elevation?

Current source material: Hive task-scoped elevation, SequencePolicyEngine, tool approval/reversibility rules.

### Layer 5: Invocation

Which Binding/Provider/Credential executes the Capability for this Attempt?

Canonical owner: Stream 6.

Keeping these layers distinct prevents Persona, route prefixes, Warden flags, or runtime budgets from accidentally becoming the authorization algorithm.

## Deletion classifications from this slice

### Strong candidate

- `middleware.privilege`: unreachable and currently a no-op placeholder

Prerequisite: verify no deployment-specific import relies on the class name as an extension hook.

### Keep during migration

- live Hive AuthMiddleware compatibility behavior
- task-scoped elevation semantics if still desired
- Workspace membership acceptance behavior

### Do not wire as authorization

- governance conformance engine
- security Gate/Warden
- SequencePolicyEngine
- A2A allowed-agent policy

These may be useful elsewhere but solve different problems.

## Next Stream 4 work

1. publish explicit delete-after prerequisites for closed Hive Project / credential-v2 / placeholder islands
2. inspect remaining live UI/service adapters for legacy Run/DAG/Mission DTO dependencies
3. track convergence PRs against these audit handoffs and update classifications as paths become canonical
