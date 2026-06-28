---
id: SPEC-272
title: "NodeRun retry, timeout, parse, and beam execution contracts"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-06-28
substrate:
  - maistro-engine#SPEC-177
  - maistro-engine#SPEC-205
related:
  - maistro-engine#SPEC-265
implements: []
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
tests: []
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-272: NodeRun Retry and Beam Contracts

## Finding addressed

`NodeRun._execute_single` and `NodeRun._execute_beam` combine retry limits, circuit/budget checks, cancellation, LLM timeout handling, parser failures, candidate scoring, and final accounting. Beam parse-failure edge cases now have exact tests and the all-parse-failed path now terminates as failed instead of returning while still running; remaining work is the single-attempt retry/timeout/cancellation state table.

## Design

1. Define a state table for single-node execution: ready, budget exhausted, circuit open, cancelled, timeout, parse failure, retryable provider failure, terminal success, and terminal failure.
2. Define retry accounting rules for parse failures versus provider exceptions.
3. Define beam behavior for all-success, all-exception, mixed scored/error candidates, empty beam width, and scorer failure.
4. Require exact assertions on final run status, attempt count, selected candidate, error payload, and emitted events.
5. Use deterministic fake LLM, parser, scorer, clock, and budget/circuit fixtures.

## Acceptance criteria

- [ ] Single execution tests cover success, timeout, parse failure, provider exception, cancellation, circuit-open, and budget-exhausted paths.
- [ ] Retry count and final error message are asserted exactly for each failure family.
- [x] Beam tests cover all-success, all-parse-fail, and mixed parse-failure/success paths.
- [ ] Beam tests cover all-provider-error, empty candidate list, and scorer failure.
- [ ] No graph execution test depends on a real LLM provider or wall-clock sleep.
- [ ] Any intentional centralized complexity is linked to this spec with a reason.
