# Backlog (Four-Repo Canonical) — Project_mAIstro PROPOSAL COPY

This is a proposal copy of the canonical BACKLOG for `Project_mAIstro`. To apply, copy this file to `Project_mAIstro/BACKLOG.md` (replacing whatever is there). See `README.md` in this directory for context.

The content below is byte-identical (modulo this header) to the same file at the root of `maistro-engine`, `AgentTuring`, and `stronghold`.

---

# Backlog (Four-Repo Canonical)

**Identical copies live in every repo of the four-repo system.** Companion to [`ROADMAP.md`](ROADMAP.md). Items are tagged by owning repo:

- `engine-NNN` — `maistro-engine`
- `maistro-NNN` — `Project_mAIstro`
- `turing-NNN` — `AgentTuring`
- `sh-NNN` — `stronghold`

Maintained per [`engine#ADR-030`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/adr/ADR-030-four-repo-governance.md). Status follows [`engine#ADR-031`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/adr/ADR-031-front-matter-and-registry.md).

## Status legend

| Marker | Meaning |
|---|---|
| Proposed | Open for discussion |
| Accepted | Decision binding |
| Implemented | Decision shipped |
| Superseded | Replaced by a successor |
| Blocked | A `blocked-by:` dependency is unmet |
| Abandoned | Decision deliberately not taken |

## Gap legend

| Marker | Meaning |
|---|---|
| `gap-spec` | No spec or ADR captures this decision yet |
| `gap-test` | Spec/ADR exists; no test covers it |
| `gap-impl` | Spec/ADR + test exist; production code does not match |

---

## `maistro-engine` items

See canonical at [`maistro-engine/BACKLOG.md`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/BACKLOG.md). Summary:

- M1 Foundation: `[engine-001]` Registry CI, `[engine-002]` INVENTORY auto-regen, `[engine-003]` front-matter rollout, `[engine-004]` CONTRIBUTING.md
- M2 Templates: `[engine-010..013]` three Copier templates + two-stream release
- M3 Drift closure: `[engine-020..022]` K8S/memory/catalog dedup coordinators
- M4 Substrate code parity: `[engine-030..032]` Ontology + Observability + Reliability
- M5 Contracts: `[engine-040..043]` Pydantic + Hypothesis + Pact + mutmut
- v1.1–2.0: `[engine-050..073]` portability proof, Forge primitive, Memory v2, Ontology Kinetic + Dynamic, etc.
- Discovered gaps: `[engine-080..085]` Pact tooling, mutation exclusions, backup, DR, chaos, trace export

---

## `Project_mAIstro` items

### v1.0 — multi-user with hard isolation + setup wizard

**[maistro-001] Setup wizard — Proposed — v1.0**
- `S-139`. v1.0 critical path. Acceptance: < 30 min for new household

**[maistro-002] Per-user memory isolation — Proposed — v1.0**
- Property test: cross-user retrieval is structurally impossible

**[maistro-003] Multi-user auth (Keycloak / JWT) — Proposed — v1.0**
- Specs: `S-018`, `S-019`, `S-024`

**[maistro-004] Native install + Podman + systemd — Proposed — v1.0**
- Specs: `S-147`, `S-148`

**[maistro-005] Tailscale-native networking — Proposed — v1.0**
- Spec: `S-153`

**[maistro-006] Setup-wizard property test — Proposed — v1.0**

**[maistro-007] Per-user isolation property test — Proposed — v1.0**

### Documentation hygiene

**[maistro-090] Front-matter on mAIstro specs — Proposed; `gap-spec` — v1.0 (warn-only)**
- 91 specs; `S-NNN` → `SPEC-NNN` on touch

**[maistro-091] Memory specs `Substrate:` recast — Proposed; `gap-impl` — v1.0 M3**
- `S-008` → `[engine#ADR-018]` · `S-009` → `[engine#ADR-016]` · `S-032` → `[engine#ADR-016]` · `S-033` → `[engine#ADR-017]`

**[maistro-092] Catalog specs `Substrate:` recast — Proposed; `gap-impl` — v1.0 M3**
- `S-005` → `[engine#ADR-009]` · `S-138` → `[engine#ADR-005/006/009]`

