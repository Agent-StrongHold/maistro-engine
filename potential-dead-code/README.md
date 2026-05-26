# potential-dead-code

Archive of layouts and code paths that are **not** on `PYTHONPATH` or part of supported imports. The former root `src/maistro` tree lives under `legacy-maistro-site/` for historical diff context while canonical code lives under `packages/`.

**Sibling / legacy reference snapshots** (same rules — not imported, provenance only) live beside it:

- `potential-dead-code/code-worth-implementing-from-legacy/` — curated hyperagent port bundle ([SPEC-177](../docs/specs/SPEC-177-hyperagent-graph-execution.md))
- `potential-dead-code/code-worth-implementing-from-legacy-site-complete/` — full-tree duplicate of `potential-dead-code/legacy-maistro-site/`
- `potential-dead-code/code-worth-implementing-from-Conductor/` · `potential-dead-code/code-worth-implementing-from-HiveConductor/` · `potential-dead-code/code-worth-implementing-from-Project-mAIstro/` — optional vendored snapshots; prefer live sibling repos when possible

**Do not add new features here.** Port into `packages/maistro-core` or `packages/maistro-server` per [`docs/specs/SPEC-177-hyperagent-graph-execution.md`](../docs/specs/SPEC-177-hyperagent-graph-execution.md).

**Removal policy:** [`docs/specs/SPEC-178-legacy-snapshot-retention.md`](../docs/specs/SPEC-178-legacy-snapshot-retention.md).

## Superseded ports

- `potential-dead-code/superseded-by-SPEC-175/` — `ProgressReporter` archived after port to `maistro.tasks.progress_webhook` ([SPEC-175](../docs/specs/SPEC-175-task-progress-webhook.md)). Eligible for deletion per SPEC-178.
