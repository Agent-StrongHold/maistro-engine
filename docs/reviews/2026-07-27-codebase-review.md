# Maistro Engine — Codebase Review & Remediation Plan

**Date:** 2026-07-27
**Scope:** all 10 packages, `formal/`, root `tests/`, 9 CI workflows, `docs/adr` + `docs/specs`
**Method:** 14-agent fleet (3 Haiku enumerators → 4 Sonnet scouts → 5 Opus reviewers → 2 Opus
adversarial verifiers), synthesized and execution-verified by the orchestrator.
Fleet specification: [`2026-07-27-agent-fleet-spec.md`](./2026-07-27-agent-fleet-spec.md).

---

## Executive summary

This is a **healthy, unusually well-tested codebase with a weak safety net around it**. The
review did not find a rotting core; it found strong engineering protected by gates that do not
gate, tests that CI does not run, and a handful of security controls that are implemented,
documented, and then never wired up.

Four themes, in priority order:

**1. The safety net is decorative in specific, fixable places.** maistro-core has **97% line
coverage across 5,568 passing tests** — genuinely good — but the CI coverage gate is
`--fail-under=20`, tolerating a 77-point regression. Separately, **542 passing tests are never
executed by any workflow**. Neither problem requires writing a single test.

**2. Three security controls are inert because of one-line wiring gaps.** Sentinel's tool
authorization, the Gate's three-strike lockout, and the skill-import Warden scan are each fully
implemented, individually tested, and disconnected in `container.py`. The formal conformance
suite cannot catch this class of bug because every property test injects its own correctly-wired
object.

**3. Four genuinely unauthenticated surfaces exist.** In hive-conductor: WebSocket routes (one of
which executes a DAG) bypass the auth middleware by construction, and container lifecycle control
over the host Docker daemon is reachable by any registered user. In maistro-canvas: the
book-maker server has no auth on any route, binds `0.0.0.0`, and proxies paid provider keys. In
maistro-server: webhook signature verification is skipped whenever the secret is unset, which is
the default — and the resulting attacker-controlled text becomes an autonomous agent's task.

**4. Documentation has drifted far enough to mislead.** CLAUDE.md undercounts ADRs by 54,
contradicts itself on the core tenancy rule, and omits two packages — one of which is an
unguarded runtime import of the shipped API.

**On the adversarial verification wave:** 18 High/Critical findings went to two independent
verifiers instructed to refute them. **2 were refuted outright, 13 were downgraded, and 3 were
confirmed** (one of them strengthened — the canvas server turned out to bind publicly and sit in
the documented run path, not to be dev-only scaffolding). Refuted and downgraded findings are
recorded in Appendix A rather than deleted, so the next review does not re-raise them. Roughly
two-thirds of the raw High/Critical output did not survive contact with the code; the surviving
third is what this plan funds.

---

## Verified by execution

Everything in this section was produced by running code, not by reading it.

| Suite | Result | Run by CI? |
|---|---|---|
| maistro-core | **5,568 passed**, 1 skipped, 1 xfailed (91s) — **97% coverage** (24,849 stmts, 784 missed) | yes |
| root `tests/` | **360 passed** (6.1s) | **no** |
| `maistro-turing/backend` | **26 passed** (2.3s) | **no** |
| `maistro-design` | **156 passed** (2.2s) | **no** |

`ruff check` and `ruff format --check` both pass cleanly across all packages (1,530 files), so
remediation starts from a clean lint baseline.

---

## Findings

Severity reflects the **post-verification** rating. "Confirmed by" indicates who established it.

### Critical

**C1 — Sentinel tool authorization is inert and fails open.**
`container.py:386` constructs `Sentinel` with `permission_table: PermissionTable = {}`, and
`security/_types.py:31-35` returns `True` whenever a tool is absent from that table. Nothing
anywhere in `packages/*/src` ever populates it. The documented control "Sentinel validates tool
calls" therefore denies nothing to anyone. Every formal property test supplies its own populated
table, so the suite proves the logic correct while never touching production wiring.
*Confirmed by direct inspection.*

**C2 — hive-conductor WebSocket endpoints are unauthenticated, and one executes work.**
`routes/ws.py` is 67 lines containing zero references to auth, tokens, cookies, or users.
`AuthMiddleware` subclasses Starlette's `BaseHTTPMiddleware`, which only sees ASGI scope
`type == "http"`, so websocket connections never reach `dispatch`. `stream_dag_run`
(`routes/ws.py:35-66`) calls `execute_dag_streaming`, i.e. LLM calls and tool invocations, for
any caller who can reach the port. Browsers do not apply CORS to WebSockets.
*Confirmed by direct inspection.* Mitigation on severity: `dag_id` is a uuid4, so an attacker
needs a leaked id — this reduces exploitability, not the missing control.

