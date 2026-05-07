# Roadmap (Four-Repo Canonical) — Project_mAIstro PROPOSAL COPY

This is a proposal copy of the canonical ROADMAP for `Project_mAIstro`. To apply, copy this file to `Project_mAIstro/ROADMAP.md` (replacing whatever is there). See `README.md` in this directory for context.

The content below is byte-identical (modulo this header line) to the same file at the root of `maistro-engine`, `AgentTuring`, and `stronghold`.

---

# Roadmap (Four-Repo Canonical)

**Identical copies live in every repo of the four-repo system:**

- [`BlakeMatthews-dev/maistro-engine`](https://github.com/BlakeMatthews-dev/maistro-engine) (substrate)
- [`BlakeMatthews-dev/Project_mAIstro`](https://github.com/BlakeMatthews-dev/Project_mAIstro) (single-tenant secure multi-user)
- [`BlakeMatthews-dev/AgentTuring`](https://github.com/BlakeMatthews-dev/AgentTuring) (autonoetic experiment)
- [`agent-stronghold/stronghold`](https://github.com/agent-stronghold/stronghold) (multi-tenant enterprise)

The full BACKLOG is the companion: see [`BACKLOG.md`](BACKLOG.md). The four-repo governance that defines this layout is [`engine#ADR-030`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/docs/adr/ADR-030-four-repo-governance.md).

See also: `ROADMAP-v1.0.md` for this product's v1.0 acceptance detail (a separate proposal once the v1.0 work surfaces).

## Item ID convention

| Prefix | Repo | Concern |
|---|---|---|
| `engine-NNN` | `maistro-engine` | Substrate library, canonical ADRs, Copier templates, registry CI |
| `maistro-NNN` | `Project_mAIstro` | Single-tenant multi-user product (self-hosting) |
| `turing-NNN` | `AgentTuring` | Autonoetic experimental product (continuity of self) |
| `sh-NNN` | `stronghold` | Multi-tenant enterprise product (compliance + isolation) |

Cross-repo references use `[repo#item-id]` notation.

## The system at a glance

| Repo | Role | Dominant constraint |
|---|---|---|
| `maistro-engine` | Substrate library + canonical ADRs + Copier templates + registry CI | n/a (substrate) |
| `Project_mAIstro` | Single-tenant secure multi-user product | **Ease of self-hosting** |
| `AgentTuring` | Autonoetic experimental agent | **Continuity of self** |
| `stronghold` | Multi-tenant enterprise product | **Multi-tenant isolation** |

## Horizons

- **v1.0** — 3 months. Per-product MVPs ship; substrate code parity reached.
- **v1.1–1.3** — 3–12 months. Hardening and inventory drainage.
- **v2.0** — 12 months. Inventory-clear.

---

## v1.0 (3 months) — organised by cross-repo phase

Phases A–D run sequentially-ish in the substrate. Phase E (per-product v1.0) runs in parallel from week 1, gated by the substrate items it depends on. Phase F ramps from week 6.

### Phase A — Foundation enforcement (weeks 1–4)

See canonical at [`maistro-engine/ROADMAP.md`](https://github.com/BlakeMatthews-dev/maistro-engine/blob/main/ROADMAP.md) for the complete tabular content (engine-001 registry CI, front-matter rollout, etc.).

### Phase B — Templates bootstrapped (weeks 2–6)

`[engine-010]` single-tenant-multi-user template; `[engine-011]` autonoetic; `[engine-012]` multi-tenant. Each round-trips against its product. `[engine-013]` two-stream release pipeline (`pkg/v*` + `template/v*`). `[maistro-095]` / `[turing-043]` / `[sh-095]` per-product bootstraps.

### Phase C — Drift closure (weeks 3–7)

`[engine-020]` K8S-* ADR migration AT → stronghold (coordinator); `[turing-042]` and `[sh-020]` are the AT-side and SH-side. `[engine-021]` memory dedup; `[turing-091]` and `[maistro-091]` are the product-side `Substrate:` recasts. `[engine-022]` catalog dedup; `[maistro-092]` is the product-side recast.

### Phase D — Substrate code parity (weeks 4–9)

`[engine-030]` Ontology Semantic facet (per `engine#ADR-036`); `[engine-031]` Observability primitives (per `engine#ADR-037`); `[engine-032]` Reliability primitives (per `engine#ADR-038`).

### Phase E — Per-product v1.0 (weeks 1–12, parallel)

#### Project_mAIstro v1.0 — multi-user with hard isolation + setup wizard

Dominant constraint: ease of self-hosting.

- `[maistro-001]` Setup wizard (`S-139` is the spec). Acceptance: a new household completes setup in < 30 min.
- `[maistro-002]` Per-user memory isolation. Property test: cross-user retrieval is structurally impossible.
- `[maistro-003]` Multi-user auth (Keycloak / JWT). Specs `S-018`/`S-019`/`S-024`.
- `[maistro-004]` Native install + Podman + systemd. Specs `S-147`/`S-148`.
- `[maistro-005]` Tailscale-native networking. Spec `S-153`.
- `[maistro-006]` Setup-wizard property test.
- `[maistro-007]` Per-user isolation property test.

#### AgentTuring v1.0 — measurable autonoesis

Full detail in [`AgentTuring/ROADMAP-v1.0.md`](https://github.com/BlakeMatthews-dev/AgentTuring/blob/main/ROADMAP-v1.0.md).

Key items: `[turing-001]` HEXACO + retest, `[turing-010]` 7-tier memory, `[turing-020]` self-talk loop, `[turing-030..034]` five property tests, `[turing-035]` 30-day staging run.

#### stronghold v1.0 — compliance-first

Full detail in [`stronghold/ROADMAP-v1.0.md`](https://github.com/agent-stronghold/stronghold/blob/main/ROADMAP-v1.0.md).

Key items: `[sh-001]` multi-tenant catalog wrapper, `[sh-010]` OPA adapter, `[sh-030]` COMPLIANCE.md OWASP mapping, `[sh-040]` two-tenant red-team CI, `[sh-050]` on-prem + cloud parity, `[sh-060]` audit chain.

### Phase F — Contracts as the bar (weeks 6–12)

Per `engine#ADR-032`. Mutation-testing kill rate is the v1.0 quality bar (≥95% boundary, ≥80% behavioral, ≥75% cross-service). `[engine-040..043]` and per-repo `[*-095]` adopt-contract-markers items.

---

## v1.1 (3–6 months) — hardening

Key items: `[engine-050]` cross-product agent portability, `[engine-051]` Forge iteration loop primitive, `[engine-052]` compliance gap audit. Turing v1.1: `[turing-050]` lineage queries, `[turing-051]` dream loop, `[turing-052]` phantom execution, `[turing-053]` adversarial hardening. Stronghold v1.1: `[sh-100]` trust-tier auto-promotion, `[sh-101]` Forge iteration (stronghold side), `[sh-102]` tournament evolution internal-only. mAIstro v1.1: `[maistro-100]` voice + email + Alexa, `[maistro-101]` hardware-signing, `[maistro-102]` internal trust root, `[maistro-103]` DID/VC.

## v1.2 (6–9 months) — RASO inner loop + memory v2 if surfaced

`[engine-060]` memory v2 (engine-led if surfaced); `[engine-061]` DSPy task signatures; `[engine-062]` mid-session model switching. Turing: `[turing-060..062]`. Stronghold: `[sh-200..201]`. mAIstro: `[maistro-200..202]` (hyperagent runtime, low-code designer, HITL primitive).

## v1.3 (9–12 months) — RASO meta-agent + agent marketplace

Turing: `[turing-070..072]` self-modifying activation graph. Stronghold: `[sh-300..301]` agent marketplace + multi-region failover.

## v2.0 (12+ months) — inventory-clear

Engine: `[engine-070..073]` Ontology Kinetic + Dynamic facets, cross-tenant ontology sharing, tournament evolution to production routing. Turing: `[turing-080..083]` self-model export/import, long-horizon recall, synthesised mood, confidence-calibrated routing. Stronghold: `[sh-400..402]` SOC 2, ISO 27001, sectoral regulators. mAIstro: `[maistro-300]` cross-self portability for households (if `[turing-080]` substrates).

---

## Cross-repo dependency graph (v1.0 critical path)

```
engine-001 (Registry CI)
    ├─→ engine-002, engine-021, engine-022, *-090 (front-matter)
    └─→ (CI flips hard at day 30)

engine-010/011/012 (Copier templates) → *-095/043 (per-product bootstrap)
engine-030 (Ontology) → turing-004
engine-031 (Observability) → turing-020 + sh-060
engine-032 (Reliability) → turing-035 + sh-050
engine-020 (K8S migration coord) → turing-042 (out) + sh-020 (in)
```

## Maintenance

- This file is **identical across all four repos**. Any edit lands in all four.
- Items get appended; status changes happen in-place. IDs are stable; never renumbered.
- Once `engine-001` (registry CI) ships, ROADMAP and BACKLOG are regenerated from front-matter.
