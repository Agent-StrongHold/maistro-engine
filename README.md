# maistro-engine

The shared Python runtime that underpins three downstream products. Not an end-user application — a substrate.

```
                          ┌───────────────────────────────────┐
                          │        maistro-engine            │
                          │   shared Python runtime + ADRs   │
                          │   + Copier templates + registry  │
                          └──────────────┬──────────────────┘
                                         │ imports / templates
                ┌───────────────────────────┼────────────────────────────────────────┐
                ▼                        ▼                        ▼
       ┌──────────────┐          ┌──────────────┐         ┌──────────────┐
       │ Project_mAIstro │        │ AgentTuring  │         │  stronghold  │
       │ single-tenant │         │ autonoetic   │         │ multi-tenant │
       │ multi-user   │         │ experiment   │         │ enterprise  │
       │ self-hosted  │         │ 24/7 self-   │         │             │
       │             │         │ awareness    │         │             │
       └──────────────┘          └──────────────┘         └──────────────┘
        ease of self-host       continuity of self      multi-tenant isolation
         (dominant constraint)   (dominant constraint)   (dominant constraint)
```

## What this repo is

- **Library** — the Python runtime: orchestrator, conduit, classifier, router, agents, A2A, memory, security, skills, tools, observability, quota, sessions, events.
- **Canonical ADRs** — architectural decisions that all three products inherit. See `docs/adr/`.
- **Copier templates** — three product scaffolds under `templates/` (per [`ADR-033`](docs/adr/ADR-033-templates-and-copier-workflow.md)).
- **Registry CI host** — the front-matter validator, link-checker, and registry generator that enforce cross-repo conventions.

## What this repo is not

- Not an end-user product. It does not ship a UI, a deployment, or a household setup wizard. Those are downstream.
- Not multi-tenant. Multi-tenancy lives in `stronghold`.
- Not autonoetic. Continuous self-modelling lives in `AgentTuring`.

## The four-repo system

| Repo | Role | Dominant constraint |
|---|---|---|
| `BlakeMatthews-dev/maistro-engine` | Substrate (this repo) | n/a |
| `BlakeMatthews-dev/Project_mAIstro` | Single-tenant secure multi-user product | Ease of self-hosting |
| `BlakeMatthews-dev/AgentTuring` | Autonoetic experimental agent | Continuity of self |
| `agent-stronghold/stronghold` | Multi-tenant enterprise product | Multi-tenant isolation |

The three products are **Copier-templated peers**, not a hierarchy. Each rebases from an engine template. See [`ADR-030`](docs/adr/ADR-030-four-repo-governance.md) for the full governance model.

## Quick start

```bash
# Requires Python 3.12 and uv (https://github.com/astral-sh/uv)
uv sync                               # install all packages in the workspace
uv run pytest                         # run the test suite
uv run alembic upgrade head           # apply migrations (needs Postgres)
docker compose up -d                  # full local stack (Postgres + LiteLLM + Langfuse)
```

The repo is a `uv` workspace with four packages:

| Package | Purpose |
|---|---|
| `maistro-core` | The library: orchestration, agents, memory, security, skills, tools |
| `maistro-server` | FastAPI HTTP surface around `maistro-core` |
| `maistro-turing` | Autonoetic self-model package consumed by `AgentTuring` |
| `maistro-canvas` | Book-builder package consumed by Canvas Studio |

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
- **router** — picks model and agent via scoring formula `quality^(qw·p) / cost^cw`
- **agents** — base/factory/strategies/roster + A2A delegation
- **memory** — learning, episodic, outcome stores; pgvector-backed
- **security** — Warden (input), Sentinel (output), Gate (boundary), PII filter
- **skills** — marketplace + Forge + canary
- **observability** — OpenTelemetry traces, Prometheus metrics, structlog logs, domain events (per [`ADR-037`](docs/adr/ADR-037-observability-taxonomy.md))
- **reliability** — retries, circuit breakers, fallbacks, SLOs (per [`ADR-038`](docs/adr/ADR-038-reliability-taxonomy.md))

## ADRs and specs

- All architectural decisions are recorded as ADRs under `docs/adr/`.
- The cross-repo inventory of every ADR and spec lives at [`docs/INVENTORY-ADRS-SPECS.md`](docs/INVENTORY-ADRS-SPECS.md).
- Front-matter and cross-reference conventions are defined in [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md).
- Acceptance criteria are layered contracts (Pydantic / Hoare / Pact) per [`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md).

### Where does my work go?

| Kind of work | Where it lands |
|---|---|
| Shared Python subsystem (orchestrator, memory, router, security…) | `maistro-engine` (this repo) — see [`ADR-019`](docs/adr/ADR-019-canonical-source-split.md) |
| Multi-tenant deployment / K8s topology / RBAC / tenant isolation | `stronghold` |
| Autonoetic self-model / 24/7 awareness loop / dossier | `AgentTuring` |
| End-user single-tenant multi-user feature (channels, household UX) | `Project_mAIstro` |
| Architectural decision affecting more than one product | Engine ADR here, with `substrate:` cross-refs from product specs |

## Status

v1.0 horizon: 3 months. v2.0 (inventory-clear): 12 months. See [`ADR-030`](docs/adr/ADR-030-four-repo-governance.md) for product-specific MVPs.

The registry CI is in **warn-only mode** during the front-matter rollout window (per [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md)). Hard CI fail at day 30.

## Contributing

1. Branch off `main` as `claude/<topic>-<slug>` (per [`ADR-001`](docs/adr/ADR-001-branching-strategy.md)).
2. ADRs live in `docs/adr/ADR-NNN-<slug>.md` with required front-matter (per [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md)).
3. Tests carry `pytest.mark.contract(...)` and `pytest.mark.scope(...)` (per [`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md)).
4. Mutation-testing kill rate is the quality bar; coverage is reported but not gating.
5. Cross-repo work uses the same branch name across repos when feasible.

## Layout

```
maistro-engine/
├── docs/
│   ├── adr/                          # Architectural Decision Records
│   ├── analysis/                     # Cross-framework comparisons
│   └── INVENTORY-ADRS-SPECS.md       # Cross-repo ADR/spec inventory
├── packages/
│   ├── maistro-core/                 # The library
│   ├── maistro-server/               # FastAPI surface
│   ├── maistro-turing/               # Autonoetic self-model package
│   └── maistro-canvas/               # Canvas Studio package
├── templates/                        # Copier templates (per ADR-033)
│   ├── single-tenant-multi-user/     # Project_mAIstro shape
│   ├── autonoetic/                   # AgentTuring shape
│   └── multi-tenant/                 # stronghold shape
├── alembic/                          # DB migrations
├── tests/
├── docker-compose.yml                # Local dev stack
├── litellm_config.yaml               # Model gateway config
├── pyproject.toml                    # uv workspace root
└── README.md                         # this file
```

## License

TBD.