**C3 — Container lifecycle over the host Docker daemon is open to any registered user.**
`routes/containers.py` contains no `Depends`, no `request.state` check — start, stop, restart,
force-delete and log-read for every container on the host. The middleware's `_PROTECTED_OPS`
list (`middleware/auth.py:47-92`) has no `/v1/containers` entry, and `POST /v1/auth/register`
is public once setup completes. The module's own comment calls itself "trusted, admin-only".
*Confirmed by direct inspection.*

**C4 — The canvas book-maker server has no authentication on any route and binds publicly.**
`packages/maistro-canvas/frontend/server.js` contains no auth middleware of any kind across ~24
routes, uses `cors()` with no allowlist and a 200 MB body limit (`:14-16`), and **binds
`0.0.0.0:5174` rather than loopback** (`:658`). Anyone who can reach the port can spend the
operator's LiteLLM/Azure/Gemini keys through the `/api/llm/*` proxies (`:386-389,:398`), destroy
all data via an unauthenticated `DELETE /api/books` that TRUNCATEs the table (`:77-84`), and
spawn an unbounded `python3` subprocess per request through `/api/export` with no cap on `pages`
(`:335-345`). The verifier established this is not dead scaffolding: `npm run server` and vite's
`/api → localhost:5174` proxy wire it into the documented run path.
*Confirmed and strengthened by verifier V1.*

**C5 — Webhook endpoints accept unsigned requests by default and feed an autonomous agent.**
`config/settings.py:131-132` defaults `github_webhook_secret`/`ci_webhook_secret` to `""` with no
validator; the empty-secret branch logs a warning and falls through to `queue.submit(task)`
(`api/webhooks.py:111-115,:202-206`). `_validate_startup` (`main.py:54-60`) checks `api_keys`
only, and the router is mounted with no auth dependency. The submitted task text is
attacker-controlled (`issue.title`, `issue.body`) and becomes the instruction for an autonomous
coding agent scoped to the repository; `detect_injection` results are logged and never block.
*Confirmed by verifier V1.*

### High

**H1 — The coverage gate permits a 77-point regression.**
`quality.yml:206` names the step "Coverage gate (95% line + 95% branch on touched files)";
`quality.yml:214` runs `coverage report --fail-under=20`. Measured actual coverage is **97%**.
The "separate matrix job (changed-files filter)" its comment defers to does not exist anywhere
in `.github/workflows/`, and `docs/QA-BASELINE.md` (cited at `quality.yml:210`) does not exist.
*Confirmed by execution + inspection.*

**H2 — 542 passing tests are orphaned from CI.**
The root `tests/` tree (360 tests), `maistro-turing/backend` (26 tests, an auth-bearing FastAPI
service with two privilege lanes), and `maistro-design` (156 tests, a package hive-conductor
imports unguarded on its live `/v1` surface) are all listed in `pyproject.toml` `testpaths` but
invoked by no workflow. All three pass today in ~11 seconds combined.
*Confirmed by execution.*

**H3 — The Gate's three-strike lockout never fires.**
`container.py:379` builds `Gate(warden=warden)` with no `strike_tracker`; every strike path in
`security/gate.py` is guarded by `if self._strike_tracker and user_id:`. A caller can trip Warden
without limit. The durable `PgStrikeTracker` (`security/pg_strikes.py:51-156`) is fully
implemented, correct, and has zero construction sites outside its own tests.
*Confirmed by direct inspection.*

**H4 — `Agent.handle()` discards the classified intent.**
`agents/base.py:219` is the **only** occurrence of the token `intent` in all 733 lines of the
file — the parameter is declared and never read. `conduit.py:120-125` passes `intent=intent` and
never passes `classified_task_type`, so the task type feeding strategy construction, RCA tagging
and learning scope is permanently `""` on every live request, and the tier computation is dead
work. *Confirmed by direct inspection.*

**H5 — `_apply_intent_hint` validates against the wrong domain.**
`conduit.py:48-59` iterates `TIER_ORDER` — the model-size tiers `small/medium/large/frontier` —
and writes a match into `intent.task_type`, whose domain is `config.task_types`. So
`intent_hint="large"` silently corrupts routing to the default agent, while every legitimate
hint (`"code"`, `"chat"`) is silently ignored. *Confirmed by direct inspection.*

