# Backlog (Four-Repo Canonical)

**Identical copies live in every repo of the four-repo system.** Companion to [`ROADMAP.md`](ROADMAP.md). Every item is tagged with its **owning repo** via the prefix:

- `engine-NNN` — `maistro-engine`
- `maistro-NNN` — `Project_mAIstro`
- `turing-NNN` — `AgentTuring`
- `sh-NNN` — `stronghold`

Cross-repo references use `[repo#item-id]` notation.

Maintained per [`engine#ADR-030`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/adr/ADR-030-four-repo-governance.md). Status follows [`engine#ADR-031`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/adr/ADR-031-front-matter-and-registry.md) lifecycle. Gap markers per [`docs/INVENTORY-ADRS-SPECS.md`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/INVENTORY-ADRS-SPECS.md).

## Status legend

| Marker | Meaning |
|---|---|
| Proposed | Open for discussion; not yet binding |
| Accepted | Decision binding; implementation may follow |
| Implemented | Decision shipped; production code matches |
| Superseded | Replaced by a successor (named in `supersedes:` of successor) |
| Blocked | A `blocked-by:` dependency is unmet |
| Abandoned | Decision deliberately not taken (kept for traceability) |

## Gap legend

| Marker | Meaning |
|---|---|
| `gap-spec` | No spec or ADR captures this decision yet |
| `gap-test` | Spec/ADR exists; no test (or test stub) covers it |
| `gap-impl` | Spec/ADR + test exist; production code does not match |

---

## `maistro-engine` items

### Foundation (M1 — weeks 1–4)

**[engine-001] Registry CI tooling — Accepted; `gap-impl` — v1.0 M1**
- Front-matter YAML validator (Pydantic schema from ADR-031)
- Cross-repo link checker via GitHub MCP / API: every `<repo>#<id>` resolves
- Registry generator: emits `registry/registry.json` and `registry.md`
- DAG validator on `supersedes:` and `blocks:` (no cycles)
- GitHub Action wiring: warn-only mode, hard-fail flip after day 30
- Tests: contract `boundary | unit` for the validator; `behavioral | property` for the DAG check

**[engine-002] INVENTORY auto-regenerated — Proposed — v1.0 M1**
- Hand-edits to `docs/INVENTORY-ADRS-SPECS.md` fail CI once tooling lands
- File becomes the registry's human-readable rendering
- Blocked-by: `engine-001`

**[engine-003] Front-matter on existing engine ADRs — Accepted; gradual — v1.0 M1**
- ADRs 000–029 (30 files) lack front-matter
- Per ADR-031: renumber-on-touch; not a bulk migration
- ADR-000 template regenerated to match the new schema

**[engine-004] CONTRIBUTING.md and convention docs — Proposed — v1.0 M1**
- Author-facing summary of ADR-031 (front-matter), ADR-032 (contracts), ADR-001 (branching)
- Linked from README; linked from product repos' READMEs

### Templates (M2 — weeks 2–6)

**[engine-010] Copier template `single-tenant-multi-user` — Accepted; `gap-impl` — v1.0 M2**
- Knobs: `users_max`, `auth_backend (keycloak | local)`, `channels (web | voice | email)`, `host_target (podman | docker | systemd)`
- Round-trip against `Project_mAIstro`

**[engine-011] Copier template `autonoetic` — Accepted; `gap-impl` — v1.0 M2**
- Knobs: `awareness_loop_hz`, `self_model (hexaco | minimal)`, `memory_consolidator (on | off)`, `dossier_store (obsidian | fs)`
- Round-trip against `AgentTuring`

**[engine-012] Copier template `multi-tenant` — Accepted; `gap-impl` — v1.0 M2**
- Knobs: `tenants_max`, `policy_engine (opa | cedar | sentinel)`, `deploy_target (k8s | on-prem | hybrid)`, `compliance_pack (owasp | nist | euaiact | all)`
- Round-trip against `stronghold`

**[engine-013] Two-stream release pipeline — Proposed — v1.0 M2**
- `pkg/v*` for the Python package
- `template/v*` for Copier template snapshots
- Blocked-by: `engine-010`, `engine-011`, `engine-012`

