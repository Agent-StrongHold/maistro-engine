# Project_mAIstro — ROADMAP and BACKLOG Proposal

**Status:** Proposal pending application.
**Reason:** This session's GitHub MCP scope is limited to `maistro-engine`, `AgentTuring`, and `stronghold`. `Project_mAIstro` is not in the allowlist, so the canonical ROADMAP and BACKLOG cannot be pushed there directly.

The canonical ROADMAP and BACKLOG are **identical across all four repos** per [`engine#ADR-030`](../../adr/ADR-030-four-repo-governance.md) (four-repo governance) and the user's directive *"a full roadmap and backlog on every repo but tagged by repo".* This proposal contains the canonical files exactly as they should appear at `Project_mAIstro/ROADMAP.md` and `Project_mAIstro/BACKLOG.md`.

## How to apply

1. Copy [`ROADMAP.md`](ROADMAP.md) from this directory to `Project_mAIstro/ROADMAP.md` (replacing whatever is there).
2. Copy [`BACKLOG.md`](BACKLOG.md) from this directory to `Project_mAIstro/BACKLOG.md` (replacing whatever is there).
3. Open a PR titled "docs(roadmap,backlog): adopt four-repo canonical ROADMAP and BACKLOG" with body referencing `engine#ADR-030`.
4. After merge, this proposal directory can be deleted from `maistro-engine`.

**Alternative:** Add `BlakeMatthews-dev/Project_mAIstro` to the GitHub MCP server's allowed-repos config, restart the session, and let me push directly.

## Files in this proposal

- [`ROADMAP.md`](ROADMAP.md) — four-repo canonical roadmap (~9KB)
- [`BACKLOG.md`](BACKLOG.md) — four-repo canonical backlog (~10KB)

These are byte-identical (apart from this README) to the same files at the root of `maistro-engine`, `AgentTuring`, and `stronghold`.

## What `Project_mAIstro`'s items in the canonical look like

The canonical `BACKLOG.md` includes a `Project_mAIstro` section with these items, all tagged `maistro-NNN`:

### v1.0 — multi-user with hard isolation + setup wizard

Dominant constraint: **ease of self-hosting**.

- `[maistro-001]` Setup wizard (`S-139`)
- `[maistro-002]` Per-user memory isolation
- `[maistro-003]` Multi-user auth (Keycloak / JWT) (`S-018`, `S-019`, `S-024`)
- `[maistro-004]` Native install + Podman + systemd (`S-147`, `S-148`)
- `[maistro-005]` Tailscale-native networking (`S-153`)
- `[maistro-006]` Setup-wizard property test
- `[maistro-007]` Per-user isolation property test

### Documentation hygiene

- `[maistro-090]` Front-matter on mAIstro specs (91 specs; `S-NNN` → `SPEC-NNN` on touch)
- `[maistro-091]` Memory specs `Substrate:` recast (`S-008`/`S-009`/`S-032`/`S-033`)
- `[maistro-092]` Catalog specs `Substrate:` recast (`S-005`/`S-138`)
- `[maistro-095]` Copier bootstrap into `engine/templates/single-tenant-multi-user/`

### v1.1–v2.0

- `[maistro-100]` Voice + email + Alexa channels (`S-041`/`S-042`/`S-043`/`S-103`/`S-104`)
- `[maistro-101]` Hardware-signing integration (`S-150`, substrate `engine#ADR-022`)
- `[maistro-102]` Internal trust root (`S-155`, substrate `engine#ADR-026`)
- `[maistro-103]` DID/VC agent identity (`S-152`, substrate `engine#ADR-024`)
- `[maistro-200]` Hyperagent graph runtime (`S-145`)
- `[maistro-201]` Node-graph designer / low-code (`S-159`)
- `[maistro-202]` Human-as-node HITL primitive (`S-158`)
- `[maistro-300]` Cross-self portability for households (v2.0; if `[turing-080]` substrates cleanly)

Full detail in the canonical [`BACKLOG.md`](BACKLOG.md) included alongside this README.

## Notes for review

- The mAIstro v1.0 dominant constraint (ease of self-hosting) drives all `[maistro-001..007]` choices.
- Specs S-NNN currently in `Project_mAIstro/specs/` should be renumbered to `SPEC-NNN` only on touch (per `engine#ADR-031`); not as a bulk migration.
- Memory specs (`S-008`, `S-009`, `S-032`, `S-033`) need `substrate:` cross-refs to engine ADR-016/017/018 per `engine#ADR-034` (memory canonical ownership). The recast is `[maistro-091]`.
- Catalog specs (`S-005`, `S-138`) need similar substrate cross-refs per `engine#ADR-035`.
- Project_mAIstro deliberately has zero ADRs; architectural choices live in engine ADRs and are cited via `substrate:` in product specs.
