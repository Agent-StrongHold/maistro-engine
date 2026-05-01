# CLAUDE.md — Maistro Engine

**Project:** Maistro Engine — Multi-agent AI platform (monorepo)
**License:** Apache 2.0
**Python:** 3.12+

---

## Architecture

Monorepo with 3 packages. Consumers import what they need.

```
packages/
├── maistro-core/      # Shared library: pip install maistro-core
├── maistro-server/    # FastAPI app: pip install maistro-server
└── maistro-turing/    # Self-model extensions: pip install maistro-turing
```

### maistro-core (the library)

Every subsystem is importable. Consumers (conductor-router, Project Turing, your own app) add `maistro-core` to their requirements and import what they need.

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

### Agent Roster (renameable)

Agents are data (agent.yaml), not code. Rename freely.

| Default Name | Strategy | Role |
|-------------|----------|------|
| Code Agent (Artificer) | plan_execute | Multi-phase engineering |
| Write Agent (Scribe) | plan_execute | Writing specialist |
| Create Agent (Forge) | react | Tool/skill creation |
| Control Agent (Warden-at-Arms) | react | Device/API control |
| Review Agent (Auditor) | direct | PR review, security checks |
| Decompose Agent (Frank) | direct | Issue analysis, spec emission |
| Build Agent (Mason) | react | Plan execution, code generation |
| Search Agent (Ranger) | react | Read-only search |
| Triage Agent (Arbiter) | delegate | Clarification + delegation |

### Builder Pipeline Stages

```
queued → issue_analyzed → acceptance_defined → tests_written →
implementation_started → implementation_ready → quality_checks_passed → completed
```

Builder roles: Frank (decompose), Mason (build), Auditor (review), Quartermaster (spec templates), Archie (property tests).

### Super Planner + Master Orchestrator

The orchestrator system that can execute the consolidation plan (or any complex task) in parallel:

- **Super Planner** decomposes goals into parallel-safe waves via topological sort
- **Master Orchestrator** dispatches waves, handles retries, tracks XP, gates security
- Both live in `maistro.orchestrator`

---

## Development Commands

```bash
# Install for development (from repo root)
pip install -e packages/maistro-core
pip install -e packages/maistro-server
pip install -e packages/maistro-turing

# Run core tests
PYTHONPATH=packages/maistro-core/src pytest packages/maistro-core/tests/ -q

# Run server tests
PYTHONPATH=packages/maistro-core/src:packages/maistro-server/src pytest packages/maistro-server/tests/ -q

# Lint
ruff check packages/
mypy packages/ --strict

# Verify all imports
PYTHONPATH=packages/maistro-core/src python3 -c "
from maistro.memory.learnings.store import InMemoryLearningStore
from maistro.security.warden.detector import Warden
from maistro.classifier.engine import ClassifierEngine
from maistro.router.selector import RouterEngine
from maistro.agents.base import Agent
from maistro.builders import BuildersOrchestrator
from maistro.a2a.delegate import A2ADelegator
from maistro.skills.marketplace import SkillMarketplace
from maistro.orchestrator import SuperPlanner, MasterOrchestrator
print('OK')
"
```

---

## Key Design Decisions

1. **Library-first, app is optional.** Core is a pure Python library. FastAPI app is a thin wrapper.
2. **Protocol-driven DI.** All business logic depends on protocols (abstract interfaces), never concrete implementations.
3. **Agents are data.** An agent is rows in PostgreSQL, prompts in YAML. The runtime is shared. Rename via agent.yaml.
4. **Scoring formula.** `quality^(qw*p) / cost^cw` with scarcity-based cost and task-type speed bonuses.
5. **Memory must forget.** Decay without reinforcement, weight floors for wisdom/regrets.
6. **All input is untrusted.** Warden scans at every trust boundary. Sentinel validates tool calls.
7. **No org_id.** Multi-tenant isolation is Stronghold-specific. Scope isolation (global → team → user → agent → session) is kept.

---

## Consumer Integration

### conductor-router (homelab)
```python
# requirements.txt: maistro-core>=0.1
from maistro.security.warden.detector import Warden
from maistro.classifier.engine import ClassifierEngine
from maistro.router.scorer import score_candidate
```

### Project Turing
```python
# requirements.txt: maistro-core>=0.1, maistro-turing>=0.1
from maistro_turing.bridge import TuringMemoryBridge, TuringSecurityBridge
from maistro_turing.self_model import Mood, PersonalityFacet
from maistro_turing.runtime import TuringActor
```

---

## File Layout

```
maistro-engine/
├── packages/
│   ├── maistro-core/
│   │   ├── pyproject.toml
│   │   └── src/maistro/
│   │       ├── agents/          # base, factory, strategies, roster
│   │       ├── a2a/             # delegate, lifecycle, guest_peers
│   │       ├── builders/        # contracts, runtime, orchestrator, spec, verifier
│   │       ├── classifier/      # engine, keyword, llm_fallback, complexity
│   │       ├── config/          # settings, loader
│   │       ├── memory/          # learnings, episodic, scopes, outcomes
│   │       ├── observability/   # logging, metrics, tracing
│   │       ├── orchestrator/    # Super Planner, Master Orchestrator
│   │       ├── persistence/     # PostgreSQL stores
│   │       ├── protocols/       # abstract interfaces
│   │       ├── router/          # scorer, selector, filter, scarcity, speed
│   │       ├── scheduler/       # heartbeat, proactive autonomy
│   │       ├── security/        # warden, sentinel, gate, auth
│   │       ├── skills/          # marketplace, forge, parser, canary, connectors
│   │       ├── tasks/           # queue, runner, models
│   │       ├── tools/           # sandbox, git, browser
│   │       └── types/           # shared dataclasses
│   │
│   ├── maistro-server/
│   │   ├── pyproject.toml       # depends: maistro-core
│   │   └── src/maistro_server/
│   │       ├── api/             # HTTP routes
│   │       └── main.py          # FastAPI app
│   │
│   └── maistro-turing/
│       ├── pyproject.toml       # depends: maistro-core
│       └── src/maistro_turing/
│           ├── bridge.py        # Adapters to maistro-core
│           ├── self_model.py    # Autonoetic identity
│           ├── runtime.py       # Actor, chat, config
│           └── producers.py     # Blog, reflection, curiosity, emotion
│
├── docs/adr/                    # Architecture Decision Records
├── CONSOLIDATION-PLAN.md        # Full subsystem inventory + wave plan
├── CLAUDE.md                    # This file
└── pyproject.toml               # Workspace root (shared tool config)
```