**H6 — SQLite writer connection is mutated from two threads with no lock.**
`state.py:46` creates `self._writer_lock` and it is **never acquired anywhere in the file**.
`_writer_loop` commits on the writer thread while `run_migration` executes
`SAVEPOINT`/`RELEASE`/`ROLLBACK TO` and `backup()` runs `PRAGMA wal_checkpoint(FULL)` on the
calling thread, over the same `check_same_thread=False` connection. A background commit
interleaved inside a migration savepoint can leave a half-applied schema despite
`MigrationFailedError` promising the DB is unchanged. *Confirmed by direct inspection.*

**H7 — `State.close()` discards queued writes.**
`state.py:165` sets `_shutdown` *before* enqueuing the sentinel, and `_writer_loop`'s guard is
`while not self._shutdown.is_set()` — so the loop exits at its next check without draining.
Because `PersistedStore.put`/`delete` are fire-and-forget, callers receive no error and believe
the writes landed. *Confirmed by direct inspection.*

**H8 — Learnings are retrieved without scope filtering and injected into system prompts.**
`sqlite_learnings.py` `find_relevant` accepts `org_id` and never uses it — the query is
`SELECT * FROM learnings WHERE status = 'active'` — and the table schema (`:14-29`) has no
`org_id` column at all. `user_id` and `scope` columns exist and are likewise not filtered.
Results are interpolated into the agent system prompt between unescaped
`<maistro:corrections>` delimiters (`agents/context_builder.py:45-63`), so a learning containing
the closing tag escapes its block. *Confirmed by direct inspection.*
Severity note: no cross-org **leak** is reachable today because no code writes a non-empty
`org_id` (see A4 in the appendix) — this is the exact invariant Stronghold's tenancy will sit on,
so it should be fixed before that refactor, not after.

**H9 — Unhandled provider exceptions leak traces and skip persistence.**
`agents/base.py:488` catches only `(ValueError, RuntimeError, TimeoutError, OSError)`, and
`handle()` (`:214-330`) has no `try/finally`. The shipped LLM client raises bare `httpx` errors
via `r.raise_for_status()` (`hive-conductor/backend/adapters/maistro_core.py:92`), and
`httpx.HTTPStatusError`/`TransportError` — along with `AgentError`, `LLMProviderError` and
`CircuitOpenError` — derive from `Exception` directly. So the most likely real failure (a provider
outage) bypasses `trace.end()` and `_persist_run` entirely; `conduit.py:126` catches it only after
cleanup was already skipped. *Confirmed by verifier V1.*

**H10 — hive-conductor's chat pipeline invokes neither Warden nor Sentinel, and fails open on
unknown tools.** `chat_completion.py:1662` dispatches via
`_TOOL_HANDLERS.get(tool_name, _tool_poll_jira)` — an unrecognised tool name silently routes to
the Jira poller carrying the user's PAT. No `warden.scan` or `sentinel.pre_call` appears anywhere
in the module, unlike every core strategy. *Confirmed by direct inspection.*

**H11 — hive-conductor has three undeclared runtime dependencies.**
`backend/requirements.txt` (17 lines) declares no `maistro-*` package, yet `routes/design.py:21`
imports `maistro_design` at module scope and `main.py:29,235` registers that router
unconditionally — unlike the `evolution`/`canvas` routers, which are guarded. `maistro_rsi` and
`maistro_evolve` are likewise imported and undeclared. `maistro-design` is additionally absent
from `uv.lock` entirely; it resolves today only via pytest's `pythonpath`. The documented
`uv pip install -r requirements.txt` deploy path therefore fails at import.
*Confirmed by direct inspection.*

### Medium

**M1 — Admin-key comparisons are non-constant-time.** `privilege.py:267,296,313,333` use plain
`!=` for every admin-gated operation, while the same file correctly uses `hmac.compare_digest`
at `:117`. `security/secret_equal.py` exists and has a formal invariant behind it. `privilege.py`
has no property-based coverage of any kind. *Confirmed by direct inspection.*

**M2 — Session cookie lacks `secure`.** `routes/auth.py:158-164` sets `httponly=True,
samesite="lax"` and no `secure=True`. Compounding: server-side sessions are never expired
(`created_at` is stored and never read), and hive-conductor registers no rate-limit middleware,
so `login`/`register` have no brute-force protection. *Confirmed by direct inspection.*

**M3 — Session history is retained forever.** Both SQL session stores implement TTL as a
read-time filter (`sqlite_sessions.py:54` `timestamp > ?`) and never `DELETE`; the only deletion
is session-id-scoped (`:89`) and called by nothing scheduled. `security/pg_strikes.py:187-190`
demonstrates the correct pattern for the same problem. *Confirmed by direct inspection.*

