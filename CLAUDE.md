# CLAUDE.md — Maistro Engine

**Project:** Maistro Engine — Shared Python runtime for AI agent platforms
**License:** Apache 2.0
**Python:** 3.12+

---

## Architecture

Monorepo with 6 packages + the hive-conductor app. The canonical shared runtime that powers Agent Conductor, Agent Stronghold, and Canvas Studio.

```
packages/
├── maistro-core/      # Shared library: pip install maistro-core
├── maistro-canvas/    # Standalone book builder (frontend + canvas engine)
├── maistro-server/    # FastAPI app (replaces conductor-router)
├── maistro-turing/    # Autonoetic self-model extensions
├── maistro-evolve/    # Elo tournament optimizer for agent self-improvement
├── hive-conductor/    # Agent Conductor app (FastAPI backend + React frontend)
└── maistro-bootstrap/ # Bootstrap stub (WIP)
```

### Product relationship

```
maistro-engine (this repo)
  │
  ├─→ Agent Conductor (household/personal)  — hive-conductor (FastAPI backend + React frontend)
  ├─→ Agent Stronghold (enterprise)         — pip install maistro-core + multi-tenant layer
  └─→ Canvas Studio (standalone book builder) — maistro-canvas + P40 image gen server
```

**ADR-019** defines the canonical source split: maistro-core = shared runtime, Stronghold = multi-tenant only. 43 ADRs total (ADR-000–ADR-042); notable recent ones: ADR-036 (ontology), ADR-038 (reliability), ADR-042 (graph execution protocol).

### Naming convention

- `AgentConfig`, `AgentError` — canonical names in maistro-core
- `MaistroConfig`, `MaistroError`, `StrongholdError` — backwards-compat aliases

### maistro-core (the library)

Every subsystem is importable. Consumers add `maistro-core` to their requirements.

| Subsystem | Import | What |
|-----------|--------|------|
| **Memory** | `maistro.memory` | Learnings, episodic, scopes, outcomes |
| **Security** | `maistro.security` | Warden (threat detection), Sentinel (policy), PII filter |
| **Classifier** | `maistro.classifier` | 3-phase intent: keywords → LLM → complexity |
| **Router** | `maistro.router` | Scoring formula + RouterEngine |
| **Agents** | `maistro.agents` | Base class, factory, strategies, roster |
| **Builders** | `maistro.builders` | Pipeline: spec → tests → code → review |
| **A2A** | `maistro.a2a` | Agent-to-agent delegation + lifecycle |
| **Skills** | `maistro.skills` | Marketplace, Forge, parser, canary |
| **Persistence** | `maistro.persistence` | PostgreSQL stores (learnings, agents, audit, quota) |
| **Protocols** | `maistro.protocols` | Abstract interfaces for DI |
| **Types** | `maistro.types` | Shared dataclasses |
| **Orchestrator** | `maistro.orchestrator` | Super Planner + Master Orchestrator |
| **Container** | `maistro.container` | DI wiring + `route_request()` |
| **Conduit** | `maistro.conduit` | Request pipeline: classify → route → agent.handle |
| **Auth** | `maistro.auth` | B2B service keys with scoped permissions |
| **Events** | `maistro.events` | Bus, handlers, recipes, triggers |
| **Quota** | `maistro.quota` | Token usage tracking per provider per billing cycle |
| **Sessions** | `maistro.sessions` | Conversation history with TTL pruning |
| **Intents** | `maistro.agents.intents` | task_type → agent_name routing table |
| **Graph** | `maistro.graph` | DAG execution: node types, executor, optimizer, phases (ADR-042) |
| **Ontology** | `maistro.ontology` | Semantic object layer and registry (ADR-036) |
| **Resilience** | `maistro.resilience` | Reliability taxonomy and circuit-breaking (ADR-038) |
| **Identity** | `maistro.identity` | Identity management |
| **Scheduling** | `maistro.scheduling` | Scheduling (distinct from the scheduler/ placeholder) |
| **Prompts** | `maistro.prompts` | Prompt templates |

### maistro-canvas (standalone book builder)

