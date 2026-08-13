# SPEC-081226-6e34: Hierarchical Permissions

- **Status:** Active
- **Date:** 2026-08-12
- **ADR:** `ADR-081226-6e34`

## Permission chain

```text
User -> Workspace -> Persona -> Graph -> Node -> Binding -> Invocation
```

## Requirements

1. Permission data MUST distinguish inheritance/no-additional-restriction from explicit allow/deny semantics.
2. Effective permission MUST never contain an action/resource privilege absent from the applicable ancestor ceiling.
3. Binding MUST NOT widen Node/Graph/Persona/Workspace/User authority.
4. Invocation MUST be denied before provider execution when effective permission does not authorize the requested action/resource.
5. Policy MUST NOT convert a permission denial into an allow.
6. Approval MAY satisfy a policy condition only for authority that is already available under the effective/authorized elevation context.
7. Privilege elevation MUST be explicit, time/scope bounded where applicable, auditable and bounded by root User/Workspace entitlement.
8. Child Runs MUST inherit authorization context and MAY narrow it. Cross-Workspace child Runs require explicit authorization/binding semantics.
9. Credential resolution MUST occur only after Binding/Invocation authorization and MUST enforce credential scope.
10. Direct UI/API/provider integrations MUST NOT bypass canonical authorization because of package-specific allowlists.
11. Collaboration roles MUST map to permission contributions rather than become a second universal authorization model.
12. Warden/Sentinel/Gate/trust/scanning/sandbox/reversibility mechanisms MUST be representable as permission/policy inputs or decisions on the canonical path.
13. Permission/policy decisions MUST emit audit/event correlation including Workspace and Invocation/Run IDs when applicable.
14. Default cross-Workspace access MUST be denied.

## Effective-permission semantics

For each requested action/resource:

1. resolve authenticated User/root entitlement;
2. resolve Workspace authorization;
3. apply Persona ceiling;
4. apply Graph ceiling;
5. apply Node ceiling;
6. apply Binding ceiling;
7. validate Invocation request is a subset;
8. evaluate contextual Policy conditions;
9. resolve allowed credentials/provider;
10. execute Invocation.

Any denial short-circuits execution.

## Acceptance Criteria

1. A Node allowed `read` under a Workspace allowing `read,write` receives only `read`.
2. A Binding requesting `write` beneath a read-only Node is rejected before provider invocation.
3. A ToolExposure cannot call an unexposed/unpermitted Binding by naming its provider directly.
4. A policy approval cannot make a root-denied capability available.
5. An approved elevation flow can activate explicitly authorized additional scope while remaining within User/Workspace entitlement and producing an audit record.
6. A child Run receives no permission absent from its parent/Binding context.
7. Cross-Workspace delegation is rejected without explicit authorization.
8. Credential resolution fails when Invocation is permitted for the Capability but not for the required credential scope.
9. Warden/Sentinel denial prevents Invocation even when static permission allows it.
10. Sandbox/network restrictions are applied as policy constraints to an otherwise permitted execution.
11. Collaboration viewer/editor/owner roles map to expected Workspace/Session actions without bypassing lower Node/Binding restrictions.
12. Audit/event output can explain which level/policy denied or conditioned an Invocation without exposing secrets.
13. Architecture fitness tests reject code paths where a Provider is invoked from product execution without a Binding/authorization boundary, except documented bootstrap/internal exemptions.

## Non-goals

This SPEC does not prescribe one storage format for PermissionSet, replace authentication providers, or eliminate domain-specific trust/risk models. It defines how those models constrain canonical execution.
