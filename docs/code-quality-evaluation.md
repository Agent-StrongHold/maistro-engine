# Code Quality Evaluation Framework

This framework turns code-review concerns into an auditable quality rubric for Maistro Engine. It complements the remediation backlog in [quality-standards.md](quality-standards.md) and the test-fidelity requirements in [SPEC-205](specs/SPEC-205-test-suite-fidelity.md).

## Quality dimensions

| # | Dimension | What good looks like | Suggested evidence |
|---|-----------|----------------------|--------------------|
| 1 | Assertion strength | Tests assert exact outputs, state transitions, emitted events, error codes, and side effects instead of existence-only checks such as `is not None`. | Pytest assertions comparing concrete values, `pytest.raises(..., match=...)`, snapshot/contract assertions for stable payloads. |
| 2 | Assertion soundness | The test measures the behavior it claims to measure and would fail for the most plausible bug in that behavior. | Arrange/act/assert structure, mutation-testing survival review, comments only where the tested invariant is non-obvious. |
| 3 | Assertion-purpose link | Each assertion maps to the public contract, acceptance criterion, or function responsibility under test. | Test names and parametrization describe the requirement; spec/ADR markers when applicable. |
| 4 | Edge-case coverage | Boundaries, empty inputs, malformed inputs, retries, timeouts, authorization failures, and concurrency races are represented. | Boundary-value tests, Hypothesis/property tests, failure-mode tests, deterministic clock fixtures for time logic. |
| 5 | Unit-test behavior | Units are isolated from network, wall-clock, database, and real LLM providers unless those dependencies are the unit under test. | Fast pytest subset, fakes/mocks, no hidden sleeps, no shared global state leakage. |
| 6 | Integration behavior | Adjacent components work together using realistic adapters, schemas, and persistence where the feature depends on them. | Package-level integration tests, database-backed tests for persistence invariants, contract tests at module boundaries. |
| 7 | End-to-end behavior | User input reaches user-visible output through the same path production uses, including scheduled/timer/alarm flows and mocked human-in-the-loop checkpoints. | E2E tests tagged with `scope("e2e")`, deterministic timers, mocked HITL decisions, assertions on final user-facing artifacts. |
| 8 | Cyclomatic complexity | Functions remain simple enough to reason about; complex orchestration is decomposed into named steps. | Radon/ruff complexity checks; target cyclomatic complexity <= 10 for ordinary functions and justified exceptions only. |
| 9 | Self-documenting code | Names, types, and structure make intent obvious before reading comments. | Clear function and variable names, small functions, typed domain models, removal of magic numbers in favor of named constants. |
| 10 | Maintainability | Code is loosely coupled, cohesive, documented where non-obvious, and easy to change without hidden side effects. | Dependency injection over module-level singletons, stable interfaces, focused modules, architecture notes for cross-cutting changes. |
| 11 | Docstring coverage | Public APIs, protocols, fixtures, and non-trivial internal helpers explain purpose, parameters, returns, errors, and invariants. | Interrogate/pydocstyle-style reports; docstrings on exported classes/functions and pytest fixtures that encode reusable behavior. |
| 12 | Dead-code detection | Unused functions, classes, and modules are either removed or explicitly justified as plugin/API surface. | Vulture report reviewed with an allowlist for dynamic imports and public extension points. |
| 13 | Complexity metrics | Maintainability index, raw size, and complexity trends are tracked over time, not reviewed ad hoc. | Radon `cc`, `mi`, and `raw` reports with thresholds and trend deltas. |
| 14 | Static linting | Style, likely bugs, unsafe patterns, and import hygiene are enforced automatically. | `ruff check .` and `ruff format --check .` in CI; no try/except around imports. |
| 15 | Type safety | Public and package-internal contracts are checked statically. | `mypy` over all package `src` trees; typed Pydantic models for API boundaries. |
| 16 | Dependency hygiene | Dependencies are intentionally declared, unused dependencies are removed, and transitive dependencies are not relied on implicitly. | Deptry/import-linter reports, lockfile review, outdated-package reports focused on maintainability rather than security risk. |
| 17 | Duplicate-code detection | Repeated implementation paths are either extracted or intentionally documented when duplication protects boundaries. | jscpd or pylint duplicate-code reports, plus reviewer sign-off for accepted duplication. |
| 18 | Test quality mutation signal | Tests fail when implementation behavior is meaningfully mutated. | Cosmic Ray/mutmut on high-risk modules; review of surviving mutants as missing assertions or equivalent mutants. |
| 19 | LLM-as-judge review A | An LLM reviewer checks assertion-purpose alignment, edge cases, and maintainability using repository context, but cannot replace deterministic checks. | Saved prompt, model, inputs, and summarized findings attached to the PR or CI artifact. |
| 20 | LLM-as-judge review B | A second model or prompt independently critiques the change for blind spots, especially test soundness and hidden coupling. | Cross-model disagreement review; action items converted to tests or documented non-actions. |

