---
id: SPEC-208
title: Foreign harness adapter — HarnessRunner slot and agent/skill format adapters
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-06-15
substrate:
  - maistro-engine#ADR-101
  - maistro-engine#SPEC-184
  - maistro-engine#ADR-058
  - maistro-engine#ADR-062
implements:
  - maistro-engine#ADR-101
related:
  - maistro-engine#ADR-083
  - maistro-engine#ADR-019
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Orchestration
owners:
  - '@BlakeMatthews-dev'
history:
  - status: Proposed
    date: 2026-06-15
---

# SPEC-208: Foreign harness adapter

**Implements:** ADR-101. ADR-101 decides *that* maistro wraps foreign agent harnesses behind a
`harness_runner` slot, can be wrapped the same way by other orchestrators, and adopts an
import-wide/export-narrow posture for agent and skill formats. This spec defines *how*: the slot
and protocol shapes, the safety wrapper, the import adapter catalog, the export artifact, and the
hierarchical-orchestration wiring.

---

## Context

SPEC-184 establishes `CapabilitySlot` / `CapabilityProvider` / `CapabilityRegistry`
(`packages/maistro-core/src/maistro/capabilities/`) as the one abstraction for installable,
toggleable, swappable capabilities, with a declared `FallbackPolicy` per slot
(`capabilities/types.py:9-14`). This spec adds one new slot, `harness_runner`, and the adapter
machinery around it.

## Decision

### 1. The `harness_runner` slot and the `HarnessRunner` protocol

```python
# capabilities/types.py — slot declaration
SlotSpec(name="harness_runner", fallback_policy=FallbackPolicy.SAFE_NOOP)
```

```python
# capabilities/protocols.py (new) — session protocol, layered on CapabilityProvider
@runtime_checkable
class HarnessRunner(CapabilityProvider, Protocol):
    """Adapter over a foreign agent harness's session/process API."""

    async def start_session(self, agent_spec: AgentConfig, *, workdir: str) -> str:
        """Start (or attach to) a harness session; returns a session_id."""
        ...

    async def send(self, session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """One turn: send messages, return the harness's response envelope."""
        ...

    async def stream(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """Stream incremental events (tokens, tool calls, status) for a session."""
        ...

    async def stop(self, session_id: str) -> None:
        """Terminate the underlying process/session."""
        ...
```

`HarnessRunner.send()` returns the same response shape the `Conduit` already normalizes at
`conduit.py:130-133` (a dict, or a string coerced via `_stop_response`), so a session-backed agent
is dispatched identically to a native one — the `Conduit`'s call to `agent.handle(...)`
(`conduit.py:120`) does not change; what changes is that `agent.handle` for a harness-backed
`AgentConfig` delegates to `registry.resolve("harness_runner")` and calls `send()`.

Multiple `HarnessRunner` providers may be registered (one per foreign harness — `pi`, `openclaw`,
`claude_code`, `codex`); `CapabilityRegistry.activate("harness_runner", name)` selects which one an
`AgentConfig` binds to, same as any other slot (`capabilities/registry.py:52-58`).

### 2. Safety wrapping

Every `HarnessRunner` provider implementation is required to compose three existing primitives —
no new trust-boundary type is introduced:

| Layer | Existing primitive | Applied to |
|---|---|---|
| Process isolation | `maistro.tools.sandbox` | the foreign harness's subprocess: filesystem + network access |
| Inbound scan | `maistro.security.warden.detector` (Warden) | every `messages` payload before `send()` |
| Outbound policy | `maistro.security.sentinel` (Sentinel) | every tool-call/action the harness reports in its response/stream, before maistro acts on it or relays it |
| Degradation | `capabilities/registry.py:91-128` resolution order | unhealthy/crashed harness → `SAFE_NOOP` → typed `Unavailable` (`capabilities/types.py:34-39`) |

A `HarnessRunner` provider's `requires()` (`capabilities/protocols.py:27-29`) declares the binary
or SDK the foreign harness needs (e.g. `pi`, `openclaw`, `claude`, `codex`) plus the sandbox
profile name; `healthcheck()` checks both the binary's presence and the sandbox's reachability.

