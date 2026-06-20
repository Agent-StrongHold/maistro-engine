# Roadmap (Four-Repo Canonical)

**Identical copies live in every repo of the four-repo system:**

- [`BlakeMatthews-dev/maistro-engine`](https://github.com/BlakeMatthews-dev/maistro-engine) (substrate)
- [`BlakeMatthews-dev/Project_mAIstro`](https://github.com/BlakeMatthews-dev/Project_mAIstro) (single-tenant secure multi-user)
- [`BlakeMatthews-dev/AgentTuring`](https://github.com/BlakeMatthews-dev/AgentTuring) (autonoetic experiment)
- [`agent-stronghold/stronghold`](https://github.com/agent-stronghold/stronghold) (multi-tenant enterprise)

Any edit lands in all four (or, until registry CI ships, in as many as the editor has access to). The full BACKLOG is the companion: see [`BACKLOG.md`](BACKLOG.md). The four-repo governance that defines this layout is [`engine#ADR-030`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/adr/ADR-030-four-repo-governance.md).

## Item ID convention (per [`engine#ADR-031`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/adr/ADR-031-front-matter-and-registry.md))

Every roadmap and backlog item is tagged by its **owning repo**:

| Prefix | Repo | Concern |
|---|---|---|
| `engine-NNN` | `maistro-engine` | Substrate library, canonical ADRs, Copier templates, registry CI |
| `maistro-NNN` | `Project_mAIstro` | Single-tenant multi-user product (self-hosting, household/team UX) |
| `turing-NNN` | `AgentTuring` | Autonoetic experimental product (continuity of self) |
| `sh-NNN` | `stronghold` | Multi-tenant enterprise product (compliance + isolation) |

Cross-repo references use `[repo#item-id]` notation, e.g. `[engine#engine-030]` or `[turing#turing-035]`.

## The system at a glance

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
       │ Project_mAIstro│        │ AgentTuring  │         │  stronghold  │
       │ single-tenant │         │ autonoetic   │         │ multi-tenant │
       │ multi-user   │         │ experiment   │         │ enterprise  │
       │ self-hosted  │         │ 24/7 self-   │         │             │
       │             │         │ awareness    │         │             │
       └──────────────┘          └──────────────┘         └──────────────┘
        ease of self-host       continuity of self      multi-tenant isolation
```

| Repo | Role | Dominant constraint |
|---|---|---|
| `maistro-engine` | Substrate library + canonical ADRs + Copier templates + registry CI | n/a (it is the substrate) |
| `Project_mAIstro` | Single-tenant secure multi-user product | **Ease of self-hosting** |
| `AgentTuring` | Autonoetic experimental agent | **Continuity of self** |
| `stronghold` | Multi-tenant enterprise product | **Multi-tenant isolation** |

## Horizons (per [`engine#ADR-030`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/adr/ADR-030-four-repo-governance.md))

- **v1.0** — 3 months. Per-product MVPs ship; substrate code parity reached.
- **v1.1–1.3** — 3–12 months. Hardening and inventory drainage.
- **v2.0** — 12 months. Inventory-clear: every accepted ADR/spec is `Implemented`, `Superseded`, or `Abandoned`.

---

## v1.0 (3 months) — organised by cross-repo phase

Phases A–D run sequentially-ish in the substrate. Phase E (per-product v1.0) runs in parallel from week 1, gated by the substrate items it depends on. Phase F (contracts as the bar) ramps from week 6.

### Phase A — Foundation enforcement (weeks 1–4)

| Item | Owner | Status | Detail |
|---|---|---|---|
| `[engine-001]` Registry CI tooling | engine | Accepted; `gap-impl` | Front-matter validator + cross-repo link checker + registry generator + GitHub Action; warn-only → hard fail at day 30 |
| `[engine-002]` INVENTORY auto-regenerated | engine | Proposed | Once `engine-001` lands, hand-edits to INVENTORY fail CI |
| `[engine-003]` Front-matter on existing engine ADRs | engine | Accepted; gradual | ADRs 000–029 gain front-matter on touch (not bulk) |
| `[engine-004]` CONTRIBUTING.md and convention docs | engine | Proposed | Author-facing summary of ADR-031/032/001 |
| `[turing-090]` Front-matter on Turing specs | turing | Proposed; warn-only | 22 top-level + ~70 nested epic stories |
| `[sh-090]` Front-matter on Stronghold specs | sh | Proposed; warn-only | Mirror of Turing's spec set during transition; will diverge post-Copier |
| `[maistro-090]` Front-matter on mAIstro specs | maistro | Proposed; warn-only | 91 specs (`S-NNN` → `SPEC-NNN` on touch) |

### Phase B — Templates bootstrapped (weeks 2–6)

| Item | Owner | Status | Detail |
|---|---|---|---|
| `[engine-010]` Copier template `single-tenant-multi-user` | engine | Accepted; `gap-impl` | Knobs: `users_max`, `auth_backend`, `channels`, `host_target`. Round-trips against Project_mAIstro |
| `[engine-011]` Copier template `autonoetic` | engine | Accepted; `gap-impl` | Knobs: `awareness_loop_hz`, `self_model`, `memory_consolidator`, `dossier_store`. Round-trips against AgentTuring |
| `[engine-012]` Copier template `multi-tenant` | engine | Accepted; `gap-impl` | Knobs: `tenants_max`, `policy_engine`, `deploy_target`, `compliance_pack`. Round-trips against stronghold |
| `[engine-013]` Two-stream release pipeline | engine | Proposed | `pkg/v*` + `template/v*` tags |
| `[maistro-095]` Copier bootstrap | maistro | Proposed; `gap-impl` | `copier copy` against fresh dir; close diff over 1–2 PRs |
| `[turing-043]` Copier bootstrap | turing | Proposed; `gap-impl` | Same pattern |
| `[sh-095]` Copier bootstrap | sh | Proposed; `gap-impl` | Same pattern |

### Phase C — Drift closure (weeks 3–7)

Resolves the inventory drift items flagged at the start of the four-repo split.

| Item | Owner | Status | Detail |
|---|---|---|---|
| `[engine-020]` K8S-* ADR migration AT → stronghold | engine (coordinator) | Accepted; `gap-impl` | 31 ADR-K8S-* records move from AgentTuring to stronghold per `[engine#ADR-030]` §4 |
| `[turing-042]` Migrate K8S-* records out of AgentTuring | turing | Accepted; `gap-impl` | Side of `engine-020` |
| `[sh-020]` Receive K8S-* records (renumbered, with substrate refs) | sh | Accepted; `gap-impl` | Catalog ones (K8S-021–023, 027) gain `substrate: [engine#ADR-006/009]` |
| `[engine-021]` Memory spec dedup | engine (coordinator) | Accepted; `gap-impl` | Engine ADR-011…017 canonical; product specs become `Substrate:`-cited |
| `[turing-091]` Memory specs `Substrate:` recast | turing | Accepted; `gap-impl` | `turing-dossier`, `turing-memory-consolidator`, `turing-notebook-live-vault`, `turing-obsidian-store` |
| `[maistro-091]` Memory specs `Substrate:` recast | maistro | Proposed; `gap-impl` | `S-008`, `S-009`, `S-032`, `S-033` |
| `[engine-022]` Catalog spec dedup | engine (coordinator) | Accepted; `gap-impl` | Engine simple form + stronghold multi-tenant variant per `[engine#ADR-035]` |
| `[maistro-092]` Catalog specs `Substrate:` recast | maistro | Proposed; `gap-impl` | `S-005`, `S-138` cite engine ADR-006/009 |

### Phase D — Substrate code parity (weeks 4–9)

The three engine ADRs that closed `gap-spec` items (036/037/038) become `Implemented`.

| Item | Owner | Status | Detail |
|---|---|---|---|
| `[engine-030]` Ontology Semantic facet | engine | Accepted; `gap-impl` | Per `[engine#ADR-036]`. v1.0 ships Semantic only; Kinetic + Dynamic deferred to v2.0 |
| `[engine-031]` Observability primitives | engine | Accepted; `gap-impl` | Per `[engine#ADR-037]`. 12 required spans, 6 metrics, 5 event topics |
| `[engine-032]` Reliability primitives | engine | Accepted; `gap-impl` | Per `[engine#ADR-038]`. retry / circuit-breaker / fallback / SLO / healthchecks |

### Phase E — Per-product v1.0 (weeks 1–12, parallel to A–D)

Each product has its own v1.0 acceptance gate. Detail in product `ROADMAP-v1.0.md` files.

#### `Project_mAIstro` v1.0 — multi-user with hard isolation + setup wizard

Dominant constraint: ease of self-hosting.

| Item | Status | Detail |
|---|---|---|
| `[maistro-001]` Setup wizard | Proposed | `S-139` is the spec; v1.0 critical path |
| `[maistro-002]` Per-user memory isolation | Proposed | Hard boundary; cross-user retrieval impossible by construction |
| `[maistro-003]` Multi-user auth (Keycloak / JWT) | Proposed | `S-018`, `S-019`, `S-024` |
| `[maistro-004]` Native install + Podman + systemd | Proposed | `S-147`, `S-148` |
| `[maistro-005]` Tailscale-native networking | Proposed | `S-153` |
| `[maistro-006]` Setup-wizard property test | Proposed | A new household can complete setup in < 30 min |
| `[maistro-007]` Per-user isolation property test | Proposed | Cross-user retrieval is structurally impossible |

#### `AgentTuring` v1.0 — measurable autonoesis

Dominant constraint: continuity of self. See [`AgentTuring/ROADMAP-v1.0.md`](https://github.com/BlakeMatthews-dev/AgentTuring/blob/main/ROADMAP-v1.0.md) for full property-test detail.

| Item | Status | Detail |
|---|---|---|
| `[turing-001]` HEXACO-24 + weekly retest | Proposed | Drift bound ≤ 0.05 L₂ weekly |
| `[turing-002]` Mood vector with decay + bounded delta | Proposed | No NaN, no unbounded values |
| `[turing-003]` Drive store with reinforcement and decay | Proposed | Passions, hobbies, interests, skills, preferences |
| `[turing-004]` `SelfModel`, `Mood`, `Drive` ontology registration | Proposed | Depends on `engine-030` |
| `[turing-010]` 7-tier memory implementation | Proposed | OBSERVATION → WISDOM |
| `[turing-011]` Weight floors REGRET (≥0.6) WISDOM (≥0.9) | Proposed | Structurally unforgettable |
| `[turing-012]` Activation graph with self-authored edges | Proposed | The self authors edges |
| `[turing-013]` Todo → episode provenance enforcement | Proposed | Required at the data model |
| `[turing-020]` Continuous self-talk loop | Accepted; `gap-impl` | Spec exists; runnable sketch only |
| `[turing-021]` Awareness loop hz tunable | Proposed | Copier knob |
| `[turing-022]` Memory consolidation at idle | Accepted; `gap-impl` | `turing-memory-consolidator.yaml` |
| `[turing-023]` Dossier generation | Accepted; `gap-impl` | `turing-dossier.yaml` |
| `[turing-030]`…`[turing-034]` Five property tests | Proposed | Identity continuity, narrative consistency, decision provenance, mood plausibility, memory floor preservation |
| `[turing-035]` 30-day staging run | Proposed | All five property tests asserted; v1.0 acceptance gate |

#### `stronghold` v1.0 — compliance-first

Dominant constraint: multi-tenant isolation. See [`stronghold/ROADMAP-v1.0.md`](https://github.com/agent-stronghold/stronghold/blob/main/ROADMAP-v1.0.md) for the full eight-workstream detail.

| Item | Status | Detail |
|---|---|---|
| `[sh-001]` Multi-tenant catalog wrapper | Proposed; `gap-impl` | Wraps engine simple form per `[engine#ADR-035]` |
| `[sh-002]` Tenant-scoped namespacing for agents/skills/tools/recipes/MCP | Proposed | |
| `[sh-003]` Cross-tenant catalog import (with consent) | Proposed | OAuth-style consent; revocable |
| `[sh-010]` OPA / Rego policy adapter | Proposed; `gap-impl` | Hot-reload, < 1ms p99 at 1000 RPS |
| `[sh-011]` Cedar policy adapter | Proposed; `gap-impl` | Same |
| `[sh-012]` Sentinel policy bridge | Proposed | Existing path stays available |
| `[sh-020]` K8S-* ADRs migrated in (renumbered, with substrate refs) | Accepted; `gap-impl` | Side of `engine-020` |
| `[sh-030]` COMPLIANCE.md OWASP Agentic Top 10 | Proposed; `gap-impl` | Module + test citations per control; gap markers honest |
| `[sh-031]` COMPLIANCE.md NIST AI RMF stub | Proposed | Govern / Map / Measure / Manage |
| `[sh-032]` COMPLIANCE.md EU AI Act stub | Proposed | Articles 9–15, 17, 26 |
| `[sh-040]` Two-tenant red-team CI | Proposed; `gap-impl` | Hypothesis-driven cross-tenant probe gen |
| `[sh-050]` On-prem (OKD) + cloud (AKS) parity | Proposed; `gap-impl` | Same Helm + image set |
| `[sh-060]` Append-only audit chain (signed, hash-chained) | Proposed; `gap-impl` | Indefinite retention |

#### `maistro-engine` (Hive Conductor) — distribution & frontend completion

Migrated from the archived `docs/archive/MASTER-PLAN.md` + `docs/archive/PRODUCT-SPEC.md`; detail in `BACKLOG.md` `[engine-100]`–`[engine-105]`.

| Item | Status | Detail |
|---|---|---|
| `[engine-100]` Hosted curl installer + web wizard | Proposed | `get.hiveconductor.com` distribution; local `get.sh`/`install.sh` only cover manual clone today |
| `[engine-101]` GHCR image publishing pipeline | Proposed | Blocks `engine-100` |
| `[engine-102]` Frontend completion vs. archived PRODUCT-SPEC | Proposed; `gap-impl` | Page-by-page coverage unverified |
| `[engine-103]` MCP server implementations | Proposed | Decide wrap-existing-tools vs. build-new |
| `[engine-104]` Port remaining Project mAIstro experimental features | Proposed | Bouncer, Agent Factory, Spawner, APM, Heartbeat, Red Team, Skill Forge, Message Board |
| `[engine-105]` Wire Master Orchestrator security gate + API dispatch | Accepted; `gap-impl` | J1–J4 shipped (`orchestrator/master.py`, `planner.py`); J5/J6 open |

### Phase F — Contracts as the bar (weeks 6–12)

Per [`engine#ADR-032`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/adr/ADR-032-contracts-as-acceptance-criteria.md). Mutation-testing kill rate is the v1.0 quality bar.

| Item | Owner | Status | Detail |
|---|---|---|---|
| `[engine-040]` Pydantic boundary contracts on all public types | engine | Proposed | ≥95% mutation kill rate |
| `[engine-041]` Hypothesis property tests on accepted behavioral ADRs | engine | Proposed | ≥80% kill rate |
| `[engine-042]` Pact-style contracts on A2A + MCP edges | engine | Proposed | ≥75% kill rate; tooling choice deferred to a separate ADR (`engine-080`) |
| `[engine-043]` Mutation-testing CI wiring | engine | Proposed | Nightly + on-merge; not on every PR |
| `[turing-095]` Adopt contract markers | turing | Proposed | `pytest.mark.contract` / `pytest.mark.scope` per ADR-032 |
| `[sh-095]` Adopt contract markers | sh | Proposed | Same |
| `[maistro-095]` Adopt contract markers | maistro | Proposed | Same |

---

## v1.1 (3–6 months) — hardening

| Item | Owner | Status | Detail |
|---|---|---|---|
| `[engine-050]` Cross-product agent portability proof | engine | Proposed | Export from mAIstro → import into stronghold tenant catalog without recoding |
| `[engine-051]` Forge iteration loop primitive | engine | Proposed | Generalises stronghold's planned test→iterate loop |
| `[engine-052]` Compliance gap audit on accepted ADRs | engine | Proposed | Feeds stronghold COMPLIANCE.md control claims |
| `[turing-050]` Lineage queries | turing | Proposed | "What did you used to think about X?" returns a snapshot |
| `[turing-051]` Dream loop | turing | Proposed | Offline replay + consolidation |
| `[turing-052]` Phantom execution | turing | Proposed | The self can simulate a route without committing |
| `[turing-053]` Adversarial hardening of the self-model | turing | Proposed | Probe for inconsistency or drift attacks |
| `[sh-100]` Trust-tier auto-promotion gates | sh | Proposed | Currently manual (`update_trust_tier`) |
| `[sh-101]` Forge iteration loop — stronghold side | sh | Proposed | Wires `engine-051` into Forge agent |
| `[sh-102]` Tournament evolution wired to internal-only routing | sh | Proposed | Production traffic in v2.0 |
| `[maistro-100]` Voice + email + Alexa channels | maistro | Proposed | `S-041`…`S-104` |
| `[maistro-101]` Hardware-signing integration | maistro | Proposed | `S-150` (substrate: `engine#ADR-022`) |

## v1.2 (6–9 months) — RASO inner loop + memory v2 if surfaced

| Item | Owner | Status | Detail |
|---|---|---|---|
| `[engine-060]` Memory v2 (if a product surfaces a need) | engine | Proposed | Engine ADR-led; products do not silently extend |
| `[engine-061]` DSPy-style task signatures evaluation | engine | Proposed | Driver: `turing#epic-07` |
| `[engine-062]` Mid-session model switching primitive | engine | Proposed | Driver: `turing#epic-10` |
| `[turing-060]` `epic-13-hyperagents-meta-level` formalised | turing | Proposed | Turing-specific concrete |
| `[turing-061]` RASO inner cycle wired to self-talk | turing | Proposed | Auditor→Mason→extract→store→track |
| `[turing-062]` Tournament evolution scaffolding (internal-only) | turing | Proposed | |
| `[sh-200]` Forge test→iterate loop | sh | Proposed | |
| `[sh-201]` Memory decay function in learnings | sh | Proposed | Engine substrate likely |

## v1.3 (9–12 months) — RASO meta-agent + agent marketplace

| Item | Owner | Status | Detail |
|---|---|---|---|
| `[turing-070]` Meta-agent that modifies activation graph | turing | Proposed | Self-modifying graph; v1.0 property tests gate edits |
| `[turing-071]` Parameter-sensitivity learner | turing | Proposed | Which knobs to turn by inches, which by leaps |
| `[turing-072]` Self-modification gate | turing | Proposed | Property tests re-run after every meta-agent edit |
| `[sh-300]` Agent marketplace (cross-tenant catalog discovery) | sh | Proposed | |
| `[sh-301]` Multi-region failover | sh | Proposed | |

## v2.0 (12+ months) — inventory-clear

| Item | Owner | Status | Detail |
|---|---|---|---|
| `[engine-070]` Ontology Kinetic facet | engine | Proposed | Actions an entity exposes, with pre/post-condition contracts |
| `[engine-071]` Ontology Dynamic facet | engine | Proposed | State transitions, version history, derivation lineage |
| `[engine-072]` Cross-tenant ontology sharing primitive | engine | Proposed | Stronghold-driven |
| `[engine-073]` Tournament-based agent evolution wired to production routing | engine | Proposed | Substrate piece |
| `[turing-080]` Self-model export / import | turing | Proposed | Strongest test of autonoesis |
| `[turing-081]` Long-horizon recall with confidence calibration | turing | Proposed | |
| `[turing-082]` Synthesised mood + drives from imported episodic record | turing | Proposed | |
| `[turing-083]` Confidence-calibrated routing | turing | Proposed | Substrate piece if it generalises |
| `[sh-400]` SOC 2 Type II audit | sh | Proposed | |
| `[sh-401]` ISO 27001 readiness | sh | Proposed | |
| `[sh-402]` Sectoral regulators (HIPAA, FedRAMP) | sh | Proposed | Per customer demand |
| `[maistro-300]` Cross-self portability for households | maistro | Proposed | If `turing-080` substrates cleanly |

---

## Cross-repo dependency graph (v1.0 critical path)

```
engine-001 (Registry CI)
    │
    ├─→ engine-002 (INVENTORY auto-regen)
    ├─→ engine-021 (Memory dedup)
    │       └─→ turing-091 + maistro-091 (Substrate recast)
    ├─→ engine-022 (Catalog dedup)
    │       └─→ maistro-092 (catalog Substrate recast)
    ├─→ turing-090 + sh-090 + maistro-090 (front-matter)
    └─→ (CI flips hard at day 30)

engine-010/011/012 (Copier templates)
    │
    ├─→ maistro-095 (bootstrap into single-tenant template)
    ├─→ turing-043 (bootstrap into autonoetic template)
    └─→ sh-095 (bootstrap into multi-tenant template)

engine-030 (Ontology)
    └─→ turing-004 (SelfModel/Mood/Drive ontology registration)

engine-031 (Observability)
    ├─→ turing-020 (self-talk loop instrumentation)
    └─→ sh-060 (audit chain)

engine-032 (Reliability)
    ├─→ turing-035 (30-day staging run stability)
    └─→ sh-050 (on-prem + cloud parity)

engine-020 (K8S-* migration coordinator)
    ├─→ turing-042 (move out of AgentTuring)
    └─→ sh-020 (receive into stronghold, renumber, substrate refs)
```

## Progress dashboard

Updated 2026-05-07 (manual; will be regenerated by registry CI once `engine-001` lands):

```
Phase A Foundation enforcement      [~] ████████░░  80%   ADRs landed; registry CI tooling pending
Phase B Templates bootstrapped      [·] ░░░░░░░░░░   0%   Pending engine-001
Phase C Drift closure                [~] █████░░░░░  50%   Memory + catalog ADRs accepted; spec-side dedup pending
Phase D Substrate code parity        [·] ░░░░░░░░░░   0%   ADRs accepted; gap-impl across the board
Phase E.maistro mAIstro v1.0         [·] ░░░░░░░░░░   0%   Specs exist (S-NNN); impl pending
Phase E.turing  Turing v1.0          [~] ██░░░░░░░░  20%   Memory tier scaffold + sketches; property tests pending
Phase E.sh      Stronghold v1.0      [~] ██████░░░░  60%   Three-boundary scan + memory + RBAC live; multi-tenant + compliance pending
Phase F Contracts as the bar         [~] ███░░░░░░░  30%   stronghold has Spec type + mutmut; engine adoption pending
```

Legend: `[x]` complete | `[~]` in progress | `[·]` not started

## Per-product detail

- mAIstro v1.0 detail — see [`Project_mAIstro/ROADMAP-v1.0.md`](https://github.com/BlakeMatthews-dev/Project_mAIstro/blob/main/ROADMAP-v1.0.md) (proposal pending; lives in `engine/docs/proposals/Project_mAIstro/` until applied)
- Turing v1.0 detail — see [`AgentTuring/ROADMAP-v1.0.md`](https://github.com/BlakeMatthews-dev/AgentTuring/blob/main/ROADMAP-v1.0.md)
- Stronghold v1.0 detail — see [`stronghold/ROADMAP-v1.0.md`](https://github.com/agent-stronghold/stronghold/blob/main/ROADMAP-v1.0.md)

## Maintenance

- This file is **identical across all four repos**. Any edit lands in all four.
- Items get appended; status changes happen in-place. IDs are stable; never renumbered.
- Once `engine-001` (registry CI) ships, ROADMAP and BACKLOG are regenerated from front-matter; hand-edits then fail CI.
- Conflicts between this canonical roadmap and a per-product `ROADMAP-v1.0.md` resolve in favor of this one, except for v1.0 acceptance test detail (which lives in the per-product file by design).