**[maistro-095] Copier bootstrap — Proposed; `gap-impl` — v1.0 M2**
- Round-trip into `engine/templates/single-tenant-multi-user/`

### v1.1–v2.0 (mAIstro)

**[maistro-100] Voice + email + Alexa channels — Proposed — v1.1**
- Specs: `S-041`, `S-042`, `S-043`, `S-103`, `S-104`

**[maistro-101] Hardware-signing integration — Proposed — v1.1**
- Spec: `S-150`. Substrate: `[engine#ADR-022]`

**[maistro-102] Internal trust root — Proposed — v1.1**
- Spec: `S-155`. Substrate: `[engine#ADR-026]`

**[maistro-103] DID/VC agent identity — Proposed — v1.1**
- Spec: `S-152`. Substrate: `[engine#ADR-024]`

**[maistro-200] Hyperagent graph runtime — Proposed — v1.2**
- Spec: `S-145`

**[maistro-201] Node-graph designer (low-code) — Proposed — v1.2**
- Spec: `S-159`. Closest analogue to Palantir AIP "Workshop"

**[maistro-202] Human-as-node HITL primitive — Proposed — v1.2**
- Spec: `S-158`

**[maistro-300] Cross-self portability for households — Proposed — v2.0**
- If `[turing-080]` substrates cleanly

---

## `AgentTuring` items

See canonical at [`AgentTuring/BACKLOG.md`](https://github.com/BlakeMatthews-dev/AgentTuring/blob/main/BACKLOG.md). Summary:

- v1.0 M1 self-model substrate: `[turing-001..004]`
- v1.0 M2 episodic + provenance: `[turing-010..013]`
- v1.0 M3 self-talk loop: `[turing-020..023]`
- v1.0 M4 property tests: `[turing-030..035]`
- v1.0 M5 polish + bootstrap: `[turing-040..043]`
- Documentation hygiene: `[turing-090..095]`
- v1.1: `[turing-050..053]` lineage / dream / phantom / adversarial hardening
- v1.2: `[turing-060..062]` RASO inner loop
- v1.3: `[turing-070..072]` meta-agent + parameter learner + self-modification gate
- v2.0: `[turing-080..083]` self-model export, long-horizon recall, etc.
- Discovered gaps: `[turing-100..102]`
- Abandoned: `[turing-200]` production deployment, `[turing-201]` multi-tenant Turing

---

## `stronghold` items

See canonical at [`stronghold/BACKLOG.md`](https://github.com/agent-stronghold/stronghold/blob/main/BACKLOG.md). Summary:

- v1.0 W1 multi-tenant catalog: `[sh-001..003]`
- v1.0 W2 policy-as-code: `[sh-010..012]`
- v1.0 W3 K8S-* migration in: `[sh-020..021]`
- v1.0 W4 COMPLIANCE.md: `[sh-030..032]`
- v1.0 W5 two-tenant red-team CI: `[sh-040]`
- v1.0 W6 on-prem + cloud parity: `[sh-050]`
- v1.0 W7 audit chain: `[sh-060]`
- v1.0 W8 acceptance + bootstrap: `[sh-070..080]`
- Documentation hygiene: `[sh-090..095]`
- v1.1: `[sh-100..102]`
- v1.2: `[sh-200..201]`
- v1.3: `[sh-300..301]`
- v2.0: `[sh-400..402]`
- Discovered gaps: `[sh-500..503]`

---

## Maintenance

- This file is **identical across all four repos**. Any edit lands in all four.
- IDs are stable. Items never get renumbered.
- When an item is shipped, mark `Implemented` and link the PR.
- When an item is no longer relevant, mark `Abandoned` with a one-line reason. Don't delete.
- Once `engine-001` (registry CI) ships, this BACKLOG is regenerated from front-matter.

---

## Note on this proposal copy

This is a proposal version. Once `Project_mAIstro` is added to the GitHub MCP allowlist (or the user applies these files manually), the canonical version that lands at `Project_mAIstro/BACKLOG.md` should mirror the engine/AgentTuring/stronghold copies verbatim. The summary sections for engine/Turing/stronghold above can either be expanded to full content (matching the other repos) or kept as summary pointers — the user's preference; both are valid four-repo-canonical patterns.
