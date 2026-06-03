---
id: ADR-091
title: Durable execution as the agent substrate
repo: maistro-engine
kind: adr
status: Proposed
created: 2026-06-02
accepted: null
implemented: null
substrate:
  - maistro-engine#ADR-038   # reliability taxonomy (Accepted)
  - maistro-engine#ADR-062   # graph execution protocol (Accepted)
implements: []
related:
  - maistro-engine#ADR-049   # shadow-git rollback
  - maistro-engine#ADR-055   # observability replay + PII tiers
  - maistro-engine#ADR-056   # task crash recovery
  - maistro-engine#ADR-071   # task planner / orchestration
  - maistro-engine#ADR-039   # external-adoption policy (inspirations)
contracts: []
tests: []
layer: Foundation
owners:
  - '@BlakeMatthews-dev'
---

# ADR-091: Durable execution as the agent substrate

## Context

Durable, resumable, replayable execution is already decided across a **cluster** of
ADRs — ADR-038 (reliability) and ADR-062 (graph execution protocol) are **Accepted**;
ADR-049 (rollback), ADR-055 (replay), ADR-056 (crash recovery), and ADR-071
(orchestration) are **Proposed** — and partially implemented in
`packages/maistro-core/src/maistro/graph/durable_runs/`.

But there is **no single statement of the stance**, and durability is articulated
mostly at the **node** level (ADR-062, `durable_runs/`) rather than the
**run / conductor** level. The pattern is convergent with durable-workflow engines
(LangGraph) and with event-sourcing as a persistence primitive.

## Decision

**An agent / task run is a durable, resumable, replayable workflow — not a stateless
function call.** Node-level durability (ADR-062, `durable_runs/`) is elevated to the
**run / conductor level**: a run survives process restart, resumes from its last
durable point, and can be replayed against recorded responses for debugging and audit.

This ADR is the **umbrella** that composes the cluster into one stance:

| Layer | ADR | Role |
|---|---|---|
| Resilience base | **ADR-038** | retries, circuit breakers, fallbacks |
| Node-level durable execution | **ADR-062** | DAG/node protocol + `durable_runs/` |
| Run-level resume | **ADR-056** | auto-resume on conductor restart; crash-loop quarantine |
| Replay | **ADR-055** | re-run orchestration against recorded responses |
| Rollback | **ADR-049** | shadow-git workspace rollback on crash |
| Orchestration | **ADR-071** | SuperPlanner waves as the run structure |

## Inspiration

Convergent with **LangGraph** (durable, checkpointed, multi-actor graph execution) and
**event-sourcing** as a persistence primitive (cf. OpenHands V1 SDK). Patterns
referenced, not code adopted — per ADR-039 / `INSPIRATIONS.md`.

## Scope

Applies to **task / mission / DAG runs** — the work that must survive crashes and be
auditable. The interactive **chat** surface stays intentionally lighter (single
request/response) and is **not** required to be a durable workflow.

## Consequences

- **Reliability:** resume-after-crash; long-running work is not lost. Addresses the
  dominant class of agent incidents (state management).
- **Debuggability:** time-travel replay of orchestration against recorded responses
  (ADR-055), bounded to orchestration bugs (not prompt/model re-execution).
- **Auditability — the key property:** durable + replayable means a run is
  **reconstructable after the fact.** This is the rare capability axis that
  *reinforces* our security / interpretability / auditability posture rather than
  trading against it — durability is simultaneously more reliable **and** more
  auditable.
- **Implementation:** the primitives exist at node level (`durable_runs/`); the
  remaining work is elevating them to the run/conductor loop and ratifying the
  Proposed cluster members.

## Status / acceptance

Proposed. Acceptance is coupled to ratifying the cluster — ADR-049, ADR-055, ADR-056,
ADR-071 → Accepted. ADR-038 and ADR-062 are already Accepted foundations.