**M4 — The mutation gate does not test the changed files it advertises.** `mutation.yml:39-53`
computes a changed-file list into `steps.changed.outputs.files`; only `.skip` is ever consumed
(`:56,:73,:110`). The config hardcodes `module-path = packages/maistro-core/src/maistro`, so the
job attempts a whole-package sweep under a 30-minute timeout. Its base ref is hardcoded to
`origin/main` on a workflow that also runs for PRs into `develop`/`integration`.
*Confirmed by direct inspection.*

**M5 — Two quality "pillars" are inert and one ratchet script is dead.**
`quality.yml:232` guards the architecture-fitness step on a directory that does not exist, so it
passes green via a warning. The contract-testing pillar (`quality.yml:9`) has no implementation —
`schemathesis` appears nowhere. `scripts/check-radon-baseline.py` is referenced by no workflow
and no script; what runs instead (`quality.yml:87`) is a report-only `radon cc` with no threshold,
under a step named "no function rated C+ allowed". *Confirmed by direct inspection.*

**M5b — A cycling durable DAG would be persisted as COMPLETED.**
`graph/durable_runs/executor.py:141` loops `while record.current_node_id and steps < max_steps`
and both exits fall through to `_mark_completed` (`:212-213`), so a run that exhausts its 256-step
budget is recorded as success with a partial blackboard. Verifier downgraded from High: the only
shipped caller obtains its snapshot from `DagRegistry.register()`, which raises on any DAG failing
`_validate_no_cycles` (`dag_validator.py:216-246`), so this is latent library behaviour rather
than a reachable production failure — it becomes reachable the moment a second caller skips the
registry. *Confirmed as latent by verifier V1.*

**M6 — Registry CI is 20 days past its own strictness deadline and never runs the link/cycle
check.** `registry.yml:4-5` documents a flip to `--strict` after ~2026-07-07; `:52` still runs
`walk .` unstrict. Cycle detection (`find_cycles`) and dangling-link checking (`check_links`)
live only in `cmd_lint`, which no workflow invokes — so supersession cycles and broken
cross-references across 118 ADRs and 151 specs are ungated. Blast radius of the flip is near
zero: only four docs lack front matter and all four are already excluded.
*Confirmed by direct inspection.*

**M7 — Two feature areas can vanish silently.** `main.py:241-243` and `:249-251` wrap the
`canvas` and `pm_fleet_v2` router registrations in bare `except Exception: pass`. An import error
removes those APIs with no log line at any level, while the adjacent `evolution`/`rsi`
registrations do log a warning. *Confirmed by direct inspection.*

**M8 — Dead and duplicated route registrations.** `widgets.router` is registered twice under an
identical prefix (`main.py:207` and `:213`), duplicating every widget path in the OpenAPI schema.
`routes/daily_report.py` (453 LOC), `routes/chat_complete.py` and `routes/projects.py` are
mounted by nothing. *Confirmed by direct inspection.*

**H→M9 — Sentinel audit entries are structurally incompatible with the SQL audit logs.**
`security/_types.py:76-84` and `types/security.py:54-69` define two different `AuditEntry`
shapes; `pg_audit.py:42-43` reads `entry.trace_id`/`entry.request_id`, which the Sentinel-built
entry lacks. Verifier downgraded from High: the write is wrapped in `except Exception` at
`sentinel/policy.py:366-367`, so the failure mode is **silent audit loss**, not a crash — and
neither SQL audit log is currently wired. A latent landmine that detonates exactly when someone
fixes A2. *Confirmed by verifier V2.*

**M10 — `create_container()` has no override seam for its defaults.** Verifier downgraded from
Critical: `Container` is a dataclass whose store fields are protocol-typed, so constructor
injection is a legitimate third substitution path, and ADR-019 names protocols — not a factory
registry — as the Stronghold seam. What remains real is the default-wiring cruft: 26
`type: ignore[assignment]` fields defaulted to `None` with only two backfilled in `__post_init__`,
so a directly-constructed `Container` is a type-safe-looking object full of `None`s.
*Confirmed by verifier V2.*

**M11 — A non-SQLite `database_url` silently degrades to in-memory stores.**
`container.py:362-366`: the `else:` branch of the `startswith("sqlite:")` test assigns four
`InMemory*` stores. The seven Postgres stores (1,097 LOC) have zero non-test constructors
monorepo-wide, while CLAUDE.md advertises "PostgreSQL stores". A misconfigured production URL
loses all data on restart with no error. *Confirmed by direct inspection.*

### Low

