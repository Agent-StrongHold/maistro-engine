# maistro-engine

The shared Python runtime — and the consolidation monorepo — behind the Maistro products. Not a library you only import: it also *contains* **Agent Conductor** (the personal/homelab app) and the **canvas ability**, and exposes `maistro-core` for downstream products to import.

```
        ┌────────────────────────────────────────────────────┐
        │                    maistro-engine                   │
        │  shared runtime ........ packages/maistro-core, …   │
        │  Agent Conductor app ... packages/hive-conductor    │
        │  canvas ability ........ packages/maistro-canvas    │
        │  + ADRs/specs + registry CI                         │
        └───────────────────────────┬────────────────────────┘
                                    │ imported by
                     ┌──────────────┴───────────────┐
                     ▼                               ▼
         ┌───────────────────────┐      ┌────────────────────────────┐
         │ Canvas book-maker POC │      │ Stronghold  (planned)       │
         │ (name TBD)            │      │ imports the engine, adds    │
         │ imports maistro-canvas│      │ multi-tenancy + a stricter  │
         │                       │      │ security stance, disables   │
         │                       │      │ homelab/personal features   │
         └───────────────────────┘      └────────────────────────────┘
```

## What this repo is

- **A monorepo** — the shared Python runtime under `packages/maistro-core`, its sibling packages, the **Agent Conductor** app (`packages/hive-conductor`, the personal/homelab product), and the **canvas ability** (`packages/maistro-canvas`). One `uv` workspace, one git repo.
- **Library-first** — `maistro-core` is a pure Python library; the FastAPI surface (`maistro-server`) is a thin wrapper. The app is optional.
- **Canonical ADRs & specs** — architectural decisions and specifications under `docs/adr/` and `docs/specs/`.
- **Registry CI host** — the front-matter validator, link-checker, and registry generator that enforce doc conventions (`packages/maistro-registry`).

> **History note.** This engine used to be split across sibling repos (`Project_mAIstro`, `stronghold`, `AgentTuring`, `conductor-router`). The canonical shape as of 2026-05 is this single substrate monorepo — sibling trees are being consolidated in additively (see [`CONSOLIDATION-PLAN.md`](docs/archive/CONSOLIDATION-PLAN.md)). Cross-repo `<repo>#<ID>` references in front-matter remain valid during the transition.

## What this repo is not

- Not, by itself, multi-tenant. Tenant isolation is the Stronghold layer on top of `maistro-core`, not part of core — there is no `org_id` in core (see [`ADR-019`](docs/adr/ADR-019-canonical-source-split.md)).
- Not the place for product-specific UX. Homelab/personal features live in Agent Conductor; the enterprise hardening lives in Stronghold.

## Products

**Shipped in this repo:**

| Product | Lives in | Audience |
|---|---|---|
| **Agent Conductor** | `packages/hive-conductor` (consumes `maistro-core`) | Household / personal, self-hosted |

**Downstream products that import the engine:**

| Product | Imports | Status |
|---|---|---|
| **Canvas book-maker** (name TBD) | `maistro-canvas` (the canvas ability) | POC — frontend app on top of the canvas engine |
| **Stronghold** | `maistro-engine` | Planned — refactor to import the engine, add multi-tenancy + a stricter security stance, and disable homelab/personal features |

The line between shared runtime and product-specific code is defined in [`ADR-019`](docs/adr/ADR-019-canonical-source-split.md): `maistro-core` stays product-agnostic; tenancy, security posture, and feature toggles live in the importing product.

## Quick start

```bash
# Requires Python 3.12+ (CI tests 3.12; the container image runs 3.14) and uv — https://github.com/astral-sh/uv
uv sync                               # install every package in the workspace
uv sync --extra bootstrap             # optional: maistro-install TUI / answers-file planner
uv run pytest                         # run the test suite
uv run alembic upgrade head           # apply DB migrations (needs Postgres)
docker compose up -d                  # full local stack (Postgres + LiteLLM + Langfuse)
```

The repo is a `uv` workspace: **nine Python packages**, plus the **`packages/hive-conductor`** reference app (frontend + backend + Docker) and the planned **`apps/maistro-gateway-node-flutter`** native node (see [`SPEC-179`](docs/specs/SPEC-179-flutter-gateway-node.md)).

| Package / tree | Purpose |
|---|---|
| `maistro-core` | The library: orchestration, agents, memory, security, skills, tools, router |
| `maistro-server` | FastAPI HTTP surface around `maistro-core` |
| `maistro-turing` | Autonoetic self-model package (mood, drives, proactive producers) |
| `maistro-canvas` | Canvas engine — the base canvas ability behind Canvas Studio |
| `maistro-evolve` | Elo-tournament optimizer for agent self-improvement |
| `maistro-bootstrap` | `maistro-install` TUI and answers-file planner (`uv sync --extra bootstrap`) |
| `maistro-registry` | Front-matter validation, link checks, registry generation |
| `packages/hive-conductor/` | Agent Conductor reference app: React frontend, FastAPI backend, Docker |
| `apps/maistro-gateway-node-flutter/` | Flutter gateway node (bootstrap with `flutter create`; see app README) |

