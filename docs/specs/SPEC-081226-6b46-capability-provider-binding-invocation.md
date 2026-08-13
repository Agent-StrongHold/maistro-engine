# SPEC-081226-6b46: Capability, Provider, Binding and Invocation

- **Status:** Active
- **Date:** 2026-08-12
- **ADR:** `ADR-081226-6b46`

## Required relationships

```text
Node -> Binding -> Capability
                 -> allowed Provider set
Invocation -> selected Provider
```

## Requirements

1. Capability MUST have a stable semantic identifier/contract independent of provider implementation.
2. Provider MUST declare which Capability it implements and its protocol/health metadata.
3. Provider registration MUST NOT grant consumer authorization.
4. Binding MUST identify Workspace/global scope, Capability, allowed/pinned providers/config and credential references as applicable.
5. Node/Persona use of a Binding MUST be permission-checked before Invocation.
6. Provider selection MUST occur within Binding constraints; health fallback MUST NOT select an unauthorized provider.
7. Invocation MUST have a stable `invocation_id` and record selected Binding/Provider plus Run/NodeRun/Attempt correlation when executed in a Run.
8. Invocation MUST NOT persist resolved secret values.
9. ToolExposure MUST be generated/validated from an authorized Binding and MUST route model tool requests back through Binding/Invocation.
10. Protocol adapters MUST NOT define an independent universal execution lifecycle.
11. Agent-backed Binding invocation MUST create a correlated child Run for delegated work.
12. Harness/session handles MAY persist for provider protocol needs but MUST remain correlated to canonical execution.
13. Provider/circuit health MUST be observable separately from Run status.
14. Binding/Node policy MAY define retry/fallback constraints; Runtime only performs mechanics.
15. Existing tools, MCP, HTTP, sandbox, renderer, image and integration adapters MAY migrate incrementally behind compatibility adapters.

## Acceptance Criteria

1. Two Providers implementing the same Capability can be registered without changing Capability identity.
2. A Binding constrained to Provider A never falls back to Provider B even when B is healthy.
3. A Binding allowing A/B selects an allowed healthy provider at Invocation time and records the selected provider.
4. Removing permission for a Binding prevents Invocation even if the Provider remains registered/healthy.
5. A tool schema exposed to a model routes its call through the same Binding authorization and produces an Invocation record.
6. An HTTP/MCP adapter and at least one local function/tool adapter satisfy the same Invocation correlation contract.
7. A credential-backed Invocation resolves a credential reference at execution and persisted Graph/Node/Invocation data contains no secret value.
8. Provider circuit/health failure can cause allowed fallback without mutating Run identity.
9. Agent-backed Binding creates a child Run with parent/Invocation correlation rather than an A2A-only task lifecycle.
10. Harness session execution keeps its external handle while Run/NodeRun/Attempt remain authoritative lifecycle records.
11. Observability can query Invocation by `workspace_id`, `run_id`, `node_run_id`, `attempt_id`, `binding_id` and `provider_id` where applicable.
12. Architecture tests reject a provider/tool adapter that directly widens parent Binding permission.

## Non-goals

This SPEC does not define the hierarchical permission algorithm, exact credential store, capability marketplace UX or provider-specific protocol implementation details.
