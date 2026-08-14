---
id: SPEC-081226-034b
title: Package Ownership and Dependency Direction
repo: maistro-engine
kind: spec
status: AC Defined
created: 2026-08-12
history:
  - status: Proposed
    date: 2026-08-12
  - status: Accepted
    date: 2026-08-12
  - status: AC Defined
    date: 2026-08-12
substrate:
  - maistro-engine#ADR-081226-034b
implements:
  - maistro-engine#ADR-081226-034b
related: []
supersedes: []
superseded-by: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
source:
  - packages
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-081226-034b: Package Ownership and Dependency Direction

- **Status:** Active
- **Date:** 2026-08-12
- **ADR:** `ADR-081226-034b`

## Canonical package roles

| Package | Canonical role |
|---|---|
| `maistro-core` | reusable domain semantics and generic platform mechanisms |
| `maistro-server` | generic API/application transport adapter |
| `hive-conductor` | Hive product/application |
| `maistro-canvas` | Canvas/composition + book-product domain/surfaces |
| `maistro-design` | design domain/skills/systems/rendering adapters |
| `maistro-turing` | cognition/self-model/persona-agent extensions |
| `maistro-evolve` | optimization/evaluation domain |
| `maistro-rsi` | recursive self-improvement domain/surface |
| `maistro-bootstrap` | installation/materialization/setup lifecycle |
| `maistro-arch-governance` | target identity for architecture/spec governance tooling |

## Requirements

1. `maistro-core` MUST NOT import product/application packages to implement canonical domain semantics.
2. Specialized packages MUST integrate execution through canonical Graph/Node/Run/Binding contracts rather than redefine universal lifecycle models.
3. `maistro-server` routes MUST delegate durable domain/execution work to canonical services once those services exist.
4. Hive duplicate lifecycle/orchestration paths MUST become adapters and be removed only after parity/reachability tests.
5. ExecutionRuntime MUST NOT import graph traversal/domain modules to decide readiness/predicates/policy.
6. Specialized NodeTypes/providers SHOULD register through public extension contracts rather than reverse imports from core.
7. `maistro-bootstrap` user-work execution responsibilities MUST be inventoried and migrated where they overlap canonical runtime/Builders/capability ownership.
8. The current `maistro-registry` physical rename MUST be isolated and MUST update package path, Python import, CLI, root workspace/source metadata, lockfile, tests and docs together.
9. Architecture governance tooling MUST remain outside the product Run ontology unless deliberately invoked as an ordinary user-work capability.
10. Package-specific event/lifecycle models on migrated paths MUST carry canonical IDs and cannot become competing authorities.
11. Dependency cycles across core/product/specialized packages MUST be rejected or explicitly waived with architecture rationale.

## Architecture fitness rules to implement

At minimum CI SHOULD enforce:

- core cannot import outward product packages;
- Runtime cannot import graph/domain traversal semantics;
- scheduler code cannot execute admitted workload directly instead of creating a Run;
- NodeType executors cannot own Run persistence;
- UI/server application code cannot invoke provider implementation directly on migrated paths;
- credentials/secrets cannot live in Graph/Node definitions;
- Binding cannot widen parent permissions;
- migrated package events carry canonical Workspace/Run correlation.

## Acceptance Criteria

1. Static/import tests prove `maistro-core` has no prohibited imports of Hive/Canvas/Design/Turing/RSI/Evolve/server application code.
2. A specialized package can register/use a NodeType or Provider through a public contract without core importing that package.
3. A server route integration test reaches canonical Workspace/Run service rather than constructing a private lifecycle record on a migrated path.
4. A Hive migrated path produces the same canonical Run/Event history as the generic server path.
5. Runtime import fitness test prevents graph predicate/readiness logic from moving into `maistro.runtime`.
6. Bootstrap audit has explicit keep/migrate disposition for agent loop, model selector, sandbox, session, delivery and credentials.
7. The `maistro-registry` -> `maistro-arch-governance` migration commit, when executed, regenerates the lockfile and passes package CLI/import tests before old paths are removed.
8. Architecture fitness CI fails on an intentionally introduced forbidden dependency/lifecycle fixture.
9. Reachability baseline decreases when duplicated product orchestration is migrated or removed.
10. No specialized package loses valid domain behavior merely to reduce package count.

## Non-goals

This SPEC does not require immediate physical package moves, prohibit all optional dependencies in application layers, or force specialized domain assets into `maistro-core`.