**L1 — Documentation drift.** `CLAUDE.md:42` claims "64 ADRs (ADR-000 through ADR-057)"; actual
is **118** (102 sequential up to ADR-101, plus 16 date-scheme) and **151** specs. The same line
says maistro-core has "no `org_id`" while `CLAUDE.md:181` (Convention 7) says the opposite and
explicitly supersedes that shorthand. `CLAUDE.md:115` claims CI does not run turing's suite;
`ci.yml:73` runs it. `maistro-rsi` and `maistro-design` are absent from CLAUDE.md entirely, and
`maistro-bootstrap` is labelled a "stub" despite being 1,275 LOC and a transitive production
dependency. *Confirmed by direct inspection.*

**L2 — Verified-dead code.** `maistro/scheduler/` is 0 bytes with 0 importers repo-wide.
`maistro_turing/producers.py` and `runtime.py` both open with `"""DEAD CODE — superseded by …`
and are shadowed by same-named packages. `services/credential_store_v2.py` is an unreferenced
third credential subsystem that also treats a failed PostgREST write as success
(`:76-77`). *Confirmed by direct inspection.*

**L3 — `execute_canvas`'s `upload` action raises `UnboundLocalError` on every call.**
Runtime-proven: `tool.py:537` binds `upload_img` while `:550-551,560-561` read `img.width`/
`img.height`. **However** — `execute_canvas` has zero callers anywhere in the repo, there is no
`canvas/__init__.py`, and the package `__init__` does not export it. So this is a certain bug in
unreachable legacy code. Its value is as evidence: `tool.py` is 922 LOC of untested, unreferenced
legacy that should be retired rather than patched (Horizon 3, item 6). *Proven by execution;
reachability confirmed by verifier V2.*
Corroborating detail from the parity audit: `upload` is also the one action with **no replacement
in the new engine**. It is broken in the old path and absent from the new one — which is the
clearest available evidence that no user has ever exercised it.

---

## Remediation plan

Ordered by (value ÷ effort), with dependencies noted. Nothing here is speculative — every item
traces to a finding above.

### Horizon 1 — Quick wins (each ≤ 1 day, no design decisions required)

| # | Action | Fixes | Effort |
|---|---|---|---|
| 1 | Add three pytest steps to `ci.yml` for root `tests/`, `maistro-turing/backend/tests`, `maistro-design/tests` | H2 | 15 min |
| 2 | Raise `quality.yml:214` `--fail-under` from 20 toward the measured 97 (suggest 95 with a documented ratchet), rename the step to match what it enforces, or implement the touched-files gate with `diff-cover` | H1 | 1–2 h |
| 3 | Populate `permission_table` in `container.py` from config **and** invert `_types.py:32-35` to fail closed with an explicit `PUBLIC_TOOLS` allowlist | C1 | 0.5 d |
| 4 | Authenticate both WebSocket handlers before `accept()`, mirroring `maistro-server/api/ws.py:81-102`; add an `Origin` check | C2 | 2 h |
| 5 | Add `/v1/containers` to `_PROTECTED_OPS` for POST/DELETE and gate log reads; validate `container_id` against `^[a-zA-Z0-9_.-]{1,128}$` | C3 | 1 h |
| 5a | Add a required-key middleware to canvas `server.js`, refuse to boot without it, bind loopback instead of `0.0.0.0`, replace `cors()` with an origin allowlist, cap `pages` before spawning `python3`, and admin-gate or delete `DELETE /api/books` | C4 | 3 h |
| 5b | Require webhook secrets in `_validate_startup` when the webhooks router is mounted; make `detect_injection` hits reject rather than log | C5 | 2 h |
| 6 | Wire a strike tracker in `container.py` (`PgStrikeTracker` on Postgres, in-memory otherwise) | H3 | 2 h |
| 7 | Fix `_apply_intent_hint` to iterate `config.task_types`; ignore-and-log unknown hints | H5 | 1 h |
| 8 | Reorder `State.close()` to enqueue-and-join before setting `_shutdown`; drain until empty | H7 | 1 h |
| 9 | Replace the four `privilege.py` `!=` comparisons with `secret_equal`; drop `admin_key` from `ElevationGrant`'s repr | M1 | 1 h |
| 10 | Add `secure=True` (config-gated for localhost dev) to the session cookie; enforce absolute session expiry | M2 | 2 h |
| 11 | Delete `scheduler/`, turing's two self-labelled DEAD CODE modules, `credential_store_v2.py`, the three unmounted route modules, and the duplicate `widgets.router` registration | L2, M8 | 2 h |
| 12 | Replace the two bare `except Exception: pass` router guards with the warning-logging form used 10 lines below | M7 | 15 min |
| 13 | Flip `registry.yml:52` to `lint . --strict` (a strict superset of `walk`) | M6 | 15 min |
| 14 | Correct CLAUDE.md: ADR/spec counts, the `org_id` self-contradiction at line 42, the stale turing-CI claim, and add `maistro-rsi`/`maistro-design` to the package table | L1 | 2 h |