### Drift closure (M3 — weeks 3–7)

**[engine-020] K8S-* ADR migration AT → stronghold (coordinator) — Accepted; `gap-impl` — v1.0 M3**
- 31 `ADR-K8S-*` records leave AgentTuring, arrive in stronghold
- Renumbered to unified `ADR-NNN` per `[engine#ADR-031]`
- Catalog-related ones (K8S-021, K8S-022, K8S-023, K8S-027) gain `substrate: [engine#ADR-006]` / `[engine#ADR-009]`
- Coordinated with `[turing-042]` and `[sh-020]`

**[engine-021] Memory spec dedup (coordinator) — Accepted; `gap-impl` — v1.0 M3**
- Engine ADR-011…017 stay canonical
- Coordinated with `[turing-091]` and `[maistro-091]`

**[engine-022] Catalog spec dedup (coordinator) — Accepted; `gap-impl` — v1.0 M3**
- Engine simple form per `[engine#ADR-006]`/`[engine#ADR-009]`; Stronghold owns multi-tenant variant per `[engine#ADR-035]`
- Coordinated with `[maistro-092]`

### Substrate code parity (M4 — weeks 4–9)

**[engine-030] Ontology Semantic facet — Accepted; `gap-impl` — v1.0 M4**
- Per `[engine#ADR-036]`. Implements `OntologyEntity`, `Ontology` protocol, registry, persistence
- v1.0 ships Semantic only; Kinetic + Dynamic deferred
- Memory record gains optional `entity_id: UUID | None` field

**[engine-031] Observability primitives — Accepted; `gap-impl` — v1.0 M4**
- Per `[engine#ADR-037]`. Required spans, metrics, event topics
- Sampling defaults configurable per service-key

**[engine-032] Reliability primitives — Accepted; `gap-impl` — v1.0 M4**
- Per `[engine#ADR-038]`. retry / circuit-breaker / fallback / SLO / healthchecks
- Hypothesis property test on circuit-breaker state machine

### Contracts (M5 — weeks 6–12)

**[engine-040] Pydantic boundary contracts on all public types — Proposed — v1.0 M5**
- ≥95% mutation kill rate at v1.0

**[engine-041] Hypothesis property tests on accepted behavioral ADRs — Proposed — v1.0 M5**
- Adopt stronghold's `Spec` type pattern in the engine
- ≥80% mutation kill rate

**[engine-042] Pact-style contracts on A2A + MCP edges — Proposed — v1.0 M5**
- ≥75% mutation kill rate
- Tooling choice deferred to `engine-080`

**[engine-043] Mutation-testing CI wiring — Proposed — v1.0 M5**
- Adopt stronghold's `mutmut` config
- Nightly + on-`main`-merge schedule

### v1.1 (engine)

**[engine-050] Cross-product agent portability proof — Proposed — v1.1**
- Serialise from mAIstro simple catalog → import into stronghold tenant catalog without recoding

**[engine-051] Forge iteration loop primitive — Proposed — v1.1**
- Generalise stronghold's planned test→iterate loop

**[engine-052] Compliance gap audit on accepted ADRs — Proposed — v1.1**
- Feeds stronghold COMPLIANCE.md control claims

### v1.2 (engine)

**[engine-060] Memory v2 (if surfaced) — Proposed — v1.2**
- Engine-led; products do not silently extend

**[engine-061] DSPy-style task signatures evaluation — Proposed — v1.2**
- Driver: `turing#epic-07`

**[engine-062] Mid-session model switching primitive — Proposed — v1.2**
- Driver: `turing#epic-10`

### v2.0 (engine)

**[engine-070] Ontology Kinetic facet — Proposed — v2.0**
- Actions an entity exposes, with pre/post-condition contracts

**[engine-071] Ontology Dynamic facet — Proposed — v2.0**
- State transitions, version history, derivation lineage

**[engine-072] Cross-tenant ontology sharing primitive — Proposed — v2.0**
- Stronghold-driven

**[engine-073] Tournament-based agent evolution wired to production routing — Proposed — v2.0**

