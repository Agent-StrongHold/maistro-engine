# Code Quality Second Pass — 2026-06-21

This pass expands beyond the original widget/chat/canvas focus. It uses a broader radon run and manual inspection of additional hotspots. Like the first deep dive, it is not an exhaustive proof of quality; it records new high-signal areas that need owning specs and follow-up tests.

## Command used

```bash
uv run python -m radon cc packages/hive-conductor/backend packages/maistro-core/src packages/maistro-server/src packages/maistro-canvas/src packages/maistro-turing/src packages/maistro-bootstrap/src packages/maistro-registry/src -s -n C
```

## New findings

| Priority | Finding | Why it matters | Owning spec |
|---|---|---|---|
| P1 | Graph execution swallows parallel node exceptions into node state assumptions. | `asyncio.gather(..., return_exceptions=True)` discards returned exception objects and relies on each `NodeRun` to self-classify; orchestration needs explicit exception accounting and tests. | [SPEC-265](specs/SPEC-265-graph-execution-exception-accounting.md) |
| P1 | Tool guardrail policy is branch-heavy and test-sensitive. | `_evaluate` encodes exact-repeat, same-tool-failure, and idempotent-no-progress thresholds in one branch sequence; regressions could over-block useful retries or under-block loops. | [SPEC-266](specs/SPEC-266-tool-guardrail-policy-table.md) |
| P1 | Auth and request logging middleware need policy tables. | Public/protected/admin-chat/elevation behavior is encoded as prefix checks, while request logging re-resolves users and logs query params; behavior needs explicit contract tests and sanitized logging policy. | [SPEC-267](specs/SPEC-267-http-middleware-policy-contracts.md) |
| P2 | Engine task submission mixes capability gating, context hydration, DTO construction, and persistence. | `submit_task` is a small orchestration hotspot; failures in context hydration are swallowed and capability gating is not isolated for exact unit tests. | [SPEC-268](specs/SPEC-268-engine-task-submission-contracts.md) |
| P2 | External payload parsers are tolerant but not contract-tested. | Atlassian parsing accepts nested and flattened MCP/REST payloads in one function; this is useful, but shape tolerance should be table-driven and schema-backed. | [SPEC-269](specs/SPEC-269-external-payload-normalization-contracts.md) |
| P2 | Credential pool selection and diagnostics are coupled. | Pool exhaustion computes diagnostic counts inside selection; strategy behavior and error payloads need independent truth-table tests. | [SPEC-270](specs/SPEC-270-credential-pool-selection-contracts.md) |

## Manual notes

### Graph execution exception accounting

`GraphRun._execute` creates node runs for all active roles, executes them with `asyncio.gather(..., return_exceptions=True)`, then ignores the returned list and infers success/failure from each `NodeRun.phase`. That can be correct if every `NodeRun.execute` always catches/classifies its failures, but the graph orchestrator currently has no explicit assertion that gathered exceptions were converted into node state. This is a test soundness risk around cancellation, retry exhaustion, and unexpected node exceptions.

### Tool guardrail policy table

`ToolGuardrail._evaluate` separately checks exact repeats, same-tool failures, and idempotent no-progress patterns. The order matters: an exact repeat can block before failure-pattern logic is evaluated. That may be intended, but it should be a documented policy table with threshold boundary tests for warn/block transitions.

### HTTP middleware policy contracts

`AuthMiddleware.dispatch` mixes public route bypasses, OPTIONS bypasses, session extraction, admin-chat blocking, and protected-operation elevation checks. `RequestLogMiddleware.dispatch` has its own path filtering and re-reads current user data for logging. These are not necessarily wrong, but they need route-policy and logging-sanitization tests so future path additions do not accidentally bypass auth or leak sensitive query parameters.

### Engine task submission contracts

`EngineService.submit_task` normalizes capability, applies gated-capability rules, conditionally hydrates program context, constructs `TaskCreate`, persists it, and logs. The function should be split into pure helpers for capability admission, context hydration, and DTO construction so tests can assert exact behavior for gated capabilities, missing context, and backend failures.

### External payload normalization

`AtlassianMCPClient._parse_jira_issue` intentionally accepts both nested REST payloads and flattened MCP payloads. The tolerance is valuable, but every accepted shape should have an exact fixture and normalized `JiraIssue` assertion. Unknown or malformed shapes should produce deterministic empty/default fields rather than accidental stringification surprises.

### Credential pool selection contracts

`CredentialPool.select` combines no-available-key diagnostics with strategy dispatch. The no-available case should have truth-table tests for all-blocked, all-cooling, mixed blocked/cooling, and soonest-available calculation. Strategy tests should separately prove `fill_first`, round-robin, and weighted selection behavior.
