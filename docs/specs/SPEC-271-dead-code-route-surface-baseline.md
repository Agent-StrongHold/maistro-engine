---
id: SPEC-271
title: "Dead-code scanner baseline and route/model surface classification"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-06-28
substrate:
  - maistro-engine#SPEC-205
related:
  - maistro-engine#SPEC-264
implements: []
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
tests: []
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-271: Dead-Code Route Surface Baseline

## Finding addressed

The third-pass vulture run mixed a true unreachable-code finding in `packages/hive-conductor/backend/routes/dags.py` with expected framework false positives from FastAPI route handlers, Pydantic fields, and dynamic integration surfaces. The unreachable-code finding has been removed; the remaining work is making the scanner baseline precise enough to block future regressions without suppressing real issues.

## Design

1. Keep the DAG route failed-response regression test as the guard for the removed unreachable branch.
2. Create a vulture allowlist/baseline with one rationale per symbol.
3. Classify findings as one of: framework decorator surface, declarative model field, public extension point, dynamic import surface, planned implementation, or remove/fix.
4. Make new 100%-confidence unreachable-code findings fail CI after the baseline lands.
5. Keep security findings out of this baseline; security remains a separate review.

## Acceptance criteria

- [x] The unreachable duplicate code in the DAG route is removed.
- [x] The DAG route has a regression test for the failed completion response.
- [ ] Vulture baseline entries include category, owner, and rationale.
- [ ] Route handlers and Pydantic fields are allowlisted only by category, not by broad file suppression.
- [ ] New high-confidence unreachable code fails CI.
- [ ] The scan report links any remaining remove/fix finding to a spec or issue.
