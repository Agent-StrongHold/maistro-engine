# maistro-engine — BACKLOG

The queue of substrate work the three products need.
Maintained per [`ADR-030`](docs/adr/ADR-030-four-repo-governance.md). Items here are engine-level. Product-only work belongs in the product BACKLOGs.

## How this BACKLOG is structured

Each item is `[id] <title> — <status> — <milestone>` followed by 1–5 bullets of detail.

- **id** — stable slug (`engine-NNN`) used in PR titles and front-matter `related:` fields. Renumbering is on-touch per [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md).
- **status** — `Proposed | Accepted | Implemented | Superseded | Blocked | Abandoned` per [`ADR-031`](docs/adr/ADR-031-front-matter-and-registry.md).
- **milestone** — `M1`…`M5` for v1.0; `v1.1`…`v2.0` beyond.

## Status legend (per ADR-031)

| Marker | Meaning |
|---|---|
| Proposed | Open for discussion; not yet binding |
| Accepted | Decision binding; implementation may follow |
| Implemented | Decision shipped; production code matches |
| Blocked | A `blocked-by:` dependency is unmet |

## Gap legend (per INVENTORY)

| Marker | Meaning |
|---|---|
| `gap-spec` | No spec or ADR captures this decision yet |
| `gap-test` | Spec/ADR exists; no test (or test stub) covers it |
| `gap-impl` | Spec/ADR + test exist; production code does not match |

---

## v1.0 critical path

### M1 — Conventions enforced

**[engine-001] Registry CI tooling — Accepted; `gap-impl` — M1**
- Front-matter YAML validator (Pydantic schema from ADR-031)
- Cross-repo link checker via GitHub MCP / API: every `<repo>#<id>` resolves
- Registry generator: emits `registry/registry.json` and `registry.md`
- DAG validator on `supersedes:` and `blocks:` (no cycles)
- GitHub Action wiring: warn-only mode, hard-fail flip after day 30
- Tests: contract `boundary | unit` for the validator; `behavioral | property` for the DAG check

**[engine-002] INVENTORY auto-regeneration — Proposed — M1**
- Hand-edits to `docs/INVENTORY-ADRS-SPECS.md` fail CI once tooling lands
- The file becomes the registry's human-readable rendering
- Blocked-by: `engine-001`

**[engine-003] Front-matter migration of existing engine ADRs — Accepted; gradual — M1**
- ADRs 000–029 (30 files) lack front-matter
- Per ADR-031: renumber-on-touch; not a bulk migration
- Each PR that edits an existing ADR adds front-matter in the same commit
- ADR-000 template regenerated to match the new schema (one-shot, separate PR)

**[engine-004] CONTRIBUTING.md and convention docs — Proposed — M1**
- Author-facing summary of ADR-031 (front-matter), ADR-032 (contracts), ADR-001 (branching)
- One-page "how to add an ADR" + "how to add a spec" + "how to cite substrate"
- Linked from README; linked from product repos' READMEs

### M2 — Templates bootstrapped

**[engine-010] Copier template — single-tenant-multi-user — Accepted; `gap-impl` — M2**
- Knobs: `users_max`, `auth_backend (keycloak | local)`, `channels (web | voice | email)`, `host_target (podman | docker | systemd)`
- Generates `pyproject.toml` pinning engine version, `docker-compose.yml`, `src/` overlay, `docs/adr/` seed with substrate refs filled, test scaffold wired to `pytest.mark.contract` / `pytest.mark.scope`
- Round-trip: `copier copy` against fresh dir matches `Project_mAIstro` current shape, modulo product-specific files

**[engine-011] Copier template — autonoetic — Accepted; `gap-impl` — M2**
- Knobs: `awareness_loop_hz`, `self_model (hexaco | minimal)`, `memory_consolidator (on | off)`, `dossier_store (obsidian | fs)`
- Round-trip against `AgentTuring`

