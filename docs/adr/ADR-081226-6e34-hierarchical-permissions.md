# ADR-081226-6e34: Hierarchical Permissions

- **Status:** Accepted
- **Date:** 2026-08-12
- **Deciders:** MAIstro maintainers
- **Technical Area:** Authorization, policy, credentials, security

## Context

MAIstro currently has auth scopes, collaboration roles, agent/tool allowlists, A2A trust/delegation modes, capability trust, approval gates, Warden/Sentinel/Gate controls, sandbox restrictions, credential policies and package-specific trust systems. These mechanisms must converge on the actual execution path so documented security is also runtime security.

## Decision

Authorization forms a narrowing hierarchy:

```text
User
  -> Workspace
    -> Persona
      -> Graph
        -> Node
          -> Binding
            -> Invocation
```

### Effective permission

Each level contributes an authorization ceiling. A child may inherit or narrow its parent; it may not self-grant authority absent from an ancestor.

Conceptually:

```text
effective = intersection(User, Workspace, Persona, Graph, Node, Binding, Invocation request)
```

An omitted child restriction means "inherit", not "allow everything". Explicit denial wins over allowance at the same/effective chain.

### Permission and Policy are distinct

Permission answers whether the actor/context may perform an action at all.

Policy evaluates whether an otherwise permitted action may proceed now under current state/context, and may require conditions such as approval, reversibility constraints, budget, trust, sandboxing or human review.

Policy may deny, defer or condition permitted behavior. Policy MUST NOT grant authority beyond the effective permission ceiling.

### Invocation is the final enforcement boundary

All external/tool/model/provider/harness/sandbox/agent-backed fulfillment MUST evaluate effective permission before Invocation. Earlier UI/API checks are defense in depth and UX, not substitutes for runtime enforcement.

### Child Runs inherit and may narrow

Delegated child Runs inherit the parent Workspace and authorization context unless an explicitly authorized cross-Workspace Binding is used. Child execution may narrow permissions; it cannot automatically widen them.

### Privilege elevation

Privilege elevation cannot be implemented by a child Node/Binding simply widening itself. Any elevation must be represented as an explicit authorized change/grant at an appropriate ancestor/security boundary, remain bounded by User/Workspace entitlement, be policy/audit visible, and produce a new effective authorization context before Invocation.

### Credentials follow permission

Permission to reference a Binding does not automatically expose all credentials. Credential resolution occurs only for an authorized Binding/Invocation and is further constrained by credential scope/policy.

### Existing security systems become evaluators/inputs

Existing systems remain useful but participate in the canonical envelope:

- auth/JWT/service-key scopes establish actor/root authority;
- collaboration ACL contributes Workspace/Session surface permissions;
- Warden/Sentinel/security scanning can deny/quarantine;
- Gate/approval can condition permitted operations;
- reversibility classification influences policy/approval;
- sandbox policy constrains execution environment;
- skill/provider trust contributes policy evidence;
- credential policy constrains secret resolution;
- A2A peer trust constrains agent-backed Bindings.

No subsystem bypasses the canonical Invocation check because it performed its own earlier trust check.

### Cross-Workspace behavior is explicit

Cross-Workspace reads, bindings, delegation or artifact access are denied by default unless an explicit product/security mechanism authorizes them.

## Consequences

- Security applies to the real execution path.
- Agents-as-tools cannot gain more authority than the calling context.
- Collaboration/trust/approval mechanisms can coexist without becoming separate authorization roots.
- Privilege elevation becomes explicit and auditable.
- Some existing permissive direct-provider/tool calls will need adapters or migration.

## Compliance

A path complies when effective authorization is computed from the full applicable chain, Binding/Invocation cannot widen ancestors, policy cannot manufacture permission, credential resolution follows authorization, and security/trust decisions are correlated to the canonical execution IDs.

## References

- `ADR-081226-9944`
- `ADR-081226-6b46`
- `docs/analysis/ARCHITECTURE-CONVERGENCE-MATRIX.md`
