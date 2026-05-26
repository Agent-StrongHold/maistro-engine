# Code worth implementing (from legacy) — **superseded by spec**

**Canonical porting spec:** [`docs/specs/SPEC-177-hyperagent-graph-execution.md`](../../docs/specs/SPEC-177-hyperagent-graph-execution.md)  
**When to delete this folder:** after SPEC-177 is **Implemented** (see [`SPEC-178`](../../docs/specs/SPEC-178-legacy-snapshot-retention.md)).

The Python files beside this README are a **frozen reference bundle** (hyperagent graph, SCOUT, optimizer, types, task fields, conductor branch). They are not importable as-is in the monorepo. Use SPEC-177 appendix A for the path map into `packages/maistro-core`.

**Related snapshots** (same retention rules — see SPEC-178):

| Folder | Role |
|--------|------|
| `../code-worth-implementing-from-legacy-site-complete/` | Full-tree duplicate of `potential-dead-code/legacy-maistro-site/` |
| `../code-worth-implementing-from-Project-mAIstro/` | Project_mAIstro conductor + specs + gateway snapshots |
| `../code-worth-implementing-from-Conductor/` · `../code-worth-implementing-from-HiveConductor/` | Other sibling snapshots — same retention rules |

**Do not re-add** large `cp -R` trees for internal stack clones; they are **gitignored** per [SPEC-178](../../docs/specs/SPEC-178-legacy-snapshot-retention.md) (see root `.gitignore`).
