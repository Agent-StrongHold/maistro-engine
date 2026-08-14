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

Every persisted Graph contains its canonical `workspace_id`. A Run captures a stable Graph snapshot including graph identity, Workspace identity, content hash and serialized definition. Editing the source Graph after Run creation cannot change that Run.

Selecting a Node creates a NodeRun; each physical try is an Attempt. GraphExecutionState owns traversal state. Run owns universal lifecycle and correlation.

Graph traversal remains domain logic. ExecutionRuntime owns concurrency, cancellation, deadlines and process supervision mechanics only.

Subgraph execution normally creates a child Run. `GraphRun`, `GraphConfig`, durable graph lifecycle records and similar duplicate concepts are implementation debt to remove as their callers move to Graph/Run/NodeRun/Attempt. They do not require compatibility adapters or parity-preserving public aliases.
