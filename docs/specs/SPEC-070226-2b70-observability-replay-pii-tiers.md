---
id: SPEC-070226-2b70
title: "Observability extensions: replayable LLM/tool proxies and PII sensitivity-tier routing"
repo: maistro-engine
kind: spec
status: Implemented
created: 2026-07-02
substrate:
  - maistro-engine#ADR-037
  - maistro-engine#ADR-050
  - maistro-engine#ADR-055
  - maistro-engine#SPEC-228
implements:
  - maistro-engine#ADR-055
related:
  - maistro-engine#ADR-053
  - maistro-engine#ADR-056
  - maistro-engine#SPEC-223
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests:
  - packages/maistro-core/tests/observability/test_tiers.py
  - packages/maistro-core/tests/observability/test_replay.py
  - packages/maistro-core/tests/observability/test_proxy.py
layer: Observability
owners:
  - '@BlakeMatthews-dev'
---

# SPEC-070226-2b70: Observability extensions — replayable proxies and PII sensitivity tiers

## Context

ADR-055 extends ADR-037 with two capabilities: (1) recorded-response replay — substrate-owned
proxies record every LLM call and tool call so orchestration code can be deterministically
re-executed against recorded responses; and (2) PII sensitivity tiers — `normal`/`sensitive`/
`secret` tags that route event payloads to different storage/retention regimes.

This SPEC realizes both, and resolves ADR-055's five open questions with concrete choices
(recorded there as recommendations; locked in here).

## Goals

- `ReplayableLLMClient` and `ReplayableToolDispatcher` proxies that record args + responses into
  the ADR-037 event log, carrying the active trace/span ids.
- `replay(trace_id)` re-runs orchestration against recorded responses without re-invoking LLMs
  or tools.
- `SensitivityTier` tag on tool registrations (extends ADR-050 `ToolRegistration`) and recipe-level
  prompt/response tagging (ADR-053 overlay-mergeable, `merge: replace`).
- Tier routing: `normal` → standard event log; `sensitive` → KMS-encrypted payload column with
  access audit; `secret` → hash + metadata only, payload never persisted.