**[engine-012] Copier template — multi-tenant — Accepted; `gap-impl` — M2**
- Knobs: `tenants_max`, `policy_engine (opa | cedar | sentinel)`, `deploy_target (k8s | on-prem | hybrid)`, `compliance_pack (owasp | nist | euaiact | all)`
- Round-trip against `stronghold`

**[engine-013] Two-stream release pipeline — Proposed — M2**
- `pkg/v*` tags publish the Python package
- `template/v*` tags publish Copier template snapshots
- Each engine ADR that affects templates must bump the right one
- Blocked-by: `engine-010`, `engine-011`, `engine-012`

### M3 — Drift items closed

**[engine-020] K8S-* ADR migration AT → stronghold — Accepted; `gap-impl` — M3**
- 31 records currently in `AgentTuring/docs/adr/`
- Move all to `stronghold/docs/adr/`, renumber to unified scheme on touch
- Catalog-related ones (K8S-021, K8S-022, K8S-023, K8S-027) gain `substrate:` refs to engine ADR-006/009 per ADR-035
- A2A-related ones (K8S-028, K8S-029) may stay engine-side if the protocol is engine-canonical
- See INVENTORY §2 for the table

**[engine-021] Memory spec dedup across products — Accepted; `gap-impl` — M3**
- AgentTuring: `turing-dossier`, `turing-memory-consolidator`, `turing-notebook-live-vault`, `turing-obsidian-store`, `epic-12-memory-v2` recast
- Project_mAIstro: `S-008`, `S-009`, `S-032`, `S-033` recast
- Each becomes `Substrate: [maistro-engine#ADR-NNN]` plus product-specific tenancy/UX/adapter content
- Specs without `substrate:` after rollout fail CI

**[engine-022] Catalog spec dedup across products — Accepted; `gap-impl` — M3**
- Project_mAIstro: `S-005`, `S-138` recast against engine ADR-006/009
- AgentTuring catalog references audit—expected to consume engine simple form, no spec needed

### M4 — Substrate code parity

**[engine-030] Ontology Semantic facet — Accepted; `gap-impl` — M4**
- Implement `OntologyEntity`, `Ontology` protocol per [`ADR-036`](docs/adr/ADR-036-ontology-semantic-object-layer.md)
- Pydantic + SQLAlchemy persistence
- In-process registry; products register their domain entities at boot
- Memory record gains optional `entity_id: UUID | None` field
- Tests: boundary `Pydantic`; behavioral `register idempotency`, `query consistency`

**[engine-031] Observability spans + metrics + events — Accepted; `gap-impl` — M4**
- Required spans on the 12 engine entry points listed in [`ADR-037`](docs/adr/ADR-037-observability-taxonomy.md)
- Six required metrics emitted with the documented label sets
- Five required event topics on the engine event bus
- Sampling defaults configurable per service-key
- Tests: contract on metric labels and event topic shape

**[engine-032] Reliability primitives — Accepted; `gap-impl` — M4**
- `retry()` decorator with exponential backoff (`2s, 4s, 8s, 16s`, max 4) for idempotent IO; refuses non-idempotent without `idempotency_key`
- `CircuitBreaker` per dependency: `closed → open (5/60s) → half-open (30s) → closed`
- `Fallback[T]` type with `cached | default | alternate-agent` variants
- `/health/{live,ready,startup}` blueprint generators
- Tests: Hypothesis property test on state machine; unit on retry timing

### M5 — Contracts as the bar

**[engine-040] Pydantic boundary contracts on all public types — Proposed — M5**
- Audit `src/maistro/types/` for non-Pydantic public types; convert
- Generate JSON Schemas from Pydantic for stable wire types
- 95% mutation kill rate at v1.0

**[engine-041] Hypothesis property tests on accepted behavioral ADRs — Proposed — M5**
- Adopt stronghold's `Spec` type pattern in the engine
- Every accepted ADR with behavioural AC gains a property test
- 80% mutation kill rate at v1.0