## Architecture at a glance

```
request ──► conduit ──► classifier ──► orchestrator ──► router ──► agent ──► tools / memory / LLM
                                                                  │
                                                            (security gates,
                                                             quota, retries,
                                                             observability)
```

- **conduit** — single entry point; classifies, routes, delegates
- **orchestrator** — plans tasks, manages execution, tracks state
- **router** — picks model and agent via the scoring formula `quality^(qw·p) / (1 + normalized_cost)^cw`
- **agents** — base / factory / strategies / roster + A2A delegation
- **memory** — learning, episodic, outcome stores; pgvector-backed; decays without reinforcement
- **security** — Warden (input), Sentinel (output), Gate (boundary), PII filter — all input is untrusted
- **skills** — marketplace + Forge + canary
- **graph** — DAG execution: nodes, executor, optimizer ([`ADR-062`](docs/adr/ADR-062-graph-execution-protocol.md))
- **observability** — traces, Prometheus metrics, structlog logs, domain events ([`ADR-037`](docs/adr/ADR-037-observability-taxonomy.md))
- **resilience** — retries, circuit breakers, fallbacks ([`ADR-038`](docs/adr/ADR-038-reliability-taxonomy.md))

## ADRs and specs

- All architectural decisions are recorded as ADRs under `docs/adr/`.
- The cross-repo inventory of every ADR and spec lives at [`docs/INVENTORY-ADRS-SPECS.md`](docs/INVENTORY-ADRS-SPECS.md).
- Front-matter and cross-reference conventions are defined in [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md); acceptance criteria are layered contracts per [`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md).
- **Legacy archives:** the former `potential-dead-code/` reference trees were **removed** once their behavior shipped under `packages/` ([`SPEC-178`](docs/specs/SPEC-178-legacy-snapshot-retention.md)); provenance remains in git history and the sibling repos.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full author guide. The essentials:

- Branch model is `feature/* → develop → integration → main` — base feature work off `develop`, never open PRs against `main` directly ([`ADR-095`](docs/adr/ADR-095-four-tier-branch-model.md)).
- ADRs live in `docs/adr/ADR-NNN-<slug>.md` with required front-matter ([`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md)); validate with `python -m maistro_registry.cli lint .`.
- Tests carry `@pytest.mark.contract` and `@pytest.mark.scope(...)` ([`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md)).
- External-library adoption follows [`ADR-039`](docs/adr/ADR-039-external-library-adoption-policy.md): import / service-boundary / pattern-reference / reject.

## Layout

```
maistro-engine/
├── docs/
│   ├── adr/                          # Architecture Decision Records
│   ├── specs/                        # Numbered engine specs (SPEC-NNN)
│   └── INVENTORY-ADRS-SPECS.md       # Cross-repo ADR/spec inventory
├── packages/
│   ├── maistro-core/                 # The library
│   ├── maistro-server/               # FastAPI surface
│   ├── maistro-turing/               # Autonoetic self-model package
│   ├── maistro-canvas/               # Canvas ability (Canvas Studio)
│   ├── maistro-evolve/               # Elo-tournament optimizer
│   ├── maistro-bootstrap/            # maistro-install planner
│   ├── maistro-registry/             # Registry / front-matter CI helpers
│   └── hive-conductor/               # Agent Conductor reference app (frontend + backend + Docker)
├── apps/
│   └── maistro-gateway-node-flutter/ # Native gateway node (Flutter; see SPEC-179)
├── formal/                           # Property-based conformance tests (Hypothesis; separate CI)
├── templates/                        # Copier templates (per ADR-033)
├── scripts/                          # Repo maintenance scripts
├── alembic/                          # DB migrations
├── tests/                            # Shared / registry pytest tree (in `testpaths`)
├── docker-compose.yml                # Local dev stack
├── pyproject.toml                    # uv workspace root (uv.lock is source of truth)
├── CONTRIBUTING.md                   # Author-facing how-to
└── README.md                         # this file
```

## License

Licensed under the Apache License, Version 2.0 (SPDX: `Apache-2.0`) — see
[`LICENSE`](LICENSE) for the full text.

Every distributable package under `packages/` declares `license = "Apache-2.0"` in its
`pyproject.toml` and ships a copy of the license in its wheel, so the terms travel with the
artifact rather than only with this repository.

```
Copyright 2026 The Maistro Engine authors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```
