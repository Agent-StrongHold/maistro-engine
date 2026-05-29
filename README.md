# maistro-engine

> The shared Python runtime behind three AI-agent products — orchestration, routing, memory, and security as one importable substrate, not an end-user app.

<!-- Badges: built with shields.io. Workflow badges read live status from GitHub Actions. -->
[![CI](https://github.com/BlakeMatthews-dev/maistro-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/BlakeMatthews-dev/maistro-engine/actions/workflows/ci.yml)
[![Quality](https://github.com/BlakeMatthews-dev/maistro-engine/actions/workflows/quality.yml/badge.svg)](https://github.com/BlakeMatthews-dev/maistro-engine/actions/workflows/quality.yml)
[![Security](https://github.com/BlakeMatthews-dev/maistro-engine/actions/workflows/security.yml/badge.svg)](https://github.com/BlakeMatthews-dev/maistro-engine/actions/workflows/security.yml)
[![Registry CI](https://github.com/BlakeMatthews-dev/maistro-engine/actions/workflows/registry.yml/badge.svg)](https://github.com/BlakeMatthews-dev/maistro-engine/actions/workflows/registry.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](#license)
[![Managed with uv](https://img.shields.io/badge/managed%20with-uv-261230.svg)](https://github.com/astral-sh/uv)

`maistro-engine` is the canonical runtime that three downstream products import and template from. You don't deploy it — you build on it. One request flows in, gets classified, routed to the best model and agent, executed against tools and memory, and guarded at every trust boundary.

```
request ──► conduit ──► classifier ──► orchestrator ──► router ──► agent ──► tools / memory / LLM
                                                                  │
                                                            (security gates,
                                                             quota, retries,
                                                             observability)
```

---

## Quick start

Zero to a passing test suite in under a minute. Requires **Python 3.12+** and [`uv`](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/BlakeMatthews-dev/maistro-engine.git
cd maistro-engine
uv sync          # install every package in the workspace
uv run pytest    # run the test suite — this is your "it works" signal
```

That's it. Everything below is optional depth.

```bash
uv sync --extra bootstrap         # maistro-install TUI / answers-file planner
uv run maistro-install --dry-run  # print the uv/docker/copier commands (see docs/install/)
uv run alembic upgrade head       # apply DB migrations (needs Postgres)
docker compose up -d              # full local stack: Postgres + LiteLLM + Langfuse
```

## Features

- **Protocol-driven DI** — every subsystem depends on abstract interfaces, never concrete implementations. Swap stores, LLM clients, or policies without touching business logic.
- **Smart routing** — picks model *and* agent via a scoring formula (`quality^(qw·p) / cost^cw`) with scarcity-based cost and task-type speed bonuses.
- **Memory that forgets** — learning, episodic, and outcome stores (pgvector-backed) that decay without reinforcement, with weight floors for hard-won wisdom and regrets.
- **Untrusted-by-default security** — Warden scans input, Sentinel validates tool calls, Gate guards boundaries, plus a PII filter at every trust edge.
- **Agents are data** — an agent is rows in a store and prompts in YAML; the runtime is shared. Add A2A (agent-to-agent) delegation on top.
- **Batteries included** — skills marketplace + Forge, quota tracking per provider, session history with TTL pruning, an event bus, and a graph (DAG) execution engine.
- **Observability out of the box** — OpenTelemetry traces, Prometheus metrics, structlog logs, and domain events ([`ADR-037`](docs/adr/ADR-037-observability-taxonomy.md)).
- **Reliability primitives** — retries, circuit breakers, fallbacks, and SLOs ([`ADR-038`](docs/adr/ADR-038-reliability-taxonomy.md)).

## Usage

The smallest meaningful example — wire a container via DI and route a request through the full pipeline (classify → route → agent → response). The API is async, and messages use the familiar OpenAI chat shape:

```python
import asyncio
from maistro.container import create_container
from maistro.types import AgentConfig

async def main():
    config = AgentConfig(router_api_key="sk-...")   # ROUTER_API_KEY is required
    container = await create_container(config)        # protocol-driven DI wiring

    response = await container.route_request(
        [{"role": "user", "content": "Summarize today's standup notes"}],
    )
    print(response["choices"][0]["message"]["content"])

asyncio.run(main())
```

`route_request` runs the conduit pipeline end to end: Gate scan → classify intent →
route to the best model/agent → execute. It also accepts `auth`, `session_id`, and
`intent_hint` keyword arguments.

Need the FastAPI HTTP surface instead of the library? That lives in `maistro-server`:

```bash
uv run uvicorn maistro_server.main:app --reload
```

<details>
<summary><strong>Verify your install (copy-paste smoke test)</strong></summary>

```bash
PYTHONPATH=packages/maistro-core/src python3 -c "
from maistro.container import Container, create_container
from maistro.conduit import Conduit
from maistro.types import AgentConfig, AgentError
from maistro.router.selector import RouterEngine
from maistro.classifier.engine import ClassifierEngine
from maistro.security.warden.detector import Warden
print('OK')
"
```

</details>

## Packages

The repo is a `uv` workspace: **six published Python packages**, plus the `hive-conductor` reference app stack and a planned native gateway node.

| Package / tree | Purpose |
|---|---|
| `maistro-core` | The library: orchestration, agents, memory, security, skills, tools |
| `maistro-server` | FastAPI HTTP surface around `maistro-core` |
| `maistro-turing` | Autonoetic self-model package consumed by `AgentTuring` |
| `maistro-canvas` | Book-builder package consumed by Canvas Studio |
| `maistro-bootstrap` | `maistro-install` TUI and answers-file planner (`uv sync --extra bootstrap`) |
| `maistro-registry` | Front-matter validation, link checks, registry generation |
| `packages/hive-conductor/` | Hive Conductor reference: Vite frontend, FastAPI backend, Docker |
| `apps/maistro-gateway-node-flutter/` | Flutter gateway node (see [`SPEC-179`](docs/specs/SPEC-179-flutter-gateway-node.md)) |

<details>
<summary><strong>Core subsystems at a glance</strong></summary>

| Subsystem | Import | What |
|---|---|---|
| Conduit | `maistro.conduit` | Request pipeline: classify → route → agent.handle |
| Container | `maistro.container` | DI wiring + `route_request()` |
| Orchestrator | `maistro.orchestrator` | Super Planner + Master Orchestrator |
| Router | `maistro.router` | Scoring formula + RouterEngine |
| Classifier | `maistro.classifier` | 3-phase intent: keywords → LLM → complexity |
| Agents | `maistro.agents` | Base class, factory, strategies, roster |
| A2A | `maistro.a2a` | Agent-to-agent delegation + lifecycle |
| Memory | `maistro.memory` | Learnings, episodic, scopes, outcomes |
| Security | `maistro.security` | Warden, Sentinel, Gate, PII filter |
| Skills | `maistro.skills` | Marketplace, Forge, parser, canary |
| Graph | `maistro.graph` | DAG execution: node types, executor, optimizer ([`ADR-042`](docs/adr/)) |
| Persistence | `maistro.persistence` | PostgreSQL stores (learnings, agents, audit, quota) |
| Quota | `maistro.quota` | Token usage tracking per provider per billing cycle |
| Sessions | `maistro.sessions` | Conversation history with TTL pruning |
| Events | `maistro.events` | Bus, handlers, recipes, triggers |

</details>

## How it fits: the four-repo system

`maistro-engine` is the substrate. The three products are **Copier-templated peers**, not a hierarchy — each rebases from an engine template ([`ADR-030`](docs/adr/ADR-030-four-repo-governance.md), [`ADR-033`](docs/adr/ADR-033-templates-and-copier-workflow.md)).

```
                          ┌──────────────────────────────────┐
                          │          maistro-engine          │
                          │   shared Python runtime + ADRs    │
                          │   + Copier templates + registry   │
                          └─────────────────┬─────────────────┘
                                            │ imports / templates
          ┌─────────────────────────────────┼─────────────────────────────────┐
          ▼                                 ▼                                 ▼
   ┌──────────────┐                 ┌──────────────┐                  ┌──────────────┐
   │Project_mAIstro│                │ AgentTuring  │                  │  stronghold  │
   │ single-tenant │                │  autonoetic  │                  │ multi-tenant │
   │  multi-user   │                │  experiment  │                  │  enterprise  │
   │  self-hosted  │                │ 24/7 self-   │                  │              │
   │               │                │  awareness   │                  │              │
   └──────────────┘                 └──────────────┘                  └──────────────┘
   ease of self-host                continuity of self                multi-tenant isolation
```

| Repo | Role | Dominant constraint |
|---|---|---|
| `BlakeMatthews-dev/maistro-engine` | Substrate (this repo) | n/a |
| `BlakeMatthews-dev/Project_mAIstro` | Single-tenant secure multi-user product | Ease of self-hosting |
| `BlakeMatthews-dev/AgentTuring` | Autonoetic experimental agent | Continuity of self |
| `agent-stronghold/stronghold` | Multi-tenant enterprise product | Multi-tenant isolation |

**What this repo is _not_:** not an end-user product (no UI, no deployment, no setup wizard — those are downstream), not multi-tenant (that lives in `stronghold`), and not autonoetic (continuous self-modelling lives in `AgentTuring`).

<details>
<summary><strong>Where does my work go?</strong></summary>

| Kind of work | Where it lands |
|---|---|
| Shared Python subsystem (orchestrator, memory, router, security…) | `maistro-engine` (this repo) — see [`ADR-019`](docs/adr/ADR-019-canonical-source-split.md) |
| Multi-tenant deployment / K8s topology / RBAC / tenant isolation | `stronghold` |
| Autonoetic self-model / 24/7 awareness loop / dossier | `AgentTuring` |
| End-user single-tenant multi-user feature (channels, household UX) | `Project_mAIstro` |
| Architectural decision affecting more than one product | Engine ADR here, with `substrate:` cross-refs from product specs |

</details>

## Documentation

The README is a landing page — depth lives under [`docs/`](docs/).

- **ADRs** — all architectural decisions are recorded under [`docs/adr/`](docs/adr/) (ADR-000 through ADR-042).
- **Inventory** — the cross-repo index of every ADR and spec: [`docs/INVENTORY-ADRS-SPECS.md`](docs/INVENTORY-ADRS-SPECS.md).
- **Conventions** — front-matter and cross-reference rules: [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md). Acceptance criteria as layered contracts (Pydantic / Hoare / Pact): [`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md).
- **Legacy archives** — frozen, non-importable snapshots live under [`potential-dead-code/`](potential-dead-code/README.md); retention is defined in [`SPEC-178`](docs/specs/SPEC-178-legacy-snapshot-retention.md).

## Status

v1.0 horizon: **3 months**. v2.0 (inventory-clear): **12 months**. See [`ADR-030`](docs/adr/ADR-030-four-repo-governance.md) for product-specific MVPs.

> ⚠️ The registry CI is in **warn-only mode** during the front-matter rollout window ([`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md)). Hard CI fail lands at day 30.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full guide. Quick reminders:

1. Branch off `main` as `claude/<topic>-<slug>` ([`ADR-001`](docs/adr/ADR-001-branching-strategy.md)).
2. ADRs go in `docs/adr/ADR-NNN-<slug>.md` with required front-matter ([`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md)).
3. Tests carry `pytest.mark.contract(...)` and `pytest.mark.scope(...)` ([`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md)).
4. Mutation-testing kill rate is the quality bar; coverage is reported but not gating.
5. Cross-repo work uses the same branch name across repos when feasible.
6. External library adoption follows [`ADR-039`](docs/adr/ADR-039-external-library-adoption-policy.md).

<details>
<summary><strong>Repository layout</strong></summary>

```
maistro-engine/
├── docs/
│   ├── adr/                          # Architectural Decision Records
│   ├── analysis/                     # Cross-framework comparisons
│   ├── specs/                        # Numbered engine specs (SPEC-17x)
│   └── INVENTORY-ADRS-SPECS.md       # Cross-repo ADR/spec inventory
├── potential-dead-code/              # Frozen legacy snapshots (not on PYTHONPATH; SPEC-178)
├── packages/
│   ├── maistro-core/                 # The library
│   ├── maistro-server/               # FastAPI surface
│   ├── maistro-turing/               # Autonoetic self-model package
│   ├── maistro-canvas/               # Canvas Studio package
│   ├── maistro-bootstrap/            # maistro-install planner
│   ├── maistro-registry/             # Registry / front-matter CI helpers
│   └── hive-conductor/               # Reference app (frontend + backend + Docker)
├── apps/
│   └── maistro-gateway-node-flutter/ # Native gateway node (Flutter; see SPEC-179)
├── scripts/                          # e.g. sibling spec pull, layout verify
├── templates/                        # Copier templates (per ADR-033)
│   ├── single-tenant-multi-user/     # Project_mAIstro shape
│   ├── autonoetic/                   # AgentTuring shape
│   └── multi-tenant/                 # stronghold shape
├── alembic/                          # DB migrations
├── tests/                            # Legacy / shared pytest (see CI comments)
├── docker-compose.yml                # Local dev stack
├── litellm_config.yaml               # Model gateway config
├── pyproject.toml                    # uv workspace root
├── CONTRIBUTING.md                   # Author-facing how-to
└── README.md                         # this file
```

</details>

## License

Apache 2.0. See [`CLAUDE.md`](CLAUDE.md) for project-wide conventions.
