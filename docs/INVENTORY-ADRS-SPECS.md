# ADR & Spec Inventory — Cross-Repo

Generated 2026-05-07 (augmented). Branch: `claude/review-compare-frameworks-Az3XA`.

This document inventories all Architecture Decision Records (ADRs) and
specification documents across the four sibling repositories
(`maistro-engine`, `Project_mAIstro`, `AgentTuring`, `stronghold`) and maps
them to the layers of the agentic-AI reference architecture
(User/Client → Orchestration → Agents → Tools → Memory → Monitoring →
Reliability → Governance → Foundation).

Until registry-CI tooling lands ([`ADR-031`](adr/ADR-031-front-matter-and-registry.md)
phase 0g), this file is hand-maintained. Once tooling lands, it is
regenerated from artifact front-matter and hand-edits will fail CI.

## Status legend (per ADR-031)

| Marker | Meaning |
|---|---|
| **Proposed** | Open for discussion; not yet binding |
| **Accepted** | Decision binding; implementation may follow |
| **Implemented** | Decision shipped; production code matches |
| **Superseded** | Replaced by a successor ADR (named in `supersedes:` of successor) |
| **Blocked** | A `blocked-by:` dependency is unmet |
| **Abandoned** | Decision deliberately not taken (kept for traceability) |

## Gap legend (used in tables below)

| Marker | Meaning |
|---|---|
| `gap-spec` | No spec or ADR captures this decision yet |
| `gap-test` | Spec/ADR exists; no test (or test stub) covers it |
| `gap-impl` | Spec/ADR + test exist; production code does not match |
| `dup` | Duplicate of another artifact; consolidation owed |

`AgentTuring` and `agent-stronghold/stronghold` are sibling forks with
near-identical trees at the time of this snapshot — most ADR/spec blobs
share SHAs across the two repos. Per [`ADR-030`](adr/ADR-030-four-repo-governance.md),
they diverge through Copier-template-per-product going forward; the
blob-identical state is migration debt, not a target.

## Counts at a glance

| Repo | ADRs | Top-level specs | Nested specs | Notes |
|---|---:|---:|---:|---|
| `maistro-engine` | **29** (ADR-000…029) + **9** new (ADR-030…038) | 5 (`SPEC-175` … `SPEC-179` under `docs/specs/`) | 0 | Engine-level decisions and meta-ADR ladder; `docs/specs/` for numbered product-style specs |
| `Project_mAIstro` | 0 | 2 (`SPEC-TEMPLATE`, `TIMELINE`) | 91 (`specs/<area>/S-NNN-*.md`) | `S-NNN` numbered backlog; renumber-on-touch → `SPEC-NNN` |
| `AgentTuring` | 31 (ADR-K8S-001…031) | 22 (`specs/*.yaml`) | ~70 (`docs/specs/epic-01–14/`) | K8S-* ADRs migrate to `stronghold` per ADR-030 |
| `stronghold` | 31 (mirror of AgentTuring) + (incoming K8S migration) | 22 (mirror) | ~70 (mirror) | Sibling fork; expect divergence post-Copier bootstrap |

Total visible ADR/spec artifacts across the four repos: **~280** (with
significant duplication between AgentTuring and stronghold expected to
resolve via Copier-driven divergence).

## What changed since the prior snapshot (2026-05-07 morning)

- **9 new engine ADRs** (030–038) form the meta-ADR ladder formalising the four-repo system. See PR #4.
- **K8S-* ADRs** now have a documented destination (stronghold) and a renumber-on-touch policy.
- **Memory drift** has a canonical owner ([`ADR-034`](adr/ADR-034-memory-canonical-ownership.md)).
- **Catalog drift** has a two-tier ownership split ([`ADR-035`](adr/ADR-035-catalog-ownership-split.md)).
- **Genuine architectural gaps** (Ontology, Observability taxonomy, Reliability taxonomy) are now Accepted ADRs (036–038).
- **Front-matter conventions** are defined ([`ADR-031`](adr/ADR-031-front-matter-and-registry.md)) and rolling out warn-only for 30 days.

---

## 1. `BlakeMatthews-dev/maistro-engine`

### ADRs (`docs/adr/`, 30 files — 029 + 9 new in PR #4)

