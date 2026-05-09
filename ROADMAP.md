# maistro-engine — ROADMAP

**Role:** substrate library + canonical ADRs + Copier templates + registry CI host (per [`ADR-030`](docs/adr/ADR-030-four-repo-governance.md)).
**Horizon:** v1.0 at 3 months; v2.0 at 12 months (inventory-clear).
**v1.0 acceptance:** every accepted engine ADR has shipped reference code + contract tests; the three Copier templates round-trip cleanly; the registry CI is hard-fail on dangling refs.

## What this roadmap is

This is the **engine** roadmap. It does not list product features (those live in product repos). It lists the substrate work the three products need.

Products have their own ROADMAPs:

- [`Project_mAIstro/ROADMAP-v1.0.md`](https://github.com/BlakeMatthews-dev/Project_mAIstro) (proposed, see `docs/proposals/Project_mAIstro-ROADMAP.md` until applied)
- [`AgentTuring/ROADMAP-v1.0.md`](https://github.com/BlakeMatthews-dev/AgentTuring/blob/main/ROADMAP-v1.0.md)
- [`stronghold/ROADMAP-v1.0.md`](https://github.com/agent-stronghold/stronghold/blob/main/ROADMAP-v1.0.md)

When a product spec needs an engine change, it opens an engine ADR. This ROADMAP plus the [`BACKLOG.md`](BACKLOG.md) are the visible queue of that work.

## v1.0 milestones (3 months)

### M1 — Conventions enforced (weeks 1–4)

- [`Phase 0g`] Registry CI tooling lands: front-matter validator + cross-repo link checker + registry generator + GitHub Action
- [`Phase 1`] INVENTORY becomes derived (regenerated from registry), not hand-maintained
- [`Phase 2c`] Existing engine ADRs (000–029) gain front-matter on touch (gradual)
- Warn-only window per [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md) closes at day 30; CI flips to hard fail

### M2 — Templates bootstrapped (weeks 2–6)

- `templates/single-tenant-multi-user/` round-trips against `Project_mAIstro` (per [`ADR-033`](docs/adr/ADR-033-templates-and-copier-workflow.md))
- `templates/autonoetic/` round-trips against `AgentTuring`
- `templates/multi-tenant/` round-trips against `stronghold`
- `copier update` workflow validated end-to-end against a synthetic template change
- Two release streams in CI: `pkg/v*` and `template/v*`

### M3 — Drift items closed (weeks 3–7)

- [`Phase 3c`] Memory specs across mAIstro/Turing recast as Substrate-cited parameterisations of engine ADR-011…017 (per [`ADR-034`](docs/adr/ADR-034-memory-canonical-ownership.md))
- [`Phase 3d`] Catalog specs split: engine simple form + stronghold multi-tenant variant (per [`ADR-035`](docs/adr/ADR-035-catalog-ownership-split.md)); the four `K8S-*` catalog ADRs migrate to stronghold (Phase 2a)
- Three product specs without `substrate:` cross-refs become a CI failure

### M4 — Substrate code parity (weeks 4–9)

- [`ADR-036`](docs/adr/ADR-036-ontology-semantic-object-layer.md) Ontology Semantic facet: `OntologyEntity`, `Ontology` protocol, registration, persistence, query. Kinetic and Dynamic facets remain `gap-impl` (deferred to v2.0).
- [`ADR-037`](docs/adr/ADR-037-observability-taxonomy.md) Observability primitives: required spans on every public entry point; required metrics emitted; event topics defined.
- [`ADR-038`](docs/adr/ADR-038-reliability-taxonomy.md) Reliability primitives: `retry()` decorator; `CircuitBreaker` per dependency; `Fallback[T]`; `/health/{live,ready,startup}`.
- All three are exercised by the three product templates' generated test suites.

### M5 — Contracts as the bar (weeks 6–12)

- [`ADR-032`](docs/adr/ADR-032-contracts-as-acceptance-criteria.md) layered contracts shipped:
  - Boundary: Pydantic models on every public type; ≥95% mutation kill rate at v1.0
  - Behavioral: Hypothesis property tests on every accepted ADR with behavioural AC; ≥80%
  - Cross-service: Pact-style contracts on every A2A and MCP edge; ≥75%
- `pytest.mark.contract` and `pytest.mark.scope` in use across the engine
- Mutation testing nightly + on `main` merges (slow gates not on every PR)

## v1.1 (3–6 months) — the products' v1.0 lands on top

- All three product v1.0s pass their acceptance suites against the engine
- Cross-product agent portability proof of concept (export an agent from `Project_mAIstro` simple catalog → import into `stronghold` tenant catalog without recoding)
- Forge iteration loop (test→iterate; today: generate→scan→save) per stronghold v1.2 plans now riding on engine

## v1.2 (6–9 months)

- Memory v2 (engine-led; if any product surfaces a need that ADR-011…017 don't cover, an engine ADR proposes the change)
- Mid-session model switching primitive (currently roadmapped in AgentTuring epic-10; engine-side support if it generalises)
- DSPy-style task signatures evaluation (epic-07)

## v2.0 (12 months) — inventory-clear

- Every accepted ADR/spec across the four repos is `Implemented` or `Superseded` or `Abandoned`. No long-standing `Accepted; gap-impl`.
- Ontology Kinetic + Dynamic facets shipped
- Cross-tenant ontology sharing (a stronghold concern; engine support)
- Tournament-based agent evolution wired to production routing (where products want it)
- Compliance certifications (delegated to stronghold COMPLIANCE.md and audit work)

## Non-goals for the engine

- **Multi-tenancy.** Owned by `stronghold`. Engine ships the simple form per [`ADR-035`](docs/adr/ADR-035-catalog-ownership-split.md).
- **Autonoetic loops.** Owned by `AgentTuring`. Engine provides primitives (memory, mood, drives) but does not run the loop.
- **Self-host UX.** Owned by `Project_mAIstro`. Engine does not ship a setup wizard or household management.
- **End-user UI.** None of the products are end-user facing from the engine; the engine ships as a Python library.

## How this ROADMAP is maintained

- Updates land alongside the work that drives them, not as separate doc-only PRs.
- Each milestone is a coordination point for cross-repo PRs (engine + at least one product).
- The progress dashboard below is regenerated; do not hand-edit unless registry CI is unavailable.

## Progress dashboard

Updated 2026-05-07 (manual; will be regenerated by registry CI once Phase 0g lands):

```
M1 Conventions enforced     [~] ████████░░  80%   ADR-030..035 + 036..038 landed; registry CI tooling pending (Phase 0g)
M2 Templates bootstrapped   [·] ░░░░░░░░░░   0%   Pending Phase 0g + bootstrap PRs in each product repo
M3 Drift items closed        [~] █████░░░░░  50%   Memory + catalog ADRs accepted (034/035); spec-side dedup pending (3c/3d)
M4 Substrate code parity     [·] ░░░░░░░░░░   0%   ADRs 036/037/038 accepted; gap-impl across the board
M5 Contracts as the bar      [~] ███░░░░░░░  30%   ADR-032 accepted + Stronghold's existing Spec type / mutmut config; engine adoption pending
```

Legend: `[x]` complete | `[~]` in progress | `[·]` not started