### 3. Import adapter catalog

```python
# maistro.agents.importers / maistro.skills.importers (new subpackages)
class AgentImporter(Protocol):
    format: str                       # "pi" | "openclaw" | "claude_code" | "codex" | "openai_assistant"
    def detect(self, source: dict | str) -> bool: ...
    def to_agent_config(self, source: dict | str) -> AgentConfig: ...

class SkillImporter(Protocol):
    format: str                       # "claude_code_skill" | "mcp_manifest" | "openai_tool"
    def detect(self, source: dict | str) -> bool: ...
    def to_skill_definitions(self, source: dict | str) -> list[SkillDefinition]: ...
```

| Source format | Importer | Target |
|---|---|---|
| Pi agent/task config | `agents.importers.pi` | `AgentConfig` (binds to `harness_runner="pi"`) |
| OpenClaw agent config | `agents.importers.openclaw` | `AgentConfig` (binds to `harness_runner="openclaw"`) |
| Claude Code `SKILL.md` / `.claude/agents/*.md` | `skills.importers.claude_code` | `SkillDefinition` — thin wrapper, `skills/parser.py` already parses this frontmatter shape |
| Codex CLI / `AGENTS.md` | `agents.importers.codex` | `AgentConfig` (binds to `harness_runner="codex"`) |
| OpenAI Assistants / Agent SDK spec | `agents.importers.openai_assistant` | `AgentConfig` + `skills.importers.openai_tool` for its tool list |
| MCP server/tool manifest | `skills.importers.mcp` | `list[SkillDefinition]` via `merge_into_tools()` (`skills/loader.py:88-99`) |