**[engine-042] Pact-style contracts on A2A + MCP edges — Proposed — M5**
- Choose tooling (`pact-python` vs hand-rolled) — separate ADR
- Consumer-driven: each consumer publishes; provider runs against all consumers
- 75% mutation kill rate at v1.0

**[engine-043] Mutation-testing CI wiring — Proposed — M5**
- Adopt stronghold's `mutmut` config
- Nightly + on-`main`-merge schedule (not every PR)
- Per-tier kill-rate thresholds enforced

---

## v1.1 (3–6 months)

**[engine-050] Cross-product agent portability proof — Proposed — v1.1**
- Serialise an agent from `Project_mAIstro` simple catalog
- Import into `stronghold` tenant catalog
- Agent runs without code changes; only catalog wrapper differs
- Demonstrates the two-tier catalog split (ADR-035) works in practice

**[engine-051] Forge iteration loop primitive — Proposed — v1.1**
- Generalise stronghold's planned Forge test→iterate loop into an engine primitive
- Available to mAIstro and AgentTuring if they want

**[engine-052] Compliance gap audit on accepted ADRs — Proposed — v1.1**
- For each accepted ADR, verify code + tests match
- Outputs an engine-side audit doc; feeds stronghold COMPLIANCE.md control claims

## v1.2 (6–9 months)

**[engine-060] Memory v2 (if surfaced) — Proposed — v1.2**
- A product spec must propose the engine ADR; engine does not anticipate memory-v2 unilaterally

**[engine-061] DSPy-style task signatures evaluation — Proposed — v1.2**
- AgentTuring's `epic-07-dspy-task-signatures` is the driver
- Engine evaluates whether to adopt as a substrate primitive

**[engine-062] Mid-session model switching primitive — Proposed — v1.2**
- AgentTuring's `epic-10-midsession-model-switching` is the driver
- Generalise if it cleanly substrates

## v2.0 (12 months) — inventory-clear

**[engine-070] Ontology Kinetic facet — Proposed — v2.0**
- Actions an entity exposes, with pre/post-condition contracts

**[engine-071] Ontology Dynamic facet — Proposed — v2.0**
- State transitions, version history, derivation lineage
- Requires schema migration policy ADR

**[engine-072] Cross-tenant ontology sharing primitive — Proposed — v2.0**
- Stronghold-driven; engine support

**[engine-073] Tournament-based agent evolution wired to production routing — Proposed — v2.0**
- Substrate piece for stronghold v2.0 + AgentTuring v2.0

## Discovered gaps (not yet milestoned)

**[engine-080] Pact tooling choice — Proposed**
- ADR-032 is silent on `pact-python` vs hand-rolled; one separate ADR resolves it

**[engine-081] Mutation-testing exclusion list per repo — Proposed**
- Equivalent mutants and unavoidable survivors need a curated list per ADR-032

**[engine-082] Backup / export semantics for memory — Proposed**
- Out-of-scope of ADR-034; needs its own ADR before any product spec asks for it

**[engine-083] Disaster-recovery / backup-restore primitives — Proposed**
- Out-of-scope of ADR-038; stronghold v1.x will need it

**[engine-084] Chaos-engineering harness — Proposed**
- Out-of-scope of ADR-038; would feed stronghold red-team CI (W5 in stronghold ROADMAP-v1.0)

**[engine-085] Trace export to long-term storage — Proposed**
- Out-of-scope of ADR-037; relevant for compliance evidence retention

## Items deferred / abandoned

*(empty at present)*

---

## Maintenance

- New items get appended; status changes happen in-place.
- IDs are stable. Items never get renumbered.
- When an item is shipped, mark `Implemented` and link the PR.
- When an item is no longer relevant, mark `Abandoned` with a one-line reason. Don't delete.
- Once registry CI lands (`engine-001`), this BACKLOG is regenerated from front-matter; hand-edits during the warn window are fine.
