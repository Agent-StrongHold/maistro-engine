# Code Quality Third Pass — 2026-06-28

This pass goes deeper than the prior broad scan reports by pairing scanner output with manual inspection of the code around each candidate finding. It is not an exhaustive claim that every remaining issue is known; it adds another set of concrete, owned findings and follow-up specs.

## Commands and inspection inputs

- `./scripts/install-quality-scanners.sh`
- `uv run python -m vulture packages/hive-conductor/backend packages/maistro-core/src packages/maistro-server/src packages/maistro-canvas/src packages/maistro-turing/src packages/maistro-bootstrap/src packages/maistro-registry/src --exclude '*/.venv/*'`
- Manual inspection of `packages/hive-conductor/backend/routes/dags.py`, `packages/maistro-core/src/maistro/graph/node.py`, `packages/maistro-core/src/maistro/graph/dag_validator.py`, `packages/maistro-bootstrap/src/maistro_bootstrap/plan.py`, and `packages/maistro-registry/src/maistro_registry/cli.py`.

## Findings

| Priority | Finding | Evidence | Direction | Owning spec |
|---|---|---|---|---|
| P1 | Vulture output is still too noisy to be useful as a gate because route decorators, Pydantic models, protocol classes, and dynamic integration surfaces are mixed with true positives. | FastAPI route callables and declarative fields are reported as unused, and the now-fixed unreachable DAG-route block shows why true positives must remain visible. | Build a reviewed vulture allowlist with categories, owners, and one-line rationales; fail only on new unclassified findings. | [SPEC-271](specs/SPEC-271-dead-code-route-surface-baseline.md) |
| P1 | `NodeRun` single-attempt and beam execution contain retry, timeout, parse, circuit, cancellation, and partial-success behavior that is too branchy to rely on happy-path tests. | `_execute_single` interleaves retry accounting, budget/circuit checks, LLM timeouts, parser errors, and final failure conversion; `_execute_beam` converts exceptions to candidates and has all-error/empty-candidate paths. | Specify exact state transitions and add focused tests for every retry/beam edge path before further graph-execution refactors. | [SPEC-272](specs/SPEC-272-node-run-retry-and-beam-contracts.md) |

## Borderline-case checklist for implementation PRs

1. Do not treat a passing scanner run as proof of quality; scanners should identify candidates, then code inspection decides whether to remove, test, or allowlist.
2. For every function with retry, timeout, cache TTL, or partial-success behavior, require tests for all-success, all-fail, mixed-success, cancellation, stale data, forced refresh, and invalid input.
3. For every CLI or route contract, assert exact user-facing output or response shape, not only that the call returns a truthy object.
4. For every allowlisted dead-code finding, require a rationale that explains the runtime discovery mechanism or public API consumer.
5. For every accepted complexity hotspot, require either decomposition or a spec-linked reason why a state machine/orchestrator remains centralized.

## Concrete next actions

1. Implement the vulture/radon baseline in SPEC-271 before making those scanners blocking.
2. Implement the remaining SPEC-272 retry/timeout/cancellation contract cases before changing graph execution internals.
