# maistro-engine v1.0.0 Release Plan

> **Status:** Active — feature freeze in effect.
> **Form:** This document is the release plan of record. Each `##` work item below is written
> as a ready-to-file GitHub issue (title / context / tasks / acceptance criteria / dependencies).
> GitHub Issues are currently disabled on this repository; when enabled, file one issue per item,
> one umbrella tracking issue linking them all, and a `v1.0.0` milestone.

## Definition of v1

- **(a)** `v1.0.0` annotated git tag on `main` + GitHub release with artifacts.
- **(b)** `maistro-core`, `maistro-canvas`, `maistro-evolve`, `maistro-rsi` (+ `maistro-bootstrap`
  as rsi's dependency) published to PyPI.
- **(c)** hive-conductor (Agent Conductor) deployable end-to-end from a clean machine:
  installer → wizard → compose → authenticated DAG execution with a real model call.
- **(d)** Evolve + RSI integrated into the Conductor UI as **first-class v1 features** — not
  experimental, not cut.

## Why now / starting state

`develop` is 55 commits ahead of `main` with a conflict-free merge path, but no release machinery
exists: zero git tags ever, no CHANGELOG, no release/publish workflow, every package hardcodes
`0.1.0` (root `0.0.0`) with no version single-source, installers clone a branch rather than a tag,
and CI builds images it then discards. Five open PRs (#266–#270) carry the codebase-review
remediation and the installer; 28 stranded branches need disposition; ~616 in-tree tests never run
in CI; six security-audit items from the June audit remain open; and several features are
advertised beyond what the code does (keyword scorers named after real benchmarks, specs marked
Implemented over `NotImplementedError` code).

## Workstream structure and ordering

```
A. Freeze & Triage ──────────────┐
        ├──> B. Security Must-Fix ───────────┐
        ├──> C. CI & Gating ─────────────────┤
        ├──> D. Truth-in-Advertising & Cuts ─┼──> G. Stabilize, Promote, Tag, Publish
        ├──> E. Release Engineering ─────────┤
        └──> F. Conductor Deployability ─────┘
```

| WS | Name | Depends on | Exit criterion |
|---|---|---|---|
| **A** | Freeze & triage | — | All 5 open PRs dispositioned; 0 stranded branches without an explicit decision. Nothing lands on `develop` after A closes except items in this plan. |
| **B** | Security must-fix | A (#270 first) | All 6 audit items + the 4 unauthenticated surfaces from PR #266 fixed; no **protected application** route reachable without auth in the default deployment. Deliberately public endpoints (health/liveness/readiness — also used by compose and image health checks — plus setup, login/register, and docs, per `backend/middleware/auth.py`) are enumerated in an approved-public list, and anything not on that list requires auth. |
| **C** | CI & gating | A (#267/#268 first) | All ~616 orphaned tests execute in CI; coverage gate honest; required status checks configured on `develop`/`integration`/`main`; `registry.yml` covers `develop`. |
| **D** | Truth-in-advertising & cuts | A (#266 is the evidence base) | No doc/spec/README claim contradicts the code; cut-list items deleted, demoted, or deferred with a tracking entry. |
| **E** | Release engineering | A; E5 needs E1 | `release.yml` exists and dry-runs green on a `v1.0.0-rc1` tag; versions single-sourced; CHANGELOG drafted; installers pin to tag. |
| **F** | Conductor deployability | A (#269 first); B5 | Clean-machine install → compose → authenticated DAG execution, including the Evolve/RSI loop driven from the Conductor UI. |
| **G** | Ship | **all of B–F** | `v1.0.0` on `main`; PyPI live; images pushed + cosigned; fresh-machine install from the tag verified. |

**Calendar (one maintainer, ~4 weeks):** W1 = A + B complete, E1/E2 started. W2 = C, D, E
complete. W3 = F complete, promote to `integration`, `v1.0.0-rc1` dry-run + soak. W4 = release day.

**Freeze rule:** any PR not tracked by this plan does not merge until `v1.0.0` is tagged.
Stabilization/deployability fixes for tracked items are allowed; new features are not.

---

# Workstream A — Freeze & triage

## A1 — Disposition the 5 open PRs under the feature freeze (S)

**Context:** PRs #266–#270 all target `develop`, none conflicted. The freeze needs an explicit
ruling per PR.

- [ ] Merge #268 (CI gates batch 1: orphaned suites, coverage 20→95, arch-fitness suite,
      mutation `base_ref` fix) — 11/11 green; merge first, it is the foundation of WS-C.
- [ ] Merge #267 (tiered mutation gate) after #268.
- [ ] Merge #266 (codebase review + remediation plan) — docs only; evidence base for WS-B/WS-D.
- [ ] Finish and merge #270 (security wiring batch 2: Sentinel permission table, strike ladder,
      Warden skill-import scan, constant-time key compares) — currently draft; this is WS-B work.
- [ ] Merge #269 (curl→wizard→compose→first-model-call installer). **Ruling: this is
      deployability (v1 criterion (c)), not a feature** — the installer is the shipping story.

**AC:** zero open PRs predating the freeze; merge order recorded here.
**Blocks:** B*, C*, F*.

## A2 — Triage the 28 stranded remote branches (S, dep A1)

**Context:** 28 remote branches carry unmerged commits with no PR. 13 are fully contained in
`develop` (residual deltas of squash-merged work). Genuinely unlanded: `feat/rsi-v3-unified`
(+4545), `feat/rsi-promotion-review` (+4322), `fix/p2-installer-bugs` (+4001),
`claude/rsi-durable-memory` (+1860), `claude/mac-installer-x1sezm` (+1553).

- [ ] Delete the 13 fully-contained branches (spot-check `git merge-tree` shows no unique hunks).
- [ ] Retire the 3 RSI mega-branches: record the supersession rationale in the umbrella tracking
      issue (bare branches have no close/comment mechanism — the issue is the ledger), then
      delete the branch refs: *superseded by the 07-26/27 RSI rewrite on develop; anything still
      wanted gets a fresh spec post-v1.* Do **not** attempt to land — they predate the rewrite
      and conflict heavily. (Evolve/RSI being v1 scope does not change this: v1 ships the
      rewritten RSI, not the pre-rewrite branches.)
- [ ] Diff `fix/p2-installer-bugs` + `claude/mac-installer-x1sezm` against #269; cherry-pick only
      installer bug fixes not subsumed (deployability, allowed under freeze); close both.
- [ ] Delete remaining residual branches.

**AC:** `git branch -r` contains only `main`, `integration`, `develop`, and branches for open
tracked work.

## A3 — Freeze policy + PR template + tracking hygiene (S)

- [ ] Enable GitHub Issues on the repo; file this plan as milestone `v1.0.0` + umbrella issue +
      one issue per item here.
- [ ] Pin the freeze rule (what merges: tracked items only; where: `develop`).
- [ ] Add minimal `.github/PULL_REQUEST_TEMPLATE.md` with a "v1 tracked item? / workstream?"
      checklist to stop freeze leaks.

**AC:** plan converted to issues; template merged; policy pinned.

---

# Workstream B — Security must-fix

## B1 — Fix canvas auth bypass + hardcoded frontend DB credential (S)

**Context:** `packages/maistro-canvas/src/maistro_canvas/auth.py:28-46` — `get_current_user`
ignores `api_key` and returns an admin `CurrentUser`, so every canvas route is unauthenticated
admin. Canvas POC frontend `server.js:10` hardcodes a Postgres credential.

- [ ] Validate the key for real (~15 lines per the June audit); constant-time compare (reuse
      #270's `secret_equal` helpers).
- [ ] Regression tests: no/bad key → 401; valid key → scoped user, not admin.
- [ ] `server.js`: credential from env, fail fast if unset; rotate the committed value.

**AC:** no canvas route returns 200 unauthenticated; secret scan clean; tests in CI.

## B2 — Make webhook signature verification fail closed (S)

**Context:** `packages/maistro-server/src/maistro_server/api/webhooks.py:111-115, 202-206` —
GitHub and CI webhook signature checks are skipped with a warning when the secret is unset.

- [ ] Unset secret → 503/501 + log; never process the payload.
- [ ] Tests: unset-secret, bad-signature, good-signature.
- [ ] Document the required env vars in deployment docs (feeds F2/E5).

**AC:** no code path processes a webhook body without a verified signature.

## B3 — Stop mounting docker.sock by default (S)

**Context:** `docker-compose.yml:41` mounts `/var/run/docker.sock` into the engine container by
default — container escape equals host root.

- [ ] Remove from the default service; move behind an explicit opt-in override/profile with a
      loud comment.
- [ ] Verify `deploy/docker-compose.prod.yml` and #269's generated compose don't reintroduce it.
- [ ] Note in SECURITY/deployment stance.

**AC:** `docker compose config` on default + prod profiles shows no docker.sock mount.

## B4 — Kill demo connector fixtures fallback + 502 detail leak (S)

**Context:** `packages/maistro-core/src/maistro/skills/connectors.py:94-153` serves fixtures named
`code-executor-unlimited` / `credential-helper` / `admin-override` on *any* HTTP error — a downed
registry silently offers maximally-privileged fake skills. `api/chat_completions.py:187` echoes
upstream exception text in 502 bodies (the streaming branch is already sanitized).

- [ ] Delete the fixtures from the runtime path outright (anything needed for tests moves into
      the test tree); HTTP failure → error, never fixtures. No runtime flag — a demo mode that
      serves privileged-looking fake skills is not worth the footgun.
- [ ] 502 path: mirror the streaming branch's sanitization; detail to server logs only.
- [ ] Tests for both.

**AC:** registry outage yields an error, not skills; 502 body contains no upstream exception text.

## B5 — Authenticate hive-conductor WS routes incl. the DAG-executing route (M, dep A1)

**Context:** PR #266 identified four unauthenticated surfaces, including hive-conductor WebSocket
routes — one of which executes a DAG. Hard prerequisite for WS-F.

- [ ] Enumerate the 4 surfaces from #266; add auth (token on WS handshake, consistent with #270's
      key handling) to each.
- [ ] DAG-execution route additionally checks an execution permission, not just identity.
- [ ] Tests: unauthenticated WS connect rejected; authenticated round-trip green (feeds C2/F4 e2e).

**AC:** zero unauthenticated surfaces remain from #266's list; conductor e2e passes with auth on.

---

# Workstream C — CI & gating

## C1 — Run all orphaned test suites in CI (~616 tests) (M, dep A1/#268)

**Context:** never executed by any workflow: `packages/maistro-design/tests` (156 — mypy'd, never
run), root `tests/` (403 — only `tests/tools/registry` runs, and only on doc-path PRs),
`packages/maistro-turing/backend/tests` (26), `packages/hive-conductor/tests` (31). #268 wires
some of this; this item closes the remainder.

- [ ] Post-#268 gap audit; wire each remaining suite into `ci.yml`/`quality.yml`.
- [ ] Fix or skip-with-tracking-link tests that fail on first real run (expect some).
- [ ] Root `tests/` runs on every PR, not just doc paths.

**AC:** every orphaned suite appears in a CI invocation; the expected inventory is generated with
`pytest --collect-only -q` per suite (node IDs — not static `def test_` counts, which
parametrization expands) and CI-collected node IDs match it (± documented skips); all suites
green on `develop`. **Blocks:** C3, G1.

## C2 — Honest coverage gate + frontend tests in CI (M, dep C1)

**Context:** `quality.yml` gate was `--fail-under=20` while labelled 95, measuring maistro-core
only (#268 raises it). No frontend test runs anywhere (canvas vitest, conductor Playwright e2e
exist unrun). Python-version messaging is inconsistent (`.python-version`=3.13, pyprojects
`>=3.12`, ruff target py311).

- [ ] Verify #268's 95 gate holds after C1; extend coverage measurement to the publish set.
- [ ] Add canvas vitest + conductor Playwright jobs (Playwright may start non-blocking; blocking
      by G1). Include the F4 RSI-page e2e once it exists.
- [ ] Align Python floors: 3.12 floor / 3.13 CI / ruff target py312.

**AC:** coverage number in CI equals the number claimed in docs; frontend jobs green.

## C3 — Configure required status checks + fix workflow branch triggers (S, dep C1+C2)

**Context:** ADR-095's required-checks acceptance criterion is unchecked on all tiers;
`registry.yml` push triggers omit `develop` (and list stale `research/pm-fleet-poc`).

- [ ] Branch protection per ADR-095: `develop` (0 approvals + required checks), `integration`
      (0 approvals + required checks + formal-conformance), `main` (1 approval + required checks);
      linear history, squash/rebase only.
- [ ] Add `develop`/`integration` to `registry.yml`; audit the other workflows' branch filters
      for `integration`.
- [ ] Check off the ADR-095 ACs.

**AC:** a red PR is mechanically blocked on every tier; ADR-095 ACs checked.

---

# Workstream D — Truth-in-advertising & cuts

## D1 — [CUT LIST] Remove or demote non-v1 surface area (L, dep A1)

**DELETE from the tree:**
- [ ] `maistro.scheduler` — 0-byte package (ADR-046 still Proposed). Delete; mark ADR-046
      Deferred/Rejected. (Distinct from `maistro.scheduling`, which is real and ships.)
- [ ] `apps/maistro-gateway-node-flutter` — README-only shell (SPEC-179 → Deferred).
- [ ] `maistro-turing` Astro frontend (0 tests). The turing *library* ships; the turing backend
      stays only if its 26 tests pass under C1.
- [ ] The 13 fully-contained remote branches (executed in A2; recorded here).

**MARK EXPERIMENTAL (ships, no stability contract, not on PyPI):**
- [ ] Canvas frontend POC (a parallel product with its own DB inside a library package) — move
      under an experimental banner and exclude from the canvas wheel
      (`[tool.hatch.build]` excludes); not part of the v1 API surface.

**Evolve + RSI are explicitly NOT cut and NOT experimental — they are v1 scope** (see F4/D3).

**DEFER to v1.1 (each gets a tracking entry via D5):**
- [ ] Canvas Studio /v2 cutover (server mounts v2; frontend not migrated).
- [ ] maistro-server canvas publish/export 501s.
- [ ] Task-queue persistence (ADR-018); canvas background job runner (SPEC-203).
- [ ] K8s/Helm deployment (ADR-081 remainder) — v1 = the four DEPLOYMENT-STANCE compose profiles.
- [ ] SPEC-184..188 capabilities/self-repair chain (Proposed; doc claim removed in D4).
- [ ] Evolve *research* specs (GEPA/TextGrad/island/OPRO/Reflexion) + contract-backfill specs —
      enhancements, not the shipping tournament.

**AC:** every line has a merged PR, a closed branch, or a v1.1 tracking entry.

## D2 — Correct spec/ADR statuses that contradict code (S) — done, #290, PR #318

- [x] SPEC-183 (OAuth identity linking; `auth/oauth.py:519` is a Phase-2 stub) → status corrected
      `Implemented` → `In Progress` with a shipped-subset note (Phases 1-2 real and tested;
      Phase 3 hive-conductor routes and Phase 4 audit wiring are follow-up).
- [x] SPEC-070226-b624 (LLMJudgeComparator; `ensemble.py:208` raises NotImplementedError) →
      status corrected `Implemented` → `In Progress` with an implementation-status note.
- [x] Deduped the 3 duplicate spec pairs (shared-tool-call-cache, canvas-tool-action-contracts,
      skill-fixer-rule-pipeline) — the stale `SPEC-070126-*` trio marked Superseded by their real
      `SPEC-062126-*` counterparts; ADR-INDEX regenerated (also gained ADR-076's previously-missing
      row).
- [x] ADR-076: recorded its actual state — content negotiation is **not implemented** (the only
      negotiation code is canvas-specific/v2; business routes are mounted under the `/v1` path);
      its ACs stay unchecked and implementation is deferred to v1.1, cross-linked to
      `KNOWN-GAPS.md` (see E4 for what the release notes may truthfully claim).

**AC:** registry gate green; no spec marked Implemented whose named feature raises
NotImplementedError. Verified: `maistro_registry.cli lint . --strict` — 0 errors.

## D3 — Rename evolve pseudo-benchmarks honestly; evolve/rsi ship as v1 (M) — done, #291, PRs #327 + #329

**Context:** `packages/maistro-evolve` scorers named `swebench` / `gaia` / `tau_bench` / `osworld`
/ `ifeval` / `bfcl` / `ragas` / `terminalbench` are keyword-overlap heuristics, not the named
benchmarks, and drive 0.65 of fitness weight (SPEC-202 Proposed). Evolve+RSI are **v1 features**,
which makes honest naming more important, not less: shipping fake scorers under real benchmark
names as a *supported* feature is the single worst credibility exposure in the tree.

**Correction to the context above (verified against the code in #327):** the premise that all
eight are "keyword-overlap heuristics" was significantly overstated. `swebench`/`terminalbench`
run real sandboxed execution and assert a real outcome; `ifeval` runs real per-instruction rule
verification. Only `ragas` is primarily keyword overlap. `bfcl`/`gaia`/`tau_bench` are
structurally-checked but each carries a real text-mention or fuzzy-substring fallback that
materially weakens it. What *is* uniformly true — and what the AC actually needed — is that none
of them run the official corpus/harness. The fix reflects that reality rather than the original
blanket claim.

- [x] Scorers renamed — to `proxy_*` rather than `heuristic_*`, because "heuristic" would have
      been its own inaccuracy for the five non-heuristic scorers (see correction above).
      `EvalResult.benchmark` values, `PROXY_BENCHMARKS`/`RSI_BENCHMARKS` registry keys, fitness
      hard-gate keys, `EvalWeights` fields, and `cycle`/`runner` default lists all moved in
      lockstep (#329). Per-benchmark docstrings stating exactly what each one does — including
      the degenerate cases — landed in #327. Real benchmark adapters remain v1.1 (SPEC-202).
- [x] v1 stability statement for both packages (#327, `__init__.py` of each). Notes the
      unresolved ADR-088 governance conflict rather than silently overriding an Accepted ADR.
- [x] Both already named in E3's PyPI publish set below; F4/#303 tracks the supported-surface
      integration.

**AC:** no identifier or docstring claims a real benchmark is being run; both packages carry a
stability statement. ✅ Verified: repo-wide grep for the 8 bare identifiers returns zero hits
outside prose about the real benchmarks; 955/955 tests pass across both packages.

## D4 — Documentation accuracy sweep (M, dep D1+D2)

- [ ] README/CLAUDE.md ADR counts (119 exist; docs say 57/64); remove deleted `src/maistro/`
      references; fix broken ADR links (README ADR-042, CONTRIBUTING → ADR-095); replace the
      superseded branch-model description; fix the bootstrap "WIP stub" label (it is a working
      CLI); remove/fix 404 private-repo links in ROADMAP.md.
- [ ] Remove the CLAUDE.md claim that SPEC-184/188 capabilities self-repair is shipped (chain is
      Proposed).
- [ ] Classifier docs: "keywords → LLM → complexity" → describe what exists (LLM phase is a
      Phase-2 comment at `classifier/engine.py:84`) or implement in v1.1.
- [ ] Verify every README claim against the tree: *if it can't be demoed from the README, delete
      the sentence.*

**AC:** link check clean; capability lists match Implemented specs only.

## D5 — KNOWN-GAPS.md — release-notes limitations input (S)

- [ ] Enumerate shipped-but-degraded behaviors with a v1.1 tracking entry each: in-memory task
      queue (restart loses tasks, ADR-018), canvas jobs never advance without a runner
      (SPEC-203), canvas publish/export 501s, conductor degraded modes (F3), Canvas Studio /v2,
      ADR-076 content negotiation unimplemented (`/v1` mount only — see D2/E4).
- [ ] Feed verbatim into CHANGELOG "Known limitations" (E4).

**AC:** every shipped-but-degraded behavior appears here or is fixed.

---

# Workstream E — Release engineering

## E1 — Single-source version 1.0.0 across the monorepo (M)

**Context:** 11 packages hardcode `0.1.0`, root `0.0.0`; only bootstrap+registry export
`__version__`; a bump is ~13 hand-edits with nothing checking agreement.

- [ ] `VERSION` file + `scripts/bump_version.py` rewriting all pyprojects + `__version__` sites;
      CI consistency check (quality.yml + release.yml guard).
      *Rejected:* hatch-vcs (zero-tag history, 11 packages sharing one tag — revisit v1.1);
      regex version sources outside package dirs (breaks sdists).
- [ ] Add `__version__` (via `importlib.metadata`) to the 9 packages missing it.
- [ ] Run the bump: everything → `1.0.0`.

**AC:** `scripts/bump_version.py 1.0.0` touches all version sites; consistency check green.
**Blocks:** E2, E3, F1, G2.

## E2 — Fix dependency bounds + uv workspace table (M, dep E1, F1)

**Context:** inter-package deps (`maistro-core>=0.1.0` etc.) have never resolved from a real
index; 8 of 11 packages have uncapped third-party upper bounds (core/canvas are the properly
capped template); no `[tool.uv.workspace]` members table exists.

- [ ] Inter-package bounds → `>=1.0.0,<2` (maintained by the E1 bump script).
- [ ] Cap uncapped third-party deps in the 8 packages; regenerate `uv.lock`.
- [ ] Add `[tool.uv.workspace]` members = `packages/*` (incl. hive-conductor once F1 lands).

**AC:** `uv lock` clean; in the E3 dry-run, `pip install maistro-rsi==1.0.0` from an index
resolves `maistro-core`/`maistro-evolve`/`maistro-bootstrap` at `1.0.0`.

## E3 — Create release.yml — tag-triggered build/publish pipeline (L, dep E1+E2)

**Context:** no release workflow exists; ci.yml builds wheels and images and discards them; the
cosign step is inert; the only image push is manual `deploy.sh` with git-SHA tags.

- [ ] `.github/workflows/release.yml`, `on: push: tags: ['v*']`.
- [ ] `guard`: tag commit is ancestor of `main` (rc: `integration`); prerelease-aware version
      check — a final tag `vX.Y.Z` must equal `VERSION` == every package version exactly, while
      an rc tag `vX.Y.Z-rcN` must have base version `X.Y.Z` == `VERSION` (packages stay at the
      final version; the rc suffix lives only in the tag); CHANGELOG has a heading matching the
      base version.
- [ ] `wheels`: sdist+wheel for the publish set — **maistro-core, maistro-canvas, maistro-evolve,
      maistro-rsi, maistro-bootstrap**; `twine check`; clean-venv install+import smoke.
- [ ] `pypi`: trusted publishing (OIDC) gated by a `release` GitHub environment approval.
      Pre-work: register the five names on PyPI; configure trusted publishers.
- [ ] `images`: build `maistro-engine` + `hive-conductor`; push to ghcr.io tagged `v1.0.0`,
      `1.0`, `latest`; **cosign sign the pushed digest** (keyless) + in-workflow verify; retire
      or rewire `deploy.sh` onto this path.
- [ ] `github-release`: release from tag; body = CHANGELOG section + ADR-076 API statement;
      artifacts = wheels, sdists, SHA256SUMS, syft SBOMs, installers.
- [ ] `v*-rc*` tags → TestPyPI + `-rc` image tags only (no `latest`) — enables the G1 dry-run.

**AC:** a `v1.0.0-rc1` tag produces TestPyPI packages, rc images, and a prerelease GitHub release
end-to-end with zero manual artifact handling.

## E4 — CHANGELOG.md + v1.0.0 release notes (S, dep D3+D5)

- [ ] Root `CHANGELOG.md` (Keep-a-Changelog); single curated `## [1.0.0]` entry by area — core,
      canvas, server, conductor, **evolve+RSI as headline features** (with the D3
      heuristic-fitness caveat), security hardening, CI.
- [ ] "Known limitations" = D5 verbatim.
- [ ] **API-version statement (required, and honest):** the stable HTTP surface in v1.0.0 is the
      `/v1` route mount; ADR-076's content-negotiation scheme
      (`Accept: application/vnd.maistro.vN+json`) is **not yet implemented** and is deferred to
      v1.1 (D5 entry) — the release notes must describe the mount, not claim negotiation the
      server doesn't perform; the API version axis remains independent of the package version.
- [ ] Point to `docs/product/DEPLOYMENT-STANCE.md` as the supported-profile matrix.

**AC:** release.yml guard finds the heading; notes reviewed against D4/D5.

## E5 — Pin installers to release tags (S/M, dep A1/#269, E3)

**Context:** `get.sh`/`install.sh`/`get.ps1` clone branch `main`; "install v1.0.0" is not
expressible.

- [ ] `MAISTRO_VERSION` env / `--version` flag; default = latest release tag via GitHub API;
      fetch the tag (or release tarball), not a branch.
- [ ] Wizard/compose output pins matching `vX.Y.Z` image tags (with E3).
- [ ] Keep `--channel dev` → `develop` for contributors.

**AC:** `MAISTRO_VERSION=v1.0.0-rc1 ./get.sh` on a clean machine installs exactly the rc.

## E6 — ADR: release & versioning process (S, dep E1–E5)

- [ ] New ADR extending ADR-095 past `main`: lockstep monorepo versioning; annotated `vX.Y.Z`
      tags on `main` only (rc exception: `integration`); release.yml as the sole publish path;
      the `release` environment approval as the publish gate; hotfix path (branch from tag →
      main → back-merge); rc conventions.

**AC:** ADR Accepted; registry gate green.

---

# Workstream F — Conductor deployability

## F1 — hive-conductor pyproject.toml; join workspace + wheel gate (M, dep E1) — done, #300, PR #331

**Context:** `packages/hive-conductor` is a bare `requirements.txt` + Vite frontend —
unpackageable, outside the wheel-imports gate, and a second unlocked dependency resolution.

- [x] `packages/hive-conductor/pyproject.toml` (hatchling, `0.9.0` from root `VERSION`);
      requirements.txt translated with bounds and its load-bearing comments preserved
      (the `httpx2`/Starlette note, the `regex`/Warden-ReDoS note); test-only deps moved to a
      `dev` extra. **`maistro-core` is `>=0.9.0,<2`, not the `>=1.0.0,<2` written above** —
      nothing in the repo is at 1.0.0 yet, so that bound does not resolve today. Flagged
      in-file to tighten at tag time.
- [x] `[tool.uv.workspace]` members added to the root pyproject — it had **none**, only
      `[tool.uv.sources]` path entries, so a package file alone would not have created
      membership. Sources converted to the canonical `{ workspace = true }` form and completed
      for every member (uv requires a source entry for any member another member depends on;
      `maistro-rsi` → `maistro-evolve` is the live case). Enrolled in wheel-imports. Not in the
      PyPI set.
- [x] Frontend build artifacts excluded from the wheel — it ships `backend/` sources only.

**AC:** the package builds; wheel-imports covers it; `uv.lock` includes it. ✅ All 10 package
wheels build; `verify-wheel-imports.py` exits 0; `uv lock --check` clean (198 packages);
hive-conductor present in `uv.lock`.

**One caveat recorded deliberately:** the wheel builds but is **not importable**.
`backend/` is a flat module layout with no package root, and the app imports itself
top-level-relative (`from config import ...`), resolved by putting `backend/` on `sys.path`
(the Dockerfile's `PYTHONPATH`, `conftest.py`'s `sys.path[0]` shim). Making it genuinely
importable means rewriting every intra-app import plus the Dockerfile and conftest — a
refactor, not a packaging change. So it is registered in `verify-wheel-imports.py`'s
`SKIPPED_DISTS` with the structural reason and what would lift it; that mechanism prints the
skip and refuses to let reduced coverage read as a pass. **`requirements.txt` remains the
install path** the Dockerfile and CI use — a dependency change must land in both.

## F2 — Verify Conductor end-to-end on a clean machine (L, dep B5, E5, F1, F3)

- [ ] Clean VM: pinned installer (E5) → wizard → compose up (incl. hive-conductor) → authenticate
      → submit a DAG over WS → real model call → results.
- [ ] Fix what breaks (env plumbing, CORS/WS origin, image tags) — deployability fixes are
      allowed under freeze.
- [ ] **Resolve the sandbox-backend gap first:** every DEPLOYMENT-STANCE profile lists
      `maistro-sandbox-worker`, but no such package/service exists in the tree, and B3 removes
      the docker.sock compatibility path — leaving the official install with no sandbox
      execution backend. Either wire a real backend into the default compose (the `deploy/sbx`
      kit / maistro-rsi sandbox backends are the candidates) and update DEPLOYMENT-STANCE's
      component naming to match what ships, or amend DEPLOYMENT-STANCE to describe v1 without
      the worker. This blocks profile verification.
- [ ] Repeat for each `docs/product/DEPLOYMENT-STANCE.md` profile claiming conductor support;
      `deploy/scripts/backup.sh` + `verify-restore.sh` pass against the stack (v1 ships the
      compose story; K8s/Helm deferred via D5).
- [ ] Write the conductor quickstart README from exactly what was run.

**AC:** scripted end-to-end run recorded (commands + output); Playwright e2e (C2) green against
the composed stack with auth on.

## F3 — Make Conductor degraded modes loud, not silent (M)

**Context:** conductor degrades silently: `services/engine.py` bridge falls back to stubs,
`services/graph_runner.py:570` returns `"stub: no LLM configured"` as a normal-looking result,
`services/design_render.py` raises NotImplementedError as a 500. A v1 user with a misconfigured
key gets fake success.

- [ ] No-LLM-configured → hard-fail DAG execution unless an explicit `--allow-stub` opt-in;
      `degraded: true` in the health endpoint; stub results labelled as stubs in payloads.
- [ ] `design_render` PNG → clean 501 with message (documented in D5).
- [ ] Tests for each degraded path.

**AC:** impossible to run a DAG against a stub LLM without having opted in.

## F4 — Evolve + RSI through the Conductor UI, end-to-end — v1 headline (L, dep A1, B5)

**Context:** v1 criterion (d). The RSI conductor surface already exists (backend
`routes/rsi.py` + `services/rsi.py`, frontend `pages/RSI.tsx`; landed 07-15, rewired in
#263/#265/#270) — this item makes it a verified, supported feature rather than a
partially-shipped one.

- [ ] From the UI, drive a full loop against the composed stack with auth on: configure
      roster/budget → start an RSI run (directed and exploratory autorun) → watch evolve
      tournament state → review quarantine-gate output → approve/reject a promotion.
- [ ] Confirm the #263 route scoping + #265 grant flow work from the UI (not just curl).
- [ ] Fix integration breaks found (finishing a partially-shipped feature — the point of the
      freeze).
- [ ] Playwright e2e for the RSI page happy path (feeds C2).
- [ ] Write the v1 stability statement for evolve+RSI (with D3): what the UI + API contract
      guarantees vs best-effort (e.g. genome model rosters, provider availability).

**AC:** the full loop above is demonstrated and recorded; RSI e2e green in CI; stability
statement published. Given RSI/evolve are the most-churned, least-soaked code in the tree, this
item is a hard gate for G1.

---

# Workstream G — Stabilize, promote, tag, publish

## G1 — Stabilization pass on `integration` + v1.0.0-rc1 dry-run (M, dep all of B–F)

**Context:** the `integration` tier is currently inert (nothing beyond develop since 06-28) —
ADR-095 built it for exactly this. Machine-authored "RSI cycle N" commits land on develop;
RSI/security/CI are the least-soaked zones.

- [ ] Audit machine-authored RSI commits on `develop` since last human review; revert any
      touching shipped surface without tests.
- [ ] Promote `develop` → `integration` (merge-tree is clean); required checks + formal
      conformance must pass there.
- [ ] Tag `v1.0.0-rc1` on `integration`; release.yml rc path runs (TestPyPI + rc images).
- [ ] Fresh-machine install from the rc (E5 + F2 + F4 scripts); soak ≥3 days; fixes land on
      `develop` and re-promote; `v1.0.0-rc2` if needed.

**AC:** an rc has traversed the full pipeline untouched by hand; soak clean.

## G2 — [RUNBOOK] Release day: promote, tag v1.0.0, publish (M, dep G1)

**Preconditions:** G1 closed; all tracked items closed except this one; `release` environment +
PyPI trusted publishers configured; branch protections live (C3).

1. Confirm `integration` == the soaked rc commit. PR `integration` → `main`; **1 approval**
   (ADR-095); all required checks green. Merge preserving linear history — the tag must point at
   a tree byte-identical to the soaked rc.
2. Release.yml guard re-verifies tag == `VERSION` == all version sites == CHANGELOG heading.
   On `main`: `git tag -a v1.0.0 -m "maistro-engine v1.0.0" && git push origin v1.0.0`.
3. Watch release.yml: guard → wheels (5-package publish set, twine check, clean-venv smoke) →
   pause at `release` environment → approve → PyPI publish → images pushed + cosign-signed
   digests → GitHub release created with all artifacts and the ADR-076 API-version statement.
4. Post-tag verification on a clean machine: `pip install maistro-core==1.0.0` (and
   `maistro-rsi==1.0.0`, which must resolve its siblings at 1.0.0) from real PyPI;
   `MAISTRO_VERSION=v1.0.0 ./get.sh` (the downloaded installer invoked by path, as in E5's AC) →
   wizard → compose → DAG execution → RSI-via-UI loop (F2+F4 scripts verbatim); `cosign verify`
   both images from outside CI.
5. Close out: back-merge `main` → `develop` if any delta; bump `develop` to `1.1.0.dev0`; lift
   the freeze; open the v1.1 tracking set seeded with D1 deferrals.
6. Rollback plan: PyPI = yank (never delete); images = move `latest`/`1.0` tags back + advisory;
   git = tag stays, ship `v1.0.1`. **No force-pushes to `main`, ever.**

---

# Decisions of record (recommendations embedded above)

1. **PyPI publish set:** `maistro-core`, `maistro-canvas`, `maistro-evolve`, `maistro-rsi`,
   `maistro-bootstrap` (rsi's dependency). Evolve+RSI are v1 scope by decision; publication is
   contingent on E2 dep-capping and proven in the E3 rc dry-run. `maistro-server`, `-turing`,
   `-design`, `-registry` stay internal for v1; widen in v1.1 with per-package stability
   statements.
2. **Open PRs under freeze:** land all five; order #268 → #267 → #266 → #270 → #269; #269 is
   ruled deployability, not feature.
3. **Stranded branches:** close the 13 contained; close the 3 RSI mega-branches as superseded by
   the already-landed RSI rewrite; salvage only installer fixes.
4. **Integration tier:** used as the RC/QA home, per ADR-095.
5. **Versioning:** lockstep static versions + bump script + CI/tag-match guard; revisit dynamic
   versioning post-v1.
6. **Evolve benchmark renames (D3) block the tag** — non-negotiable for a public v1.