A registry (`ImporterRegistry`, mirroring `CapabilityRegistry`'s shape but unkeyed by slot) tries
each importer's `detect()` in registration order and applies the first match. The marketplace
connectors (`skills/connectors.py`) gain an `import_format: str | None` field on `SkillMetadata` so
a catalog entry can name its format explicitly and skip detection.

### 4. Export: one target format

```python
# maistro.agents.export (new)
def export_agent(agent: AgentConfig, skills: list[SkillDefinition]) -> ExportBundle:
    """Returns an MCP server manifest exposing `agent`'s skills as MCP tools,
    plus a SKILL.md describing the agent, for any MCP- or SKILL.md-aware harness."""
```

`ExportBundle` is `{mcp_manifest: dict, skill_md: str}`. There is exactly one export path,
regardless of how the agent was imported (native, Pi, OpenClaw, ...). A maistro-defined agent
consumed from Pi/OpenClaw/Codex goes through that harness's own MCP client — maistro does not
special-case the consumer.

### 5. Hierarchical orchestration mechanics

**Outbound (maistro drives a foreign harness):** ADR-062's graph executor gains a `NodeStrategy`
implementation, `HarnessNodeStrategy`, whose `execute()` resolves `harness_runner` from the
`CapabilityRegistry`, calls `start_session()` once per `GraphRun`, and `send()` per `NodeRun` —
recording the same per-node telemetry (input, output, timing, error classification) as native
strategies (ADR-062 `NodeRun`). `IterationBudget` applies uniformly; a foreign harness node cannot
exceed the shared iteration budget.

**Inbound (maistro is driven by another orchestrator):** a new `hive-conductor` route,
`POST /v1/harness/sessions`, implements the `HarnessRunner` HTTP shape
(`start_session` → returns `session_id`; `POST /v1/harness/sessions/{id}/send`; `GET
/v1/harness/sessions/{id}/stream` SSE; `DELETE /v1/harness/sessions/{id}`). Internally it wraps the
existing `Conduit.route_request()` (`conduit.py:68`) — the remote orchestrator sees a
`HarnessRunner`-shaped session; maistro internally still runs its normal classify → route →
`agent.handle` pipeline. Auth uses the existing B2B service-key scopes (`maistro.auth`); a
dedicated scope (`harness:session`) gates this route.

## Acceptance criteria

- [ ] `harness_runner` `SlotSpec` defined with `FallbackPolicy.SAFE_NOOP`; `HarnessRunner` Protocol
      added to `capabilities/protocols.py`, `mypy --strict` clean.
- [ ] At least one real `HarnessRunner` provider (e.g. `pi` or `openclaw`) implements
      `start_session`/`send`/`stream`/`stop` over a sandboxed subprocess; `healthcheck()` reflects
      binary presence + sandbox reachability.
- [ ] Every `send()` call passes its `messages` through Warden before reaching the subprocess, and
      every action in the harness's response passes through Sentinel before being surfaced —
      asserted via a fake harness that emits a flagged payload and a flagged action.
- [ ] A crashed/unhealthy `HarnessRunner` provider degrades the slot to `SAFE_NOOP`
      (`Unavailable`); the calling agent/graph node receives the typed result, never an exception.
- [ ] At least two `AgentImporter`/`SkillImporter` implementations exist (one agent format, one
      skill format — e.g. Claude Code `SKILL.md` and one of Pi/OpenClaw/Codex), each with
      `detect()` + `to_agent_config()`/`to_skill_definitions()` round-tripped in a unit test.
- [ ] `export_agent()` produces a valid MCP server manifest (validated against the MCP schema) and
      a `SKILL.md` whose frontmatter `skills/parser.py` can re-parse — for an agent that was
      itself imported via one of the new importers (proves the import→export round trip through
      the internal representation).
- [ ] `HarnessNodeStrategy` runs as a graph node under ADR-062's `GraphRun`, recording `NodeRun`
      telemetry identically to a native strategy, and respects `IterationBudget`.
- [ ] `POST /v1/harness/sessions` (+ send/stream/stop) is reachable with a `harness:session`
      service-key scope and rejects requests without it; a session created this way produces the
      same response shape as a local `Conduit.route_request()` call for the same messages.

## Testing

- Unit: each `AgentImporter`/`SkillImporter` `detect()`/`to_*()`; `export_agent()` MCP manifest +
  `SKILL.md` shape; `HarnessRunner` registry resolution (healthy / unhealthy / disabled →
  `SAFE_NOOP`).
- Contract: `HarnessRunner` Protocol conformance for each provider (boundary); Warden/Sentinel
  wrapping order is enforced regardless of provider (behavioral) — a fake provider cannot bypass
  the wrapper.
- Integration: outbound — a `HarnessNodeStrategy` node driving a stub `HarnessRunner` inside a
  `GraphRun`; inbound — `POST /v1/harness/sessions/.../send` round-tripping through
  `Conduit.route_request()` against an in-memory container.
- Property (formal/, per repo convention): "a `harness_runner` provider that is absent, disabled,
  or unhealthy never causes a graph node or `Conduit` call to raise" (extends the SPEC-184
  `safe_noop` invariant to this slot).

## Open questions

- Per-harness session lifecycle limits (idle timeout, max concurrent sessions per host) —
  resource-management policy, likely belongs with the follow-up stateful policy engine
  (ADR-101, Follow-ups) rather than this spec.
- Whether `HarnessNodeStrategy` needs its own `priority_tier` interaction with
  `determine_execution_tier` (`conduit.py:24-33`) when a foreign harness reports its own
  cost/latency profile.
- Exact MCP manifest versioning/compatibility story as the MCP spec evolves — `export_agent()`
  should target a pinned MCP schema version with a documented upgrade path.

## References

- [ADR-101: Foreign harness adapters, hierarchical orchestration, and agent/skill portability](../adr/ADR-101-foreign-harness-adapters-and-portability.md)
- [SPEC-184: Modular capability platform](SPEC-184-modular-capability-platform.md)
- [ADR-058: A2A delegation protocol](../adr/ADR-058-a2a-delegation-protocol.md)
- [ADR-062: Graph execution protocol](../adr/ADR-062-graph-execution-protocol.md)
- [ADR-083: Skills and MCP gateway trust](../adr/ADR-083-skills-mcp-trust.md)
- Seams: `capabilities/protocols.py:11-31`, `capabilities/registry.py:91-128`,
  `capabilities/types.py:9-39`, `conduit.py:24-33,68,120,130-133`, `skills/parser.py`,
  `skills/loader.py:23-66,88-99`, `skills/connectors.py`, `a2a/delegate.py`, `a2a/guest_peers.py`