```
packages/maistro-canvas/
├── src/maistro_canvas/      # Python library
│   ├── types.py             # Canvas types + 20 domain errors
│   ├── protocols.py         # CanvasStore, ImageGenClient, CompositorService
│   ├── auth.py              # Standalone API key auth
│   └── canvas/              # Canvas engine (from Stronghold spec 1189)
│       ├── tool.py          # In-process canvas tool (903 lines)
│       ├── executor.py      # Canvas action executor
│       ├── compositor.py    # PIL-based RGBA layer assembly
│       ├── store.py         # PostgreSQL canvas store
│       └── routes.py        # REST API routes
├── frontend/                # React + Express POC
│   ├── src/                 # React UI (14 components)
│   ├── server/              # Python backend
│   │   ├── mcp/             # Canvas pipeline, illustration, refinement
│   │   ├── lulu/            # Lulu print-on-demand integration
│   │   ├── models/          # SQLAlchemy models (11 tables)
│   │   └── templates/       # Story templates
│   └── SPEC.md
└── agents/davinci/          # Da Vinci agent definition
```

### maistro-turing (autonoetic self-model)

Implementation in progress: Mood, HEXACO personality, drives, proactive producers (blog, reflection, curiosity, emotion). Bridges to maistro-core for memory and security. Note: tests/ directory exists but is empty; maistro-turing is not exercised in CI.

---

## Development Commands

```bash
# Install for development (from repo root — uv.lock is the source of truth)
uv sync
# Or with pip:
pip install -e packages/maistro-core
pip install -e packages/maistro-server
pip install -e packages/maistro-turing
pip install -e packages/maistro-canvas
pip install -e packages/maistro-evolve

# Run core tests (~375 tests)
PYTHONPATH=packages/maistro-core/src pytest packages/maistro-core/tests/ -q

# Run all package tests (~525 total; maistro-turing has no tests yet)
PYTHONPATH=packages/maistro-core/src:packages/maistro-canvas/src:packages/maistro-turing/src \
  pytest packages/maistro-core/tests packages/maistro-server/tests \
  packages/maistro-canvas/tests packages/maistro-evolve/tests -q

# Formal property-based conformance tests (separate CI flow — formal-conformance.yml)
PYTHONPATH=packages/maistro-core/src pytest formal/ -q

# Lint (note: CI targets root src/ only; run manually for packages/)
ruff check packages/
mypy packages/ --strict

# Verify all core imports
PYTHONPATH=packages/maistro-core/src python3 -c "
from maistro.container import Container, create_container
from maistro.conduit import Conduit
from maistro.types import AgentConfig, AgentError
from maistro.memory.learnings.store import InMemoryLearningStore
from maistro.security.warden.detector import Warden
from maistro.classifier.engine import ClassifierEngine
from maistro.router.selector import RouterEngine
from maistro.agents.intents import IntentRegistry
from maistro.quota.tracker import InMemoryQuotaTracker
from maistro.sessions.store import InMemorySessionStore
print('OK')
"

# Verify canvas imports
PYTHONPATH=packages/maistro-core/src:packages/maistro-canvas/src python3 -c "
from maistro_canvas import CanvasRecord, CanvasStore, ImageGenClient
from maistro_canvas.types import validate_canvas_dimensions, CanvasError
print('OK')
"
```

---

## Key Design Decisions

1. **Library-first, app is optional.** Core is a pure Python library. FastAPI app is a thin wrapper.
2. **Protocol-driven DI.** All business logic depends on protocols (abstract interfaces), never concrete implementations.
3. **Agents are data.** An agent is rows in a store, prompts in YAML. The runtime is shared.
4. **Scoring formula.** `quality^(qw*p) / cost^cw` with scarcity-based cost and task-type speed bonuses.
5. **Memory must forget.** Decay without reinforcement, weight floors for wisdom/regrets.
6. **All input is untrusted.** Warden scans at every trust boundary. Sentinel validates tool calls.
7. **No org_id in maistro-core.** Multi-tenant isolation is Stronghold-specific. Scope isolation (global → team → user → agent → session) is kept.
8. **Canvas Studio is standalone.** Runs on a mini-PC with a P40 image gen server. No Conductor or Stronghold required.

---

## File Layout