**Sequencing note:** items 3 and 6 will surface previously-suppressed denials and lockouts. Land
them early in a release cycle, not before a freeze.

### Horizon 2 — Structural (1–2 weeks)

1. **Fix `Agent.handle()`'s discarded intent (H4).** Derive `classified_task_type` from
   `intent.task_type` and thread tier/preferred-strengths into strategy construction. Add a
   conduit-level test asserting the agent receives a non-empty task type — the absence of that
   assertion is why this survived. *Do this before any routing-quality work, since routing
   metrics are currently measuring a degenerate path.*
2. **Add the `state.py` writer lock (H6).** Guard every `self._writer` access, or route
   migration/checkpoint work through the transaction queue so only the writer thread touches the
   connection.
3. **Scope the learnings store (H8).** Add `org_id` as a real column with a migration, filter on
   it plus `user_id`/`scope` in both SQL stores, and escape `</maistro:corrections>` in the
   rendered block. Add a property test asserting a learning cannot terminate its own block.
4. **Add a `try/finally` around `handle()` and widen the strategy catch (H9).** Catch `Exception`
   in `_run_strategy` (re-raising `asyncio.CancelledError`) and guarantee `trace.end()` and
   `_persist_run` run on every path. Today a provider outage — the single most likely production
   failure — silently loses the trace and the run record.
5. **Route hive-conductor's chat loop through the core security objects (H10).** The immediate
   half is one line — change the dispatch default from `_tool_poll_jira` to `None` and return a
   structured error. The structural half is passing inbound text through `gate.process_input` and
   wrapping `_execute_tool` in `sentinel.pre_call`/`post_call`; `adapters/maistro_core.py:160-161`
   already has both objects in hand.
6. **Declare hive-conductor's dependencies (H11).** Add `maistro-design`/`maistro-rsi`/
   `maistro-evolve` to `requirements.txt` and the root `[project.dependencies]`; guard the
   `design` router import; give hive-conductor a `pyproject.toml` so it enters the uv workspace.
7. **Repair the mutation and quality gates (M4, M5).** Make the mutation job consume its own
   changed-file list and use `github.base_ref`; wire `check-radon-baseline.py` or delete it;
   author `tests/fitness/` (import-boundary assertions per ADR-019/068 are the obvious first
   three) and remove the directory guard so a deleted suite fails loudly.

### Horizon 3 — Strategic (Stronghold preparation)

1. **Unify the duplicated type hierarchies (M9).** One `AuditEntry`, one `AuditLog`, one
   `LLMClient` — today there are two, two, and three respectively. Do this *before* wiring any
   SQL audit log, or the wiring will silently lose audit records.
2. **Wire or explicitly retire the Postgres backend (M11).** Either add `_wire_pg_backend()` and
   make an unsupported scheme raise, or mark the 1,097 LOC of `pg_*` stores as unwired so nobody
   assumes durability. The silent in-memory fallback is the dangerous middle state.
3. **Tidy `create_container`'s defaults (M10).** The protocol seam is adequate; the 26
   `None`-defaulted `type: ignore` fields are not. Backfill them in `__post_init__` or make them
   genuinely optional.
4. **Decide the core/product boundary for `maistro/cli/` and `maistro/integrations/`.** Verifier
   downgraded these to Low — the CLI is behind the `tui` extra and integrations has no production
   importer — but both are product-specific code shipped in the product-agnostic library, and
   Stronghold has no seam to disable them. Cheapest fix: move behind extras and add ADR-019 rows.
5. **Consolidate hive-conductor's four reimplemented subsystems** (scheduler, HA tools,
   credentials, pg stores). For each, pick the winning copy, replace the other with a thin
   adapter, and add a regression test at the seam.
