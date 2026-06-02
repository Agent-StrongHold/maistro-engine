# Engine specs (`docs/specs/`)

Numbered specifications that live in this monorepo (distinct from sibling `Project_mAIstro/specs/` trees). Each file is `SPEC-NNN-<slug>.md` with front-matter per [`ADR-031`](../adr/ADR-031-front-matter-and-registry.md).

Frozen **reference** trees that specs ported from (hyperagent bundle, gateway snapshot) were archived under `potential-dead-code/` and have since been **removed** ([SPEC-178](./SPEC-178-legacy-snapshot-retention.md)); provenance lives in git history and the sibling repos.

| ID | Document |
|---|---|
| SPEC-175 | [Task progress webhook](SPEC-175-task-progress-webhook.md) |
| SPEC-176 | [Hive Conductor package](SPEC-176-hive-conductor-package.md) |
| SPEC-177 | [Hyperagent graph execution](SPEC-177-hyperagent-graph-execution.md) |
| SPEC-178 | [Legacy snapshot retention](SPEC-178-legacy-snapshot-retention.md) |
| SPEC-179 | [Flutter gateway node](SPEC-179-flutter-gateway-node.md) |

Cross-repo inventory: [`docs/INVENTORY-ADRS-SPECS.md`](../INVENTORY-ADRS-SPECS.md). Pull sibling product specs with `./scripts/pull-sibling-product-specs.sh` (see root `AGENTS.md`).
