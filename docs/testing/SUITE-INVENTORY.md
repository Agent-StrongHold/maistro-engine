# Test suite inventory

Per-suite collected **node-ID counts**, for C1 (#286). Node IDs, not static
`def test_` counts — parametrization expands one `def` into many IDs, so
counting definitions understates every parametrized suite.

Regenerate with:

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

## Counts as of `develop` @ F3 (#336)

| Suite | Node IDs | Runs in CI |
|---|---:|---|
| `packages/maistro-core/tests` | 5732 | `ci.yml` |
| `packages/maistro-evolve/tests` | 528 | `ci.yml` |
| `packages/maistro-rsi/tests` | 427 | `ci.yml` |
| `packages/maistro-server/tests` | 185 | `ci.yml` |
| `packages/maistro-turing/tests` | 176 | `ci.yml` |
| `packages/maistro-design/tests` | 156 | `ci.yml` |
| `packages/maistro-bootstrap/tests` | 123 | `ci.yml` |
| `packages/maistro-canvas/tests` | 122 | `ci.yml` |
| `packages/maistro-turing/backend/tests` | 26 | `ci.yml` (own invocation) |
| `tests/` (root) | 599 | `ci.yml` (minus `tests/tools/registry`, which `registry.yml` owns) |
| `formal/` | 417 | `formal-conformance.yml` + `quality.yml` Pillar 2 |
| `packages/hive-conductor/backend/tests` | 1042 | `ci.yml` (bare python) |
| `packages/hive-conductor/tests/e2e` | 24 | `ci.yml` `hive-conductor-e2e` (docker-compose) |

## `packages/hive-conductor/tests/e2e` — read before "wiring it in"

C1's context lists this directory as ~31 orphaned tests. That count does not
survive contact with the files. It contains four `test_*.py` modules, and only
**one** is a pytest suite:

- **`test_pm_workflow_api.py`** — 24 real tests. **Already covered**: the
  `hive-conductor-e2e` job runs it against the docker-compose stack. It is not
  orphaned.
- **`test_pm_agent.py`**, **`test_pm_real_atlassian.py`** — **not test suites**.
  Neither defines a single `test_*` function; both are manual scripts whose
  entry point is `run_pm_workflow()` / `run()` under
  `if __name__ == "__main__"`. They contribute **zero** node IDs. Adding them
  to a CI invocation would run nothing.
- **`test_pm_vision.py`** — real tests, but they drive a real browser against a
  live conductor and need a real `GOOGLE_API_KEY`.

All three of the latter imported `browser_use` unguarded at module scope. That
package ships only in `Dockerfile.research` (the main image deliberately sheds
the browser surface — see the root `Dockerfile` header), so importing it raised
`ModuleNotFoundError` **at collection time**, which aborted collection for the
entire directory — all four modules, including the 24 real tests. They are now
`pytest.importorskip`-guarded, so the directory collects cleanly and each
skip states its reason.

**`test_pm_workflow_api.py` is deliberately left unguarded.** A
`skipif`-on-unreachable-server would make it silently skip inside the very
compose job that exists to run it — converting a real test into a green no-op.
It should error loudly when the stack it needs is absent.

## Known gap against C1's acceptance criterion

C1 asks that "CI-collected node IDs match [this inventory] (± documented
skips)". This document is the inventory half. **The automated comparison is not
wired up** — nothing currently fails CI when a suite's collected count drifts
from the table above. That check is the remaining work on #286; the counts here
are a hand-regenerated snapshot until it exists.
