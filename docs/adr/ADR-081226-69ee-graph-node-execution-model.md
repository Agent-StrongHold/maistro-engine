---
id: ADR-081226-69ee
title: Graph and Node Execution Model
repo: maistro-engine
kind: adr
status: Accepted
created: 2026-08-12
accepted: 2026-08-12
layer: Orchestration
owners: ['@BlakeMatthews-dev']
history:
  - status: Proposed
    date: 2026-08-12
  - status: Accepted
    date: 2026-08-12
---

# ADR-081226-69ee: Graph and Node Execution Model

## Decision

Graph is the Workspace-scoped editable composition object. Node is its universal executable position. A one-node Graph is valid.

A Run executes a stable Graph snapshot. Selecting a Node creates a NodeRun; each physical try is an Attempt.

Existing GraphRun semantics decompose into `Run + GraphExecutionState`. GraphExecutionState owns traversal state. Run owns universal lifecycle and correlation.

Graph traversal remains domain logic. ExecutionRuntime owns concurrency, cancellation, deadlines and process supervision mechanics only.

Subgraph execution normally creates a child Run. Durable graph records migrate to canonical Run/NodeRun projections after behavior parity is proven.