### Discovered gaps (engine)

**[engine-080] Pact tooling choice — Proposed**
- `pact-python` vs hand-rolled — separate ADR resolves

**[engine-081] Mutation-testing exclusion list per repo — Proposed**
- Equivalent mutants and unavoidable survivors

**[engine-082] Backup / export semantics for memory — Proposed**
- Out of scope of ADR-034

**[engine-083] Disaster-recovery / backup-restore primitives — Proposed**
- Out of scope of ADR-038; stronghold v1.x will need

**[engine-084] Chaos-engineering harness — Proposed**
- Out of scope of ADR-038; would feed `[sh-040]` red-team CI

**[engine-085] Trace export to long-term storage — Proposed**
- Out of scope of ADR-037; relevant for compliance evidence retention

---

## `Project_mAIstro` items

### v1.0 — multi-user with hard isolation + setup wizard

**[maistro-001] Setup wizard — Proposed — v1.0**
- Spec: `S-139`. Critical path for v1.0
- Acceptance: a new household can complete setup in < 30 minutes

**[maistro-002] Per-user memory isolation — Proposed — v1.0**
- Hard boundary at the storage layer
- Property test: cross-user retrieval is structurally impossible

**[maistro-003] Multi-user auth (Keycloak / JWT) — Proposed — v1.0**
- Specs: `S-018`, `S-019`, `S-024`

**[maistro-004] Native install + Podman + systemd — Proposed — v1.0**
- Specs: `S-147`, `S-148`

**[maistro-005] Tailscale-native networking — Proposed — v1.0**
- Spec: `S-153`

**[maistro-006] Setup-wizard property test — Proposed — v1.0**

**[maistro-007] Per-user isolation property test — Proposed — v1.0**

### Documentation hygiene (parallel to v1.0)

**[maistro-090] Front-matter on mAIstro specs — Proposed; `gap-spec` — v1.0 (warn-only)**
- 91 specs; renumber-on-touch (`S-NNN` → `SPEC-NNN`)

**[maistro-091] Memory specs `Substrate:` recast — Proposed; `gap-impl` — v1.0 M3**
- `S-008 session-summarization` → `substrate: [engine#ADR-018]`
- `S-009 episodic-memory-bridge` → `substrate: [engine#ADR-016]`
- `S-032 episodic-memory` → `substrate: [engine#ADR-016]`
- `S-033 memory-evolution` → `substrate: [engine#ADR-017]`

**[maistro-092] Catalog specs `Substrate:` recast — Proposed; `gap-impl` — v1.0 M3**
- `S-005 agent-factory` → `substrate: [engine#ADR-009]`
- `S-138 agent-conductor` → `substrate: [engine#ADR-005]` `[engine#ADR-006]` `[engine#ADR-009]`

**[maistro-095] Copier bootstrap — Proposed; `gap-impl` — v1.0 M2**
- Round-trip into `engine/templates/single-tenant-multi-user/`

### v1.1 (mAIstro)

**[maistro-100] Voice + email + Alexa channels — Proposed — v1.1**
- Specs: `S-041`, `S-042`, `S-043`, `S-103`, `S-104`

**[maistro-101] Hardware-signing integration — Proposed — v1.1**
- Spec: `S-150`. Substrate: `[engine#ADR-022]`

**[maistro-102] Internal trust root — Proposed — v1.1**
- Spec: `S-155`. Substrate: `[engine#ADR-026]`

**[maistro-103] DID/VC agent identity — Proposed — v1.1**
- Spec: `S-152`. Substrate: `[engine#ADR-024]`

### v1.2 (mAIstro)

**[maistro-200] Hyperagent graph runtime — Proposed — v1.2**
- Spec: `S-145`

**[maistro-201] Node-graph designer (low-code) — Proposed — v1.2**
- Spec: `S-159`. Closest analogue to Palantir AIP "Workshop"

**[maistro-202] Human-as-node HITL primitive — Proposed — v1.2**
- Spec: `S-158`

### v2.0 (mAIstro)

**[maistro-300] Cross-self portability for households — Proposed — v2.0**
- If `[turing-080]` substrates cleanly

