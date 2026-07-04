# Cross-repo mining — durable checkpoint folder

This folder is the **crash-safe shared state** for the effort to mine
`stronghold`, `AgentTuring`, and `A2UI` into `maistro-engine`. It is committed to the
branch on every slice completion, so a session crash, stall, or container reclaim can
never lose more than the last file of analysis.

## Layout

```
docs/mining/
  README.md                 # this file
  INVENTORY.md              # master consolidated, ranked, deconflicted backlog
  reports/<slice-id>.md     # one report per search agent, appended one finding at a time
  progress/<slice-id>.json  # heartbeat per slice: status/files_done/last_file/note
```

## Scope rule (product-agnostic only)

Per engine **ADR-019** (canonical-source-split) and **ADR-035** (catalog-ownership-split),
maistro-core keeps only the *soft* scope axes `global→org→team→user→agent→session`.
Enterprise/multi-tenant, hard `tenant` isolation, K8s, OIDC/Entra, and the coin/wallet
economy are **Stronghold-owned** — findings tag these `Stronghold-owned: skip`; they are
inventoried but not ported into the engine.

## Search-agent contract (crash-safe)

1. **Resume first** — read your own `reports/<slice>.md` + `progress/<slice>.json`; skip
   files already recorded; continue from `files_done`.
2. **Flush after every file** — append the finding block immediately; never hold findings
   across more than one file.
3. **Heartbeat after every file** — overwrite `progress/<slice>.json`.
4. **On completion** — set `status: complete`, write a 3–5 line summary at the top.

## Finding block format

```
### <stronghold/path>:<line>
- **What:** …
- **Engine coverage checked:** <engine file(s) grepped/read> → present / partial / missing
- **Gap severity:** missing | partial | stubbed | weaker | parity
- **Action:** port code | new ADR | new SPEC | merge into <id> | concept-note | skip
- **Effort:** S | M | L
- **Product-agnostic?** yes | Stronghold-owned (skip)
```

## Provenance

`reports/wave1-*.md` are the completed first-wave (Opus) reports, transcribed here so the
inventory lives in one place. `reports/S01…S17` are the Haiku re-scan slices (finer,
line-level; they close the veins a session-limit crash left partial).