Engine-internal architectural decisions. Numbering is sequential (`ADR-NNN`) and scoped to the engine.

| ID | Title | Layer | Status | Notes |
|---|---|---|---|---|
| ADR-000 | template | — | Superseded (by ADR-031) | Regenerated to new front-matter as follow-up |
| ADR-001 | branching-strategy | Foundation | Accepted | |
| ADR-002 | porting-workflow | Foundation | Accepted | |
| ADR-003 | agent-runtime-gap-resolution | Orchestration | Accepted | |
| ADR-004 | agent-spec | Agents | Accepted | |
| ADR-005 | schemas | Orchestration | Accepted | |
| ADR-006 | recipe-registry | Orchestration | Accepted | Canonical catalog substrate per ADR-035 |
| ADR-007 | variant-selector | Orchestration | Accepted | Router scoring; substrate for ADR-038 SLO throttling |
| ADR-008 | structured-output-parser | Agents | Accepted | |
| ADR-009 | spawner | Orchestration | Accepted | Canonical catalog substrate per ADR-035 |
| ADR-010 | lane-scheduling | Orchestration | Accepted | |
| ADR-011 | memory-engine | Memory | Accepted | Canonical memory substrate per ADR-034 |
| ADR-012 | alembic-migration | Foundation | Accepted | |
| ADR-013 | memory-types | Memory | Accepted | Canonical per ADR-034 |
| ADR-014 | memory-protocols | Memory | Accepted | Canonical per ADR-034 |
| ADR-015 | learning-store | Memory | Accepted | Canonical per ADR-034 |
| ADR-016 | episodic-store | Memory | Accepted | Canonical per ADR-034 |
| ADR-017 | outcome-store | Memory | Accepted | Canonical per ADR-034 |
| ADR-018 | task-record-persistence | Foundation | Accepted | |
| ADR-019 | canonical-source-split | Foundation | Accepted | Extended by ADR-030 |
| ADR-020 | setup-wizard | Foundation | Accepted | |
| ADR-021 | conductor-seed | Orchestration | Accepted | |
| ADR-022 | hardware-signing | Governance | Accepted | Cryptographic identity substrate |
| ADR-023 | agent-crypto-ops | Governance | Accepted | Cryptographic identity substrate |
| ADR-024 | agent-identity-did-vc | Governance | Accepted | DID/VC; substrate for AGT-style identity |
| ADR-025 | electrum-server | Foundation | Accepted | |
| ADR-026 | internal-trust-root | Governance | Accepted | |
| ADR-027 | lightning-federation | Foundation | Accepted | |
| ADR-028 | privilege-separation | Governance | Accepted | |
| ADR-029 | networking-substrate | Foundation | Accepted | |
| **ADR-030** | **four-repo-governance** | **Foundation** | **Accepted** | **NEW — PR #4** |
| **ADR-031** | **front-matter-and-registry** | **Foundation** | **Accepted** | **NEW — PR #4** |
| **ADR-032** | **contracts-as-acceptance-criteria** | **Foundation** | **Accepted** | **NEW — PR #4** |
| **ADR-033** | **templates-and-copier-workflow** | **Foundation** | **Accepted** | **NEW — PR #4** |
| **ADR-034** | **memory-canonical-ownership** | **Memory** | **Accepted** | **NEW — PR #4** |
| **ADR-035** | **catalog-ownership-split** | **Tools** | **Accepted** | **NEW — PR #4** |
| **ADR-036** | **ontology-semantic-object-layer** | **Foundation** | **Accepted** | **NEW — PR #4; closes ontology gap-spec** |
| **ADR-037** | **observability-taxonomy** | **Observability** | **Accepted** | **NEW — PR #4; closes observability gap-spec** |
| **ADR-038** | **reliability-taxonomy** | **Reliability** | **Accepted** | **NEW — PR #4; closes reliability gap-spec** |

### Specs