6. **Retire `maistro-canvas/canvas/tool.py`** (922 LOC, zero importers, contains L3) in favour of
   `executor.py` + `compositor.py` + `store.py` + `routes.py`. A capability-parity audit
   (Appendix C) shows this is *not* a straight deletion: nine of its twelve capabilities are
   already reimplemented better, but three did not carry over. Sequence:
   1. **Decide `upload` and `duplicate`** — the two genuinely missing actions. Both are small
      additions to `store.py` + `routes.py` if wanted (`LayerRecord.image_path` and `store_blob`
      already exist, so `upload` is a route and a wiring line, not new infrastructure). If not
      wanted, say so in the ADR from step 3 — the point is that the decision is recorded rather
      than made silently by a deletion.
   2. **Confirm the character-reference data question is empty.** It almost certainly is: no
      migration anywhere creates `character_references` (the `CREATE_TABLE_SQL` at `tool.py:625`
      is a module constant annotated "migration managed separately", and no such migration
      exists), and `save/load/list_character_reference` have zero callers. The only residual risk
      is an operator having run that SQL by hand against a real database, since the functions
      accept an injected `db_pool`. One `SELECT count(*)` settles it.
   3. **Write the ADR** recording that `AssetSheet` + `generate_sheet`/`regenerate_sheet`
      (ADR-039) supersedes `CharacterReference`, and that the two models are not
      wire-compatible — `AssetSheet` is a superset (sockets, skin sets, world-style inheritance,
      pose geometry, scene-graph parenting, revisions) with no import path from the old shape.
   4. **Delete the module**, after grepping the Da Vinci agent definition
      (`packages/maistro-canvas/agents/davinci/`) for a dynamic load by name — a Python-import
      grep will not catch a YAML-declared tool reference.

   Effort: S if `upload`/`duplicate` are dropped, M if they are ported.
7. **Write one ADR fixing the RSI dependency direction.** The shipped API process currently
   imports a self-modification toolchain (`services/rsi.py:138`); `Dockerfile.rsi-runner` implies
   RSI should stay out-of-band. Nothing records which is intended.

---

## Appendix A — Refuted and downgraded findings

Recorded so they are not re-raised. Two findings were **refuted outright**:

**A1 — "Canvas Express server queries tables no migration creates" (was Critical): REFUTED.**
The premise is false — there are two different databases. `alembic.ini:3` targets
`postgresql+asyncpg://mcp:mcp@localhost:5441/mcp_orders` (matching the compose service, port
`5441:5432`, `POSTGRES_DB: mcp_orders`), while `server.js:8-11` targets port `5440`, database
`canvas_studio` — a pre-existing external instance whose `key TEXT PK, data JSONB` shape is
documented in `frontend/SPEC.md:132`. The identically-named `generation_attempts` tables are
unrelated. *Verified independently by the orchestrator.*

**A2 — "Streaming chat kills the SSE response when a tool raises" (was High): REFUTED.**
`routes/chat.py:108-114` wraps `async for event in run_chat_completion_streaming(...)` in
`try/except Exception` and yields a terminal `{"type":"done","content":"Error: …"}` frame, which
`Chat.tsx:333-334` renders. The `(no response)` branch is unreachable on tool failure.
*Verified independently by the orchestrator.*

**Downgraded:**

| Finding | Was | Now | Mitigating fact |
|---|---|---|---|
| A3 — `tenant_id` in core violates ADR-068 | High | Low | `AgentSpec.tenant_id` is verbatim what `ADR-004:107` specifies; the `skills/catalog.py` half does contradict ADR-035/068 but `SkillCatalog` has zero non-test importers |
| A4 — `AuthContext` lacks `org_id` | High | Low | Omission is deliberate and documented; no code writes a non-empty `org_id`, so no cross-org leak is reachable — the isolation is inert, not broken |
| A5 — core ships homelab/app-client code | High | Low | `maistro.cli` is behind the optional `tui` extra and cannot import without opt-in; `maistro.integrations` has no production importer |
| A6 — `/health/ready` always ready | High | Medium | Real defect, but the LB contract is served by maistro-server's health endpoint, which does return 503; hive's consumers test HTTP 200 only, and in-memory stores are this app's documented default |
| A7 — canvas fetches lack timeouts | High | Medium | The nine bare fetches are real but proxy to a localhost sidecar whose paid Lulu calls are bounded (`lulu/client.py:63,94,186`), and all nine are wrapped in try/catch returning 502 |
| A8 — two divergent canvas engines | Medium | Low | `execute_canvas` is unreachable — zero callers, not exported |
| A9 — `create_container` has no DI seam | Critical | Medium | Protocol-typed dataclass fields make constructor injection a valid third path; ADR-019 names protocols as the seam |
| A10 — Sentinel/Pg audit incompatibility | High | Medium | Wrapped in `except Exception` → silent audit loss, not a crash; neither SQL audit log is wired |
| A11 — `PersistedStore` read-after-write race | High | Low | Shipped consumers are write-through caches reading from an in-memory dict; `list_all` is called only at startup, after an explicit `state.flush()` (`foundation.py:91`) |
| A12 — Trigger cooldown check-then-act | High | Low | The only trigger registered outside tests is an event recorder where an extra fire appends a distinct row — the desired behaviour; every cooldown-sensitive recipe is an unused template |
| A13 — Reactor spawns unbounded handler tasks | High | Low | `_handlers` is empty in every shipped configuration (`register_source` is never called outside tests) and nothing calls `emit()`; the started Reactor only reports liveness to `/health` |
| A14 — Reactor `stop()` use-after-close | High | Low | `state_submit`/`state_query` are guarded by `if self._state_conn:` and `stop()` nulls it in the same non-yielding block, so a resumed orphan no-ops; residual impact is a dropped shutdown write |