```
maistro-engine/
├── packages/
│   ├── maistro-core/
│   │   ├── pyproject.toml
│   │   └── src/maistro/
│   │       ├── agents/          # base, factory, strategies, roster, intents
│   │       ├── a2a/             # delegate, lifecycle, guest_peers
│   │       ├── auth/            # B2B service keys
│   │       ├── builders/        # contracts, runtime, orchestrator, spec, verifier
│   │       ├── classifier/      # engine, keyword, llm_fallback, complexity
│   │       ├── config/          # settings, loader
│   │       ├── conduit.py       # Request pipeline
│   │       ├── container.py     # DI wiring
│   │       ├── events/          # bus, handlers, recipes
│   │       ├── integrations/    # HA, CoinSwarm, Turing bridges
│   │       ├── memory/          # learnings, episodic, scopes, outcomes
│   │       ├── observability/   # logging, metrics, tracing
│   │       ├── orchestrator/    # Super Planner, Master Orchestrator
│   │       ├── persistence/     # PostgreSQL stores
│   │       ├── protocols/       # abstract interfaces
│   │       ├── quota/           # billing, tracker
│   │       ├── router/          # scorer, selector, filter, scarcity, speed
│   │       ├── scheduler/       # placeholder
│   │       ├── security/        # warden, sentinel, gate, auth
│   │       ├── sessions/        # conversation history
│   │       ├── skills/          # marketplace, forge, parser, canary, connectors
│   │       ├── tasks/           # queue, runner, models
│   │       ├── tools/           # sandbox, git, browser
│   │       ├── types/           # AgentConfig, AgentError, shared dataclasses
│   │       ├── graph/           # DAG execution: node, executor, optimizer, phases (ADR-042)
│   │       ├── ontology/        # Semantic object layer, registry (ADR-036)
│   │       ├── resilience/      # Reliability taxonomy, circuit-breaking (ADR-038)
│   │       ├── identity/        # Identity management
│   │       ├── scheduling/      # Scheduling (separate from scheduler/ placeholder)
│   │       └── prompts/         # Prompt templates
│   │
│   ├── maistro-canvas/
│   │   ├── pyproject.toml       # depends: maistro-core
│   │   ├── frontend/            # React + Express book builder POC
│   │   ├── agents/davinci/      # Da Vinci agent definition
│   │   └── src/maistro_canvas/
│   │       ├── types.py         # Canvas types + domain errors
│   │       ├── protocols.py     # CanvasStore, ImageGenClient, CompositorService
│   │       ├── auth.py          # Standalone auth
│   │       └── canvas/          # executor, compositor, store, routes, tool
│   │
│   ├── maistro-server/
│   │   ├── pyproject.toml       # depends: maistro-core
│   │   └── src/maistro_server/
│   │       ├── api/             # HTTP routes
│   │       └── main.py          # FastAPI app
│   │
│   ├── maistro-turing/
│   │   ├── pyproject.toml       # depends: maistro-core
│   │   └── src/maistro_turing/
│   │       ├── bridge.py        # Adapters to maistro-core
│   │       ├── self_model.py    # Autonoetic identity
│   │       ├── runtime.py       # Actor, chat, config
│   │       └── producers.py     # Blog, reflection, curiosity, emotion
│   │
│   ├── maistro-evolve/
│   │   ├── pyproject.toml
│   │   └── src/maistro_evolve/  # Elo tournament optimizer (crossover, mutate, fitness, harness)
│   │
│   └── hive-conductor/          # Agent Conductor app (no pyproject.toml — requirements.txt)
│       ├── backend/             # FastAPI app
│       │   ├── main.py          # Entrypoint + route registration
│       │   ├── routes/          # agents, audit, chat, cli, containers, dags, mcp, memory…
│       │   ├── models/          # SQLAlchemy models
│       │   ├── middleware/      # Auth middleware
│       │   ├── services/        # Business logic
│       │   ├── adapters/        # Langfuse telemetry, noop
│       │   └── requirements.txt
│       └── frontend/            # React SPA
│
├── formal/                      # Property-based conformance tests (Hypothesis); separate CI flow
├── docs/adr/                    # Architecture Decision Records (ADR-000 through ADR-042)
├── src/maistro/                 # Old layout (agent spec/spawner/recipes + model pricing)
└── pyproject.toml               # uv workspace root (uv.lock is source of truth)
```
