---
id: SPEC-228
title: "Observability baseline: logging, metrics, tracing scaffolding (partial vs. ADR-037)"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-06-20
substrate: []
implements:
  - maistro-engine#ADR-037
related: []
supersedes: []
blocks: []
blocked-by: []
contracts: []
tests:
  - packages/maistro-core/tests/test_metrics.py
  - packages/maistro-core/tests/events/test_events.py
layer: Observability
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-228: Observability baseline (partial implementation)

## Context

ADR-037 defines a four-primitive observability taxonomy (traces, metrics, logs, events)
with specific required span names, `maistro_*`-namespaced Prometheus metrics, and
dot-namespaced event topics. `maistro-core/observability/` and `maistro-core/events/`
predate the ADR and provide the four scaffolding *categories*, but use different names
and narrower scope than the ADR's contract. This SPEC documents what exists today,
honestly, without claiming the ADR is fully realized.

## Goals

- Document the actual logging/metrics/tracing/events modules as implemented.
- Enumerate, explicitly, which of ADR-037's required spans/metrics/event topics are
  implemented and which are not, so the gap is traceable rather than assumed closed.

## Non-goals

- Closing the gap (adding the missing spans/metrics/events) — that is future work,
  tracked via the Open Questions / a follow-up SPEC, not this documentation pass.
- Backend selection (Langfuse vs. Arize Phoenix) — per-product Copier knob, out of scope.

## Decision

Implemented today, in `packages/maistro-core/src/maistro/observability/`:

- `logging.py` — `configure_logging()`; structlog JSON/console setup; binds
  `request_id` via contextvars. Does **not** bind `trace_id`/`agent_id` as ADR-037
  requires ("Always carry `trace_id` and `agent_id` when available").
- `metrics.py` — hand-rolled `MetricsRegistry` with its own metric names
  (`http_requests_total`, `llm_requests_total`, `circuit_breaker_state`,
  `tasks_submitted_total`, etc.). None are namespaced `maistro_*` per the ADR's
  naming convention.
- `tracing.py` — a single generic `trace_agent(name)` decorator; OTEL span if available,
  else no-op. Not wired to any of the ADR's mandated span names.
- `middleware.py` — `RequestIDMiddleware`, binds only `request_id` to structlog context.

Events: `packages/maistro-core/src/maistro/events/bus.py` — an in-memory `EventBus`
bounded to 1000 events, with a free-text, ungoverned `event_type` scheme (e.g.
`"agent_fitness"`, `"warden_block"`). This serves a cross-service trigger-bus purpose,
not ADR-037's domain-event taxonomy, and does not persist indefinitely as the ADR
requires for audit value.

### Gap matrix vs. ADR-037

| Required (ADR-037) | Status |
|---|---|
| `maistro_llm_tokens_total`, `maistro_llm_cost_usd_total`, `maistro_request_duration_seconds`, `maistro_security_block_total`, `maistro_quota_remaining_ratio`, `maistro_circuit_state` | Not implemented — no `maistro_*` metrics exist; closest analog is unprefixed `circuit_breaker_state` |
| Spans: `conduit.invoke`, `orchestrator.plan/execute`, `router.select`, `classifier.classify`, `agent.act/delegate`, `tool.call`, `mcp.call`, `memory.read/write/consolidate`, `security.gate`, `quota.check`, `policy.decide` | Not implemented — `trace_agent()` decorator exists but no call site uses these names |
| Event topics: `agent.lifecycle`, `task.lifecycle`, `security.violation`, `policy.decision`, `memory.consolidation`, `quota.exhausted` | Not implemented — `EventBus` uses an unrelated free-text scheme |
| structlog with `trace_id`/`agent_id` propagation | Partial — only `request_id` is bound |
| Indefinite event persistence | Not implemented — in-memory, 1000-event cap |
| Sampling/retention config | Not found |

## Acceptance criteria

- [x] A logging module exists and configures structlog with request-scoped context
- [x] A metrics registry exists and exposes counters/gauges/histograms (with different names than ADR-037 specifies)
- [x] A tracing decorator exists with OTEL span fallback
- [x] An event bus exists for cross-component signaling
- [ ] The 6 ADR-037-named `maistro_*` metrics are emitted
- [ ] The ~14 ADR-037-required spans are instrumented at their named call sites
- [ ] The 6 ADR-037-named event topics are emitted
- [ ] `trace_id`/`agent_id` are bound to log context
- [ ] Events persist indefinitely (audit requirement)
- [ ] Sampling/retention policy is configured

## Testing

- `packages/maistro-core/tests/test_metrics.py` — tests the local registry's own
  (non-ADR-037) metric names.
- `packages/maistro-core/tests/events/test_events.py` (28 tests) — covers the
  trigger/bus mechanism, not the ADR-037 taxonomy.
- No test in the repo references any ADR-037 metric, span, or event name.

## Open questions

- Should the existing `metrics.py`/`events/bus.py` be extended in place to add the
  ADR-037 names alongside the existing ones, or should ADR-037 compliance be a
  separate adapter layer?
- Who owns wiring the ~14 required spans across `conduit`, `orchestrator`, `router`,
  `classifier`, `agents`, `tools`, `memory`, `security`, `quota` — likely one PR per
  subsystem rather than one big PR, per ADR-037's own "same PR as the public API"
  consequence.
- Should this SPEC be split into per-primitive SPECs (traces, metrics, events) once
  work starts, so each can progress through the lifecycle states independently?

## References

- `packages/maistro-core/src/maistro/observability/logging.py`
- `packages/maistro-core/src/maistro/observability/metrics.py`
- `packages/maistro-core/src/maistro/observability/tracing.py`
- `packages/maistro-core/src/maistro/observability/middleware.py`
- `packages/maistro-core/src/maistro/events/bus.py`
- `packages/maistro-core/tests/test_metrics.py`
- `packages/maistro-core/tests/events/test_events.py`