## Appendix B — Corrections to the review's own inputs

The fleet corrected itself in four places; recorded for method credibility.

- **"maistro-registry has 0 tests"** — false, and it originated in my own scout brief. Its tests
  live at `tests/tools/registry/`, outside the package, and `registry.yml:46` runs them.
- **"CLAUDE.md's Conventions section says 'No org_id in core'"** — false. Convention 7
  (`CLAUDE.md:181`) says the opposite; the stale text is at `CLAUDE.md:42`.
- **"maistro-rsi is a leaf, imported by nothing"** — false. `hive-conductor/backend/services/rsi.py:138`
  imports it, making a self-modification toolchain a transitive dependency of the shipped API.
- **Most "UNTESTED" subpackage rows in the coverage map were grep artifacts** — those
  subpackages have suites importing through the package `__init__`. The only genuinely untested
  module in maistro-core is the empty `scheduler/` placeholder. No test-writing work should be
  funded against that list.


## Appendix C — Canvas engine capability parity (`tool.py` → new engine)

Commissioned to answer "does everything the legacy engine does exist in the new files, only
better?" before authorising the deletion in Horizon 3 item 6. Answer: nine of twelve, yes and
better; three did not carry over.

### Reimplemented, and better

| `tool.py` capability | Replacement | Improvement |
|---|---|---|
| `generate` (`:339`) | `JobAction.GENERATE` → `executor.py`, `POST /{id}/layers/{lid}/generate` | Durable job records with status, multi-variant + `accept_variant`, cancellation, Warden scan, model registry, `_sanitise_error` (`executor.py:75`) |
| `refine` (`:400`) | `JobAction.REFINE` | Same job machinery; rejects refine on an imageless layer (`executor.py:191`) |
| `reference` (`:435`) | `JobAction.REFERENCE` | Same |
| `composite` (`:470`) | `PilCompositorService.composite` (`compositor.py:244`), `POST /{id}/composite` | PIL work offloaded via `asyncio.to_thread`; PNG/WebP/JPG encoders (`:212-224`); persisted history (`save_composite`, `latest_composite`) |
| `text` (`:501`) | `JobAction.TEXT` + `_render_text_layer` (`compositor.py:109`) | Typed `TextConfig` instead of loose kwargs |
| `list_layers` (`:566`) | `store.list_layers` + `GET /{id}/layers` | Postgres-backed instead of a module-level process dict |
| `transform` (`:573`) | `store.update_layer` + `_transform_layer_image` (`compositor.py:63`) | Adds `normalise_rotation`, opacity/blend/visible/locked, and `reorder_layers` with z-index collision detection (`store.py:495-498`) |
| `delete` (`:590`) | `store.remove_layer` + `DELETE` route | Transactional |
| `get_or_create_canvas`/`destroy_canvas` (`:78`,`:89`) | `create_canvas`/`get_canvas`/`update_canvas` + delete route | Durable, org-scoped through `_require_canvas(store, canvas_id, auth.org_id)`; `_MAX_LAYERS` ceiling enforced under `SELECT … FOR UPDATE` (`store.py:266-275`) |

The new engine also adds capabilities the legacy one never had: job cancellation, variant
acceptance, canvas export, model listing, blob storage, and composite history.

### Not carried over

| Capability | Status | Notes |
|---|---|---|
| `upload` (`tool.py:528`) | **No replacement** | `routes.py:419-439` `add_layer` accepts geometry only — no image bytes, no base64, no `UploadFile`; no upload route exists anywhere in `routes.py`. Primitives are present (`LayerRecord.image_path` at `types.py:199`, `store.store_blob` at `store.py:665`), so this is a wiring gap, not missing infrastructure. Also the action broken by L3. |
| `duplicate` (`tool.py:595`) | **Absent** | Grep for "duplicate" across `store.py`/`routes.py`/`executor.py`/`asset_*.py` returns only unrelated z-index collision messages. |
| Character references (`tool.py:611-816`) | **Superseded by a different model** | `AssetSheet` + `generate_sheet`/`regenerate_sheet` (ADR-039, `layers.py:226`) is a strict superset — sockets, skin sets, world-style inheritance, pose geometry, scene-graph parenting, revisions — but is not wire-compatible with `CharacterReference` (`tool.py:611`), and there is no import path between them. The `character_references` table is created by no migration in the repo and the three functions have zero callers, so the data-migration risk is near zero (see Horizon 3 item 6, step 2). |