### Items deferred / abandoned (mAIstro)

*(empty at present; pending mAIstro repo access)*

---

## `AgentTuring` items

### v1.0 — measurable autonoesis

Full detail in [`AgentTuring/ROADMAP-v1.0.md`](https://github.com/BlakeMatthews-dev/AgentTuring/blob/main/ROADMAP-v1.0.md).

**[turing-001] HEXACO-24 + weekly retest — Proposed; `gap-impl` — v1.0 M1**
- Drift bound ≤ 0.05 L₂ weekly under no-stress conditions
- First month calibrates the bound

**[turing-002] Mood vector with decay + bounded delta — Proposed; `gap-impl` — v1.0 M1**

**[turing-003] Drive store with reinforcement and decay — Proposed; `gap-impl` — v1.0 M1**

**[turing-004] `SelfModel`, `Mood`, `Drive` ontology registration — Proposed; `gap-impl` — v1.0 M1**
- Blocked-by: `[engine-030]`

**[turing-010] 7-tier memory implementation — Proposed; `gap-impl` — v1.0 M2**
- Substrate: `[engine#ADR-016]`, `[engine#ADR-017]`

**[turing-011] Weight floors REGRET (≥0.6) WISDOM (≥0.9) — Proposed; `gap-impl` — v1.0 M2**

**[turing-012] Activation graph with self-authored edges — Proposed; `gap-impl` — v1.0 M2**

**[turing-013] Todo → episode provenance enforcement — Proposed; `gap-impl` — v1.0 M2**

**[turing-020] Continuous self-talk loop — Accepted (spec); `gap-impl` — v1.0 M3**
- Spec: `specs/turing-self-talk-loop.yaml`

**[turing-021] Awareness loop hz tunable — Proposed — v1.0 M3**
- Copier knob in `[engine-011]`

**[turing-022] Memory consolidation at idle — Accepted (spec); `gap-impl` — v1.0 M3**
- Spec: `specs/turing-memory-consolidator.yaml`

**[turing-023] Dossier generation — Accepted (spec); `gap-impl` — v1.0 M3**
- Spec: `specs/turing-dossier.yaml`

**[turing-030] Identity continuity property test — Proposed — v1.0 M4**

**[turing-031] Narrative consistency property test — Proposed — v1.0 M4**

**[turing-032] Decision provenance property test — Proposed — v1.0 M4**

**[turing-033] Mood plausibility property test — Proposed — v1.0 M4**

**[turing-034] Memory floor preservation property test — Proposed — v1.0 M4**

**[turing-035] 30-day staging run — Proposed — v1.0 M4 (acceptance gate)**
- All five property tests asserted; failure is hard fail
- Depends on `[engine-032]`

**[turing-040] Reading-order docs aligned with template — Proposed — v1.0 M5**

**[turing-041] Strip Stronghold-only content — Proposed; `gap-impl` — v1.0 M5**
- `ARCHITECTURE.md` (60KB) review and excise multi-tenant + K8s + enterprise content
- Coordinated with `[sh-021]`

**[turing-042] Migrate K8S-* records out — Accepted; `gap-impl` — v1.0 M5**
- Side of `[engine-020]`
- Coordinated with `[sh-020]`

**[turing-043] Bootstrap into autonoetic Copier template — Proposed; `gap-impl` — v1.0 M5**
- Blocked-by: `[engine-011]`

### Documentation hygiene (Turing)

**[turing-090] Front-matter on Turing specs — Proposed; `gap-spec` — v1.0 (warn-only)**
- 22 top-level + ~70 nested epic stories

**[turing-091] Memory specs `Substrate:` recast — Accepted; `gap-impl` — v1.0 M3**
- `turing-dossier.yaml` → `substrate: [engine#ADR-016]`
- `turing-memory-consolidator.yaml` → `substrate: [engine#ADR-016, engine#ADR-017]`
- `turing-notebook-live-vault.yaml` → `substrate: [engine#ADR-011]`
- `turing-obsidian-store.yaml` → `substrate: [engine#ADR-014]`
- `epic-12-memory-v2` (stub) → promote to engine ADR or close as duplicate

**[turing-092] Project Turing research consolidation — Proposed — v1.0**
- Decide: research-track-then-promote, or canonical AgentTuring source

**[turing-095] Adopt contract markers — Proposed — v1.0 M5**
- `pytest.mark.contract` / `pytest.mark.scope` per `[engine#ADR-032]`

### v1.1 (Turing)

**[turing-050] Lineage queries — Proposed — v1.1**

**[turing-051] Dream loop — Proposed — v1.1**

**[turing-052] Phantom execution — Proposed — v1.1**

**[turing-053] Adversarial hardening of the self-model — Proposed — v1.1**
- Uses `[engine-084]` chaos primitives if shipped

### v1.2 (Turing)

**[turing-060] `epic-13-hyperagents-meta-level` formalised — Proposed — v1.2**

**[turing-061] RASO inner cycle wired to self-talk — Proposed — v1.2**

**[turing-062] Tournament evolution scaffolding (internal-only) — Proposed — v1.2**

### v1.3 (Turing)

**[turing-070] Meta-agent that modifies activation graph — Proposed — v1.3**

**[turing-071] Parameter-sensitivity learner — Proposed — v1.3**

**[turing-072] Self-modification gate — Proposed — v1.3**

### v2.0 (Turing)

**[turing-080] Self-model export / import — Proposed — v2.0**

**[turing-081] Long-horizon recall with confidence calibration — Proposed — v2.0**

**[turing-082] Synthesised mood + drives from imported episodic record — Proposed — v2.0**

**[turing-083] Confidence-calibrated routing — Proposed — v2.0**

### Discovered gaps (Turing)

**[turing-100] HEXACO drift bound calibration — Proposed — v1.0 M1**
- The 0.05 number is a guess; first weekly re-tests calibrate

**[turing-101] Narrative recall idiom decision — Proposed — v1.0 M4**
- LLMs reconstruct, they don't replay

**[turing-102] Sleep / off-hours behavior — Proposed — v1.x**
- Decision pending v1.0 staging observation

### Items deferred / abandoned (Turing)

**[turing-200] Production deployment — Abandoned**
- Turing is experimental; production is `stronghold`'s job

**[turing-201] Multi-tenant Turing — Abandoned**
- Structurally incompatible with autonoetic posture

---

## `stronghold` items

### v1.0 — compliance-first

Full detail in [`stronghold/ROADMAP-v1.0.md`](https://github.com/agent-stronghold/stronghold/blob/main/ROADMAP-v1.0.md).

**[sh-001] Multi-tenant catalog wrapper — Proposed; `gap-impl` — v1.0 W1**
- Wraps engine simple form per `[engine#ADR-035]`
- Tenant-scoped namespacing, audit on every mutation

**[sh-002] Tenant-scoped namespacing for agents/skills/tools/recipes/MCP — Proposed — v1.0 W1**

**[sh-003] Cross-tenant catalog import (with consent) — Proposed — v1.0 W1**
- OAuth-style consent; revocable

**[sh-010] OPA / Rego policy adapter — Proposed; `gap-impl` — v1.0 W2**
- Hot-reload, < 1ms p99 at 1000 RPS

**[sh-011] Cedar policy adapter — Proposed; `gap-impl` — v1.0 W2**

**[sh-012] Sentinel policy bridge — Proposed — v1.0 W2**
- Existing path stays available

**[sh-020] Receive K8S-* records (renumbered, with substrate refs) — Accepted; `gap-impl` — v1.0 W3**
- 31 records arrive from AgentTuring per `[engine-020]`
- Catalog ones gain `substrate: [engine#ADR-006]` / `[engine#ADR-009]`

**[sh-021] Absorb stronghold-only content from AgentTuring strip — Proposed — v1.0 W3**
- Coordinate with `[turing-041]`

**[sh-030] COMPLIANCE.md OWASP Agentic Top 10 — Proposed; `gap-impl` — v1.0 W4**
- Module + test citations per control; gaps honest

**[sh-031] COMPLIANCE.md NIST AI RMF stub — Proposed — v1.0 W4**
- Govern / Map / Measure / Manage

**[sh-032] COMPLIANCE.md EU AI Act stub — Proposed — v1.0 W4**
- Articles 9–15, 17, 26

**[sh-040] Two-tenant red-team CI — Proposed; `gap-impl` — v1.0 W5**
- Property tests for tenant-isolation invariants
- Hypothesis-driven cross-tenant probe generator
- Timing-attack tolerance (±5ms)

**[sh-050] On-prem (OKD) + cloud (AKS) parity — Proposed; `gap-impl` — v1.0 W6**
- Same Helm + image set
- Acceptance suite runs on both in CI

**[sh-060] Append-only audit chain — Proposed; `gap-impl` — v1.0 W7**
- Hash-chained signing
- Tamper-detection test
- Indefinite retention (vs metrics 30d, traces 10% sampled)

**[sh-070] v1.0 acceptance suite green — Proposed — v1.0 W8**

**[sh-080] Bootstrap into multi-tenant Copier template — Proposed; `gap-impl` — v1.0 W8**
- Blocked-by: `[engine-012]`

### Documentation hygiene (Stronghold)

**[sh-090] Front-matter on Stronghold specs — Proposed; `gap-spec` — v1.0 (warn-only)**

**[sh-095] Adopt contract markers — Proposed — v1.0 M5**
- `pytest.mark.contract` / `pytest.mark.scope` per `[engine#ADR-032]`

### v1.1 (Stronghold)

**[sh-100] Trust-tier auto-promotion gates — Proposed — v1.1**
- Currently manual `update_trust_tier`

**[sh-101] Forge iteration loop (stronghold side) — Proposed — v1.1**
- Wires `[engine-051]` into Forge agent

**[sh-102] Tournament evolution wired to internal-only routing — Proposed — v1.1**
- Production traffic in v2.0 / `[sh-300]`

### v1.2 (Stronghold)

**[sh-200] Forge test→iterate loop — Proposed — v1.2**

**[sh-201] Memory decay function in learnings — Proposed — v1.2**
- Engine substrate likely (`[engine-060]` if surfaced)

### v1.3 (Stronghold)

**[sh-300] Agent marketplace (cross-tenant catalog discovery) — Proposed — v1.3**

**[sh-301] Multi-region failover — Proposed — v1.3**

### v2.0 (Stronghold)

**[sh-400] SOC 2 Type II audit — Proposed — v2.0**

**[sh-401] ISO 27001 readiness — Proposed — v2.0**

**[sh-402] Sectoral regulators (HIPAA, FedRAMP) — Proposed — v2.0**
- Per customer demand

### Discovered gaps (Stronghold)

**[sh-500] Policy evaluation latency under load — Proposed — v1.0 W2**
- OPA at 1000 RPS p99 < 1ms is achievable but tight
- If benchmark fails, fallback is in-process Sentinel with OPA as tier-2

**[sh-501] K8S-* migration churn — Proposed — v1.0 W3**
- 31 ADRs to relocate, renumber, front-matter
- Bulk migration script is the path

**[sh-502] Cross-tenant catalog consent flow design — Proposed — v1.0 W1**
- No prior art exactly fits

**[sh-503] OWASP Agentic Top 10 evidence completeness — Proposed — v1.0 W4**
- Standard is recent; honest gap reporting > overclaim

### Items deferred / abandoned (Stronghold)

*(empty at present)*

---

## Maintenance

- This file is **identical across all four repos**. Any edit lands in all four.
- IDs are stable. Items never get renumbered.
- When an item is shipped, mark `Implemented` and link the PR.
- When an item is no longer relevant, mark `Abandoned` with a one-line reason. Don't delete.
- Once `engine-001` (registry CI) ships, this BACKLOG is regenerated from front-matter; hand-edits then fail CI.
- Per-product `ROADMAP-v1.0.md` files contain v1.0 acceptance test detail (workstreams, property-test contracts) that doesn't duplicate here. Conflicts on v1.0 acceptance detail resolve in favor of those files; conflicts on item ID/owner/status resolve in favor of this BACKLOG.
