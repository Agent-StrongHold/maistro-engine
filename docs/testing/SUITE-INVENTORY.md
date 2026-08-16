# Test suite inventory

Per-suite collected **node-ID counts**, for C1 (#286). Node IDs, not static
`def test_` counts — parametrization expands one `def` into many IDs, so
counting definitions understates every parametrized suite.

**This table is enforced.** `ci.yml`'s `test` job runs
[`scripts/check-suite-inventory.py`](../../scripts/check-suite-inventory.py) as
its last step; it collects every suite below and fails the build if any count
drifts. When you legitimately add or remove tests, refresh the table and commit
it with your change:

```bash
python3 scripts/check-suite-inventory.py            # check (what CI runs)
python3 scripts/check-suite-inventory.py --update   # rewrite the counts below
```

The gate compares **counts, not node-ID sets** — a checked-in manifest of ~9,500
node IDs would churn on every `@parametrize` tweak, and the rename case it would
catch is already covered by the suites actually *running* in CI. What counts
catch, and nothing else does, is a suite silently dropping to zero collected.
Rationale in full in the script's module docstring.

Regenerate a single suite by hand with:

```bash
# Everything under the uv workspace:
REQUIRE_AUTH=false MAISTRO_DRY_RUN=1 uv run pytest <suite> --collect-only -q | tail -3

# hive-conductor is the exception — bare python, never uv. Its conftest
# re-inserts the backend dir at sys.path[0] because the monorepo root has a
# `services/` package that shadows its own (ci.yml:149 runs it this way).
REQUIRE_AUTH=false MAISTRO_DRY_RUN=1 python3 -m pytest packages/hive-conductor/backend/tests --collect-only -q | tail -3

# formal/ needs evolve + rsi on PYTHONPATH, not just core — omitting them is
# a collection ImportError, not a test failure, and reads like a broken suite:
PYTHONPATH=packages/maistro-core/src:packages/maistro-evolve/src:packages/maistro-rsi/src \
  uv run pytest formal --collect-only -q | tail -3
```

## Counts as of current branch

Refreshed after the runtime cleanup queue (#355, #359, #361), the promotion
CI reconciliation, the Workspace/Persona convergence slice, and Stream 5 parity
characterization. The convergence work adds 44 maistro-core node IDs covering
ExecutionRuntime mechanics, Project to Workspace compatibility,
WorkspaceMembership role semantics, the live Persona model, and
one-Persona-per-Workspace persistence. Stream 5 adds four maistro-core node IDs.
Graph routing parity in #402 adds 10 maistro-core node IDs.
Graph execution-state frontier coverage in #403 adds nine maistro-core node IDs.
Stream 1 adds 99 maistro-core node IDs for the canonical Project,
Run/NodeRun/Attempt, runtime, persistence, and execution-service contracts.
Stream 6 adds five provider-parity node IDs.
Stream 3 authorization/resource-scope coverage adds 19 maistro-core node IDs.
Stream 7 product-adapter parity adds four maistro-core and two maistro-canvas
node IDs.
Stream 2 event, checkpoint, and outbox coverage adds 51 maistro-core node IDs.
The repo-task wrapper compatibility regression adds one maistro-evolve node ID.
Reachability production-root coverage adds four root-suite node IDs.
Mutation scheduler/history coverage adds ten root-suite node IDs.
Mutation continuation and repository-health aggregation add twelve root-suite
node IDs.
Workspace creation was deliberately moved out of the scope-gated parametrized
Hive cases and into the ordinary product-surface check, so Hive loses one
collected node ID while retaining the intended assertion. Other suite counts are
unchanged.

| Suite | Node IDs | Runs in CI |
|---|---:|---|
| `packages/maistro-core/tests` | 6137 | `ci.yml` |
| `packages/maistro-evolve/tests` | 629 | `ci.yml` |
| `packages/maistro-rsi/tests` | 427 | `ci.yml` |
| `packages/maistro-server/tests` | 185 | `ci.yml` |
| `packages/maistro-turing/tests` | 176 | `ci.yml` |
| `packages/maistro-design/tests` | 156 | `ci.yml` |
| `packages/maistro-bootstrap/tests` | 123 | `ci.yml` |
| `packages/maistro-canvas/tests` | 124 | `ci.yml` |
| `packages/maistro-turing/backend/tests` | 26 | `ci.yml` (own invocation) |
| `tests/` (root) | 638 | `ci.yml` (minus `tests/tools/registry`, which `registry.yml` owns) |
| `formal/` | 417 | `formal-conformance.yml` + `quality.yml` Pillar 2 |
| `packages/hive-conductor/backend/tests` | 1230 | `ci.yml` (bare python) |
| `packages/hive-conductor/tests/e2e` | 24 | `ci.yml` `hive-conductor-e2e` (docker-compose) |