- Built-in PII detector on `normal`-tagged events (reuses SPEC-223's pattern catalogue): fail
  loudly in dev, redact-and-log + `pii.unexpected_match` event in prod.
- Registration-time enforcement: an agent whose tools/LLM client bypass the proxies fails to
  register; CI grep forbids direct `litellm.completion` in engine code.

## Non-goals

- Prompt/model-bug replay (temperature-0 + frozen RNG deterministic re-execution) — ADR-055
  explicitly bounds replay to orchestration debugging.
- Tenant-key encryption for the `secret` tier (ADR-055 OQ4 — deferred, per its own recommendation).
- External streaming of recorded events (Kafka etc.).

## Decision

### Decisions on ADR-055's open questions

1. **Sealed store backend**: same Postgres schema, KMS-encrypted `payload_encrypted` column,
   application-layer access policy (per ADR-055's recommendation).
2. **PII detector**: built-in pattern set from SPEC-223's catalogue + a `register_pattern()`
   extension hook.
3. **Replay scope**: recorded-response replay only; shares the event log with ADR-056 resume but
   is a distinct operation (`replay` re-runs orchestration; `resume` continues execution).
4. **Tenant-key encryption**: deferred.
5. **Recording overhead**: async best-effort writer with a bounded buffer (default 10k events);
   on buffer overflow, drop `normal`-tier records with a `observability.record_dropped` counter —
   never block the hot path. `sensitive`/`secret` records are never dropped silently (blocking
   write with 100ms budget, then error).

### Proxy interfaces

```python
class SensitivityTier(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    SECRET = "secret"

@dataclass(frozen=True)
class ReplayEvent:
    trace_id: str
    span_id: str
    seq: int                       # monotonic per trace — replay ordering key
    kind: Literal["llm", "tool"]
    request_hash: str              # sha256 of canonicalised args
    payload: dict | None           # None for secret tier
    tier: SensitivityTier

class ReplayableLLMClient(Protocol):
    async def call(self, request: LLMRequest) -> LLMResponse: ...
    async def replay(self, trace_id: str) -> AsyncIterator[ReplayEvent]: ...

class ReplayableToolDispatcher(Protocol):
    async def call(self, tool_call: ToolCall) -> ToolResult: ...
    async def replay(self, trace_id: str) -> AsyncIterator[ReplayEvent]: ...
```

Replay mode: proxies are constructed for a `replay_source=trace_id`
(`create_replay_proxies(store, replay_source)` builds an LLM + tool proxy pair sharing one
`ReplaySession` cursor); the proxies then serve recorded responses matched by
`(seq, request_hash)` and never touch the inner client. A request whose hash does not match the
recorded one at that position raises `ReplayDivergenceError` (the orchestration bug you were
looking for, surfaced as the diff between recorded and attempted request).

### Tier routing and storage

Storage is realised as a `RecordStore` protocol (`maistro.observability.replay`), not a fixed
SQL schema: `InMemoryRecordStore` is the reference implementation, and a Postgres store (the
originally sketched `tier`/`payload_encrypted`/`payload_hash` columns + `sealed_access_audit`
table) plugs in behind the same protocol. KMS is likewise realised as injected
`encryptor`/`decryptor` callables (`bytes -> bytes`) so products wire a real KMS envelope
without a hard dependency in core.

- `normal`: full payload stored as-is (ADR-037 retention).
- `sensitive`: payload encrypted via the injected encryptor; readable only through
  `RecordStore.read_sensitive_payload(trace_id, seq, accessor, reason)`, which writes an
  `AccessAuditRecord` per read. (Scope enforcement and the 30-day retention job live with the
  Postgres store implementation.)
- `secret`: `request_hash` + metadata only; payload bytes never persisted anywhere.

### Registration-time enforcement

- `ToolRegistration` gains `sensitivity: SensitivityTier = NORMAL` (extends ADR-050 shape).
- Agent factory asserts the wired LLM client and tool dispatcher are the proxy implementations
  (`isinstance` on the protocol's registered concrete types); otherwise `AgentRegistrationError`.
- CI: `grep -rn "litellm.completion\|litellm.acompletion" packages/maistro-core/src` outside
  `observability/proxy.py` fails the lint job.

**Wiring status:** the library layer is implemented in `maistro.observability`
(`tiers.py`, `replay.py`, `proxy.py`). Container/agent-factory wiring and the CI grep rule are
follow-up work outside this change's scope (container.py deliberately untouched); today no core
code calls `litellm` directly, so the grep rule can be added to ci.yml at wiring time.

## Acceptance criteria

- [x] Every LLM/tool call through the proxies writes a `ReplayEvent` carrying the active ADR-037
      `trace_id`/`span_id` and a per-trace monotonic `seq`.
- [x] `replay(trace_id)` yields events in original `seq` order (property test).
- [x] Re-running an orchestration path in replay mode never invokes the real LLM or tool
      (asserted via a poisoned real client that raises if touched).
- [x] A divergent request during replay raises `ReplayDivergenceError` naming the seq and hash diff.
- [x] `sensitive`-tagged payloads are only readable via the scoped read path; each read writes an
      access-audit row.
- [x] `secret`-tagged calls persist hash + metadata only — no payload bytes in any table (property
      test over generated payloads).
- [x] PII detector flags a `normal` event containing an email/card/secret-shaped token: raises in
      dev mode, redacts + emits `pii.unexpected_match` in prod mode.
- [ ] Direct `litellm` invocation in engine code fails CI; an agent wired with a non-proxy client
      fails registration. *(Deferred to container/agent-factory wiring + ci.yml grep rule — see
      wiring status above.)*
- [x] Hot path is never blocked by recording for `normal` tier (buffer-overflow test drops records
      and increments `observability.record_dropped`).

## Testing

- Unit: tier routing per tag; hash computation stability; bounded-buffer overflow behaviour.
- Integration: record a small orchestration run (2 LLM calls, 3 tool calls), replay it, assert
  identical orchestration decisions and zero real invocations.
- Property (Hypothesis, per ADR-055): for any sequence of recorded LLM + tool calls, replay yields
  the same logical event order; for any payload, secret tier persists no payload bytes.
- Reuses SPEC-223 redaction fixtures for the PII detector patterns.

## Open questions

- Whether replay should be exposed as a CLI (`maistro replay <trace_id>`) in this phase or only as
  a library API (leaning: library first, CLI follow-up).

## References

- [ADR-055: Observability extensions](../adr/ADR-055-observability-replay-and-pii-tiers.md)
- [ADR-037: Observability](../adr/ADR-037-observability-taxonomy.md)
- [SPEC-223: Secret redaction](SPEC-223-secret-redaction.md)
- [SPEC-228: Observability baseline gaps](SPEC-228-observability-baseline-gaps.md)