## Recommended scanner set

Use `./scripts/run-quality-scans.sh` for the current consolidated local scan. If radon or vulture are missing, install the non-security scanner subset with `./scripts/install-quality-scanners.sh` (requires PyPI or an internal package index); once installed, the scan script runs them as advisory until baselines are triaged. Use deterministic code-quality scanners as merge gates and LLM judges as advisory reviewers. Security review is tracked separately and intentionally excluded from this rubric:

- **pytest + pytest-cov** for unit, integration, e2e, and coverage evidence.
- **Hypothesis** for property and boundary testing where input space is large.
- **Cosmic Ray or mutmut** for mutation testing on high-risk logic.
- **ruff** for linting, formatting, import hygiene, and selected complexity rules.
- **mypy** for static typing across package source trees.
- **vulture** for dead-code detection with a reviewed allowlist.
- **radon** for cyclomatic complexity, maintainability index, and raw metrics.
- **interrogate or pydocstyle** for docstring coverage and docstring conventions.
- **deptry** for unused, missing, and transitive dependency hygiene.
- **jscpd or pylint duplicate-code** for duplicated implementation paths.
- **import-linter** for architectural dependency-boundary rules when packages need explicit layering constraints.
- **LLM judge prompts** for test-intent critique, edge-case brainstorming, and maintainability review; record model names and prompt versions.

## Evaluation reports

- [2026-06-21 initial code quality scan](code-quality-initial-scan-2026-06-21.md)
- [2026-06-21 code quality deep dive](code-quality-deep-dive-2026-06-21.md)
- [2026-06-21 code quality second pass](code-quality-second-pass-2026-06-21.md)
- [2026-06-28 code quality third pass](code-quality-third-pass-2026-06-28.md)

## Minimal PR quality gate

Every code PR should answer these questions before merge:

1. Which user-visible or package-visible contract changed?
2. Which unit tests prove the smallest behavior in isolation?
3. Which integration or e2e test proves the real path still works?
4. Which failure mode or edge case would have failed before this change?
5. Did scanners run cleanly, or is every warning documented with an owner and follow-up?
6. If an LLM judge was used, which findings became tests or code changes?

## LLM judge prompt templates

### Prioritized improvement judge

```text
You are reviewing a Maistro Engine pull request for test and code quality.
Given the diff, relevant specs, and nearby code, propose exactly 5 prioritized improvements that would most increase confidence, readability, or maintainability.
Rank them from highest to lowest expected value.
For each improvement, include: priority rank, affected file or symbol, the quality dimension it improves, why it matters, and a concrete change or test to add.
Prefer improvements that are specific, verifiable, and tied to the purpose of the changed code.
Do not include security findings; security is reviewed separately.
```

### Worst-flaw judge

```text
You are reviewing a Maistro Engine pull request for the biggest test and code quality risks.
Given the diff, relevant specs, and nearby code, find exactly the 5 biggest or worst flaws that could make the change misleading, fragile, over-complex, under-tested, or hard to maintain.
Rank flaws by severity and blast radius.
For each flaw, include: severity rank, affected file or symbol, the failed quality dimension, why it is risky, how the current tests or scanners could miss it, and the smallest concrete fix.
Focus on assertion weakness, assertion soundness, missing edge cases, over-mocking, poor unit/integration/e2e coverage, cyclomatic complexity, unclear code, tight coupling, missing docstrings, dead code, and duplicate code.
Do not include security findings; security is reviewed separately.
```
