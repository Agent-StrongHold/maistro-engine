---
id: S-159
title: "Node Designer + Graph Designer UI — visual composition of the hyperagent graph"
domain: infra
status: draft
priority: P1
effort: ""
created: 2026-04-25
completed: ""
owner: conductor
commits: []
supersedes: ""
---

# S-159: Node Designer + Graph Designer UI

## Acceptance Criteria

- [ ] Adding a node via Node Designer produces a node visible on the Graph Designer canvas within 1s of admin signature
- [ ] Editing a node via Node Designer updates the canvas live; existing in-flight chains use the prior version (no mid-chain config swap)
- [ ] Channel-priority drag-reorder works on Teams/Slack/email/SMS/Conductor/Conductor-app channel types
- [ ] Form validation refuses invalid combos (admin-only tools on user-keyed nodes; shell on human nodes; CONVERSATION with non-empty whitelist; etc.)
- [ ] Adapter handshake test runs for imported-agent nodes; failure blocks save
- [ ] All Designer changes are admin-signed via wallet-app push (S-150 mode 3) and recorded as VCs in the audit log
- [ ] Graph Designer renders nodes + edges + live traffic for a graph of at least 50 nodes without performance degradation
- [ ] Replay mode plays back actual traffic for an operator-selected time window using Langfuse trace data
- [ ] Trust-tier color coding is consistent: gold (featured) / green (trusted) / yellow (shadow) / red (untrusted) / blue (human) / purple (conductor-as-node)
- [ ] Users in read-only mode can view + replay traffic from their own chains; cannot edit; cannot view chains they didn't initiate
- [ ] Export / import: a graph YAML round-trips through export → import without loss; reproduces an equivalent graph on a fresh conductor
- [ ] Graph import security: an imported graph YAML is validated with the same per-node checks as Node Designer form submission; a YAML specifying admin-only tools (e.g. `shell`) on a user-level node is **rejected** with a validation error naming the violating field; a YAML that sets `trust_tier` to anything other than `untrusted` for a new node is **silently overridden** to `untrusted` (all imported nodes start at `untrusted` regardless of the YAML value); the import flow cannot bypass tool-whitelist invariants enforced by the form
- [ ] CLI parity: every Designer action has a `maistro graph ...` CLI command for headless / scripted use

See `blakematthews-dev/project_maistro` specs/infra/S-159-node-graph-designer.md for full spec.