No `specs/` tree exists in this repo (and won't — specs live in product repos per ADR-019/030). Closest analogues remain:

- `docs/archive/CONSOLIDATION-PLAN.md` (historical — see archived banner)
- `docs/anthropic-agent-framework.md`
- `docs/claude-quality-enforcement.md`
- `docs/quality-standards.md`
- `docs/audit/AUDIT-2026-02-20.md`, `docs/audit/TESTING-AUDIT-2026-02-20.md` (historical — see `docs/audit/HN-LAUNCH-AUDIT.md` for current state)
- `docs/analysis/` (cross-framework comparisons)
- `docs/specs/SPEC-176-hive-conductor-package.md` — Hive Conductor monorepo package (`packages/hive-conductor/`)
- `docs/specs/SPEC-180-maistro-install-bootstrap.md` — `maistro-install` answers schema, plan JSON, `--apply`, Hive `/v1/install/plan`
- `docs/specs/SPEC-181-hive-missions-maistro-core-bridge.md` — future: Hive missions → maistro-core execution (SPEC-176 phase 2)

### Engine-level gaps after PR #4

| Gap | Status |
|---|---|
| Ontology | **Closed** by ADR-036 (Accepted; impl is gap-impl until v1.0) |
| Observability taxonomy | **Closed** by ADR-037 (Accepted; spans/metrics/events spec'd) |
| Reliability taxonomy | **Closed** by ADR-038 (Accepted; primitives spec'd) |
| Front-matter conventions | **Closed** by ADR-031 (Accepted; warn-only rollout) |
| Four-repo governance | **Closed** by ADR-030 (Accepted) |
| Memory drift across repos | **Closed** by ADR-034 (migration plan defined) |
| Catalog drift across repos | **Closed** by ADR-035 (two-tier split) |
| Templating mechanism | **Closed** by ADR-033 (Copier; bootstrap pending) |
| Acceptance-criteria format | **Closed** by ADR-032 (layered contracts; Hypothesis + Pact + Pydantic) |
| Registry CI tooling | `gap-impl` — spec'd in ADR-031, not built (Phase 0g) |
| Compliance mapping doc | n/a here — stronghold owns COMPLIANCE.md (Phase 4d) |
| Eval / regression harness | Spec'd in AgentTuring epic-01-eval-substrate; engine ADR optional |

---

## 2. `BlakeMatthews-dev/AgentTuring` (and `agent-stronghold/stronghold` mirror)

Per ADR-030: AgentTuring is the autonoetic experimental product. Its dominant constraint is **continuity of self**. The K8S-* ADR set describes enterprise multi-tenant deployment topology and migrates to `stronghold` per ADR-030; AgentTuring keeps only autonoetic-relevant ADRs.

### ADRs (`docs/adr/`, 31 files + README) — migration in flight

All currently prefixed `ADR-K8S-`. Per ADR-031 renumber-on-touch, each migrates to a destination repo and is renumbered to `ADR-NNN`.

| ID | Title | Migration target | Layer | Notes |
|---|---|---|---|---|
| K8S-001 | namespace-topology | `stronghold` | Foundation | Multi-tenant topology |
| K8S-002 | rbac-boundary | `stronghold` | Governance | |
| K8S-003 | secrets-approach | `stronghold` | Governance | |
| K8S-004 | networkpolicy-posture | `stronghold` | Governance | |
| K8S-005 | warden-topology | `stronghold` | Governance | |
| K8S-006 | runtime-okd | `stronghold` | Foundation | |
| K8S-007 | distro-compatibility-matrix | `stronghold` | Foundation | |
| K8S-008 | prod-dev-isolation | `stronghold` | Foundation | |
| K8S-009 | migration-sequence | `stronghold` | Foundation | |
| K8S-010 | storage-pluggability | `stronghold` | Foundation | |
| K8S-011 | secrets-provider-pluggability | `stronghold` | Governance | |
| K8S-012 | crc-sandbox | `stronghold` | Foundation | |
| K8S-013 | hybrid-execution-model | `stronghold` | Orchestration | |
| K8S-014 | six-tier-priority-system | `stronghold` | Orchestration | |
| K8S-015 | priority-tier-eviction-order | `stronghold` | Orchestration | |
| K8S-016 | gitops-controller | `stronghold` | Foundation | |
| K8S-017 | architecture-diagram-pipeline | `stronghold` | Foundation | |
| K8S-018 | per-user-credential-vault | `stronghold` | Governance | |
| K8S-019 | tool-policy-layer | `stronghold` | Governance | |
| K8S-020 | mcp-server-gateway-orchestrator | `stronghold` | Tools | Multi-tenant gateway |
| K8S-021 | tool-catalog | `stronghold` | Tools | Substrate: engine#ADR-006 (per ADR-035) |
| K8S-022 | skill-catalog | `stronghold` | Agents | Substrate: engine#ADR-006 (per ADR-035) |
| K8S-023 | resource-catalog | `stronghold` | Tools | Substrate: engine#ADR-006 (per ADR-035) |
| K8S-024 | mcp-transport-auth-discovery | `stronghold` | Tools | |
| K8S-025 | sandboxed-primitive-mcp-guests | `stronghold` | Tools | |
| K8S-026 | sandbox-pod-catalog | `stronghold` | Tools | |
| K8S-027 | agent-catalog | `stronghold` | Agents | Substrate: engine#ADR-009 (per ADR-035) |
| K8S-028 | stronghold-as-a2a-peer | `stronghold` (or engine if A2A protocol) | Agents | TBD |
| K8S-029 | a2a-guest-peers | engine (A2A protocol) | Agents | TBD — a2a is engine-level |
| K8S-030 | task-acceptance-policy | `stronghold` | Orchestration | |
| K8S-031 | builder-capabilities | engine (or split) | Agents | TBD |

### Top-level specs (`specs/`, 22 files) — stay in AgentTuring (autonoetic-relevant)

| Spec | Layer | Substrate (per ADR-034) |
|---|---|---|
| `TURING-CONSOLE-README.md` | UserClient | — |
| `archie-property-gen.yaml` | Agents | — |
| `complexity-triage.yaml` | Orchestration | — |
| `phase1-pipeline-wiring.yaml` | Orchestration | — |
| `phase2-verifier.yaml` | Reliability | engine#ADR-038 |
| `phase3-plan-caching.yaml` | Foundation | — |
| `phase4-agent-configs.yaml` | Agents | — |
| `prompt-caching.yaml` | Foundation | — |
| `quartermaster-spec-emission.yaml` | Orchestration | — |
| `rca-structured-output.yaml` | Agents | engine#ADR-008 |
| `spec-enriched-prompts.yaml` | Agents | — |
| `turing-blog-authoring.yaml` | Agents | — |
| `turing-chat-streaming.yaml` | UserClient | — |
| `turing-dossier.yaml` | Memory | engine#ADR-016 (per ADR-034) |
| `turing-frontend-port.yaml` | UserClient | — |
| `turing-memory-consolidator.yaml` | Memory | engine#ADR-016, engine#ADR-017 (per ADR-034) |
| `turing-notebook-live-vault.yaml` | Memory | engine#ADR-011 (per ADR-034) |
| `turing-obsidian-store.yaml` | Memory | engine#ADR-014 (per ADR-034) |
| `turing-self-talk-loop.yaml` | Agents | — (autonoetic-only) |
| `turing-skills-lab.yaml` | Agents | engine#ADR-006, engine#ADR-009 |
| `turing-synapse-crud-endpoints.yaml` | Tools | — |
| `turing-wordpress-publishing.yaml` | Tools | — |

### Nested specs (`docs/specs/`, ~70 files) — stay in AgentTuring

Epic directories (each contains a `README.md`, `tests-manifest.md`, and varying numbers of `story-NN-*.md` files; some are stubs). Substrate per ADR-034 noted where relevant.

| Epic | Layer | Substrate / Notes |
|---|---|---|
| epic-01-eval-substrate (5 stories) | Reliability | engine#ADR-038 |
| epic-02-capability-profile | Agents | |
| epic-03-agent-call-acls | Governance | |
| epic-04-substrate-tool-agent-taxonomy | Tools / Agents | engine#ADR-006, engine#ADR-009 |
| epic-05-agents-as-tools | Agents | |
| epic-06-conduit-reasoning-agent | Agents | |
| epic-07-dspy-task-signatures | Orchestration | |
| epic-08-prompt-versioning-rollback | Foundation | |
| epic-09-canary-ab-tournament | Reliability | engine#ADR-038 |
| epic-10-midsession-model-switching | Foundation | engine#ADR-038 fallback |
| epic-11-group-chat-patterns | Agents | |
| epic-12-memory-v2 (stub) | Memory | Promote to engine ADR or close as dup (per ADR-034) |
| epic-13-hyperagents-meta-level | Agents | autonoetic-only |
| epic-14-artificer-v2-rethink | Agents | |

---

## 3. `BlakeMatthews-dev/Project_mAIstro`

Per ADR-030: single-tenant secure multi-user product. Dominant constraint: **ease of self-hosting**. v1.0 = multi-user with hard per-user isolation + setup wizard (`SPEC-139`).

No ADRs (deliberate — architectural choices live in engine ADRs and are cited via `substrate:` in product specs). Specs are organised under `specs/<area>/S-NNN-*.md` with a global numbering scheme (`S-001`…`S-159`). Renumber-on-touch → `SPEC-NNN`.

### Meta

- `specs/SPEC-TEMPLATE.md`
- `specs/TIMELINE.md`

### `specs/conductor/` (19) — Orchestration

Key specs (substrate per ADR-034 and ADR-035 noted):

- S-001 heartbeat
- S-002 factory-spawner — `Substrate: engine#ADR-009`
- S-003 artifact-intent
- S-004 conversation-intent
- S-005 agent-factory — `Substrate: engine#ADR-009` (per ADR-035)
- S-006 apm
- S-007 3-phase-classifier
- S-008 session-summarization — `Substrate: engine#ADR-018` (per ADR-034)
- S-009 episodic-memory-bridge — `Substrate: engine#ADR-016` (per ADR-034)
- S-010 session-isolation
- S-011 morning-digest
- S-012 positive-pattern-learning
- S-105 uncapped-tool-loop
- S-106 user-profiles
- S-107 confidence-decay
- S-138 agent-conductor — `Substrate: engine#ADR-005, engine#ADR-006, engine#ADR-009` (per ADR-035)
- S-143 1khz-reactor
- S-145 hyperagent-graph-runtime
- S-158 human-as-node — HITL primitive; `Substrate: engine#ADR-036` (ontology entity vote target)

### `specs/channels/` (5) — UserClient

S-041 voice-agent · S-042 voice-model-group · S-043 phone-notifications · S-103 email-channel · S-104 alexa-devices

### `specs/infra/` (30) — Foundation

Key specs:
- S-018 keycloak-migration (multi-user auth)
- S-019 openwebui-jwt (multi-user)
- S-024 jwt-auth (multi-user)
- S-045 langfuse-setup — `Substrate: engine#ADR-037`
- S-101 traefik-dashboard
- S-102 pwa-dashboard
- S-139 setup-wizard — **v1.0 critical path**
- S-140 sqlite-singleton
- S-141 vault
- S-147 native-install
- S-148 podman-container
- S-153 tailscale-native

(plus S-013, S-014, S-015, S-016, S-017, S-020, S-021, S-044, S-100, S-116, S-117, S-118, S-119, S-120, S-130, S-132, S-133, S-135, S-144, S-159)

### `specs/intelligence/` (11) — Memory + Agents

- S-025 dream-loop — autonoetic? Or for mAIstro? Confirm scope
- S-026 adversarial-hardening — `Substrate: engine#ADR-038`
- S-027 tournament-arena — `Substrate: engine#ADR-038` (canary/AB)
- S-028 context-archaeology
- S-029 temporal-patterns
- S-030 phantom-execution
- S-031 mood-ring — *should this be Turing-only? Confirm per ADR-030 autonoetic boundary*
- S-032 episodic-memory — `Substrate: engine#ADR-016` (per ADR-034)
- S-033 memory-evolution — `Substrate: engine#ADR-017` (per ADR-034)
- S-114 collective-unconscious
- S-115 agent-networking

### `specs/security/` (14 + 2 meta) — Governance

`ARCHITECTURE.md`, `PHILOSOPHY.md`,
S-022 bouncer · S-023 secrets-manager · S-024 jwt-auth · S-109 secrets-migration · S-131 group-policy-hardening · S-141 vault · S-142 privilege-separation · S-149 conductor-seed · S-150 hardware-signing · S-151 agent-crypto-ops · S-152 agent-identity-did-vc · S-155 internal-trust-root · S-156 lightning-federation

Most `Substrate: engine#ADR-022..029` (cryptographic identity).

### `specs/tools/` (14) — Tools

S-034 time-capsule · S-035 skills-subsystem · S-036 message-board · S-037 clawhub · S-038 skill-forge · S-039 ultra-think · S-040 project-build-agents · S-108 user-feedback · S-110 hooks-system · S-111 clawhub-full · S-112 skill-evolution · S-113 stress-rehearsal — `Substrate: engine#ADR-038` · S-134 browser-cdp-refactor · S-154 electrum-server

---

## Cross-repo mapping to the reference architecture

| Reference layer | maistro-engine | AgentTuring / stronghold | Project_mAIstro |
|---|---|---|---|
| 1. User / Client | — | `turing-chat-streaming`, `turing-frontend-port`, `TURING-CONSOLE-README` | `specs/channels/*` (5) |
| 2. Orchestration / Control Plane | ADR-003, 005-010, 018, 021 | K8S-013–015, K8S-030; `phase1-pipeline-wiring`, `complexity-triage`, `quartermaster-spec-emission`; epic-07 | `specs/conductor/*` (19) |
| 3. Agent Layer | ADR-004, 008, 036 | K8S-022, K8S-027–029, K8S-031; `phase4-agent-configs`, `archie-*`, `rca-*`, `turing-self-talk-loop`, `turing-skills-lab`, `turing-blog-authoring`; epics 02, 05, 06, 11, 13, 14 | `specs/intelligence/*` (11) |
| 4. Tools & Integrations | — | K8S-019–026; `turing-synapse-crud-endpoints`, `turing-wordpress-publishing`; epic-04 | `specs/tools/*` (14) |
| 5. Memory & Knowledge | **ADR-011, 013–017, 034 (canonical)** | `turing-dossier`, `turing-memory-consolidator`, `turing-notebook-live-vault`, `turing-obsidian-store`; epic-12 (stub) | `specs/intelligence/{S-032,S-033}`; conductor `S-008,S-009`; tools `S-034` |
| 6. Monitoring & Observability | **ADR-037 (NEW; canonical taxonomy)** | epic-09 (canary/AB); `S-045` Langfuse | `specs/infra/{S-015,S-045,S-101,S-102}` |
| 7. Reliability & Failure | **ADR-038 (NEW; canonical taxonomy)** | `phase2-verifier`; epic-01, epic-09 | `specs/intelligence/S-026`; tools `S-113` |
| 8. Governance & Security | ADR-022–024, 026, 028 | K8S-002–005, K8S-011, K8S-018, K8S-019; epic-03; `backlog_security_spec`, `container_hardening_spec`, `vault_client_spec` | `specs/security/*` (16) |
| 9. Foundation / Infrastructure | ADR-001, 002, 012, 019, 020, 025, 027, 029, 030–033, 036 | K8S-001, K8S-006–010, K8S-012, K8S-016, K8S-017; `phase3-plan-caching`, `prompt-caching`; epic-08, epic-10 | `specs/infra/*` (30) |

Bold = canonical owner per ADR-030/031/034/035.

## Drift items — status

| Item | Was | Now (per PR #4) |
|---|---|---|
| Memory described in 3 places | Highest drift risk | **Resolved by ADR-034** — engine canonical, products `Substrate:`-cite |
| Catalog described in 3 places | High drift risk | **Resolved by ADR-035** — engine simple form + stronghold multi-tenant variant |
| K8S-* ADRs in wrong repo | 31 ADRs in AgentTuring | **Migration plan defined by ADR-030** — destination is stronghold, on-touch renumbering |
| AgentTuring ≡ stronghold | Blob-identical | **Resolved by ADR-033** — Copier-driven divergence post-bootstrap |
| Project_mAIstro has no ADRs | Flagged as inconsistent | **Acceptable per ADR-030** — product specs `substrate:`-cite engine ADRs |
| No ADR cross-references | Manual mapping | **Resolved by ADR-031** — front-matter + registry CI (warn-only rollout) |

## Methodology

- Listings produced via the GitHub MCP API against each repo's default branch HEAD (snapshot 2026-05-07).
- Epic story counts under `docs/specs/epic-*` are not exhaustively enumerated; epic-01 (5 stories) and epic-12 (stub) were sampled to characterise the structure.
- Layer mapping is judgement-based against the agentic-AI reference architecture. Edge cases attribute to the layer that owns the dominant decision.
- This file is hand-maintained until the registry CI tooling lands (Phase 0g, see todo list). Once tooling lands, regeneration is automatic and hand-edits fail CI.
