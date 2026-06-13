# HackerNews Launch Readiness Audit

**Date:** 2026-06-10
**Scope:** `origin/develop` @ `648dc69` (full tree + reachable git history + CI)
**Method:** Parallel review — secrets/PII scan, security re-verification against `AUDIT.md` (2026-02-20), public-launch hygiene sweep, CI/test reproduction.
**Context:** The repository is **already public** on GitHub. Everything below is exposed today; the question is what to fix before deliberately driving traffic to it.

---

## Verdict: NOT READY — but close

No live secrets require rotation. The security posture has improved dramatically since the February audit (13 of 16 Majors and 2 of 4 Criticals genuinely fixed in code). The launch blockers are:

1. Employer-internal references and personal-infrastructure details committed in the tree and in recent git history.
2. CI is red on `develop` — all four jobs fail, and the fix already exists on `integration` (#113) but never landed here.
3. No LICENSE file exists anywhere in the repo, while README/CLAUDE.md claim Apache 2.0.
4. The README quick start (`uv run pytest`) crashes on collection.
5. Three remaining security items: docker.sock mount in default compose, a canvas auth stub that grants admin to any caller, fail-open webhook signature verification.

---

## 1. Employer / personal information exposure (P0)

No API keys, tokens, or private keys exist in the working tree or reachable history. All `sk-`/`AKIA`/`ghp_`/`PRIVATE KEY` matches are verified test fixtures, redaction examples, or intentional Warden test payloads. No `.env` files are committed; root `docker-compose.yml` uses `:?` fail-fast for all secrets; installers generate random tokens.

What does ship is employer and home-network information:

| # | Finding | Location | Action |
|---|---------|----------|--------|
| 1.1 | **Scrub script documents everything it scrubbed**: four internal employer hostnames, an internal Jira project key, a real Airtable base ID, an internal codename, an internal email alias, and an internal migration timeline | `scripts/scrub-and-push-upstream.py` (tracked since `f6a06e2`, in ~10+ commits) | Delete the file **and** rewrite history (`git filter-repo --path scripts/scrub-and-push-upstream.py --invert-paths`). Treat the Airtable base ID as exposed. |
| 1.2 | **Employer work email as git author** on the 12 most recent `develop` commits (`648dc69`…`c0aa10d`) plus 19 `Co-authored-by` trailers | git history | Re-author (history rewrite) before announcing; switch git config to the GitHub noreply address already used on 103 commits. |
| 1.3 | Work-machine path leaking full name + employer OneDrive + internal project (macOS OneDrive path with full name and project), plus an internal-wiki reference | `packages/hive-conductor/OVERNIGHT-PLAN.md:261-264` | Remove lines; covered by the same history-rewrite pass. |
| 1.4 | Employer-internal project data in demo fixtures: internal Jira project key and Airtable table/field names; `carlos_pm.json` appears to be a real colleague's dashboard | `packages/hive-conductor/backend/data/demo_dashboards/*.json`, `DEMO-READY.md:31,48`, `docs/WAYS-OF-WORKING.md`, `packages/hive-conductor/frontend/src/fantasia-theme.css` | Rename to generic demo project/persona names. |
| 1.5 | Home-LAN topology in code defaults: private RFC-1918 addresses in `ha_tools.py:13`, `playwright.config.ts:9`, SPEC-185, SPEC-187 | hive-conductor + docs/specs | Replace with `localhost`/env placeholders. |
| 1.6 | Personal/family domain + home reverse-proxy hostname: a personal email address and reverse-proxy hostname | `docs/specs/SPEC-002-email-channel.md:3,31-32`, `cutover/MASTER-PLAN.md:266` | Replace with `example.com` placeholders. |
| 1.7 | Hardcoded Postgres credential (localhost dev default, no env override) | `packages/maistro-canvas/frontend/server.js:10` | Read from env; rotate if that password is reused anywhere real. |

Minor: commit message `433b362` discloses personal financial planning (cloud-credit amounts); `docker-compose.pm-poc.yml` ships `alice:changeme-alice` POC keys (documented, acceptable); `orders@maincharacter.press` ships as a library default in the Lulu client — confirm intentional; ADR-024/026 use `brigid` as an instance name — genericize if it's a real device.

**History rewrite scope:** the offending content is concentrated in recent history — an interactive rebase of the last ~15 commits (re-author + drop OVERNIGHT-PLAN lines) plus a `git filter-repo` pass for the scrub script covers it. Since the repo is already public, assume the content has been crawled: rotate anything you consider sensitive regardless of rewrite.

---

## 2. CI and test health (P0)

**Every recent CI run on `develop` is a failure** — all four jobs, on every commit through `648dc69`:

| Job | Failure | Root cause | Status |
|-----|---------|------------|--------|
| `lint-and-type-check` | `ruff check .` — 29 errors (21 auto-fixable) | Lint drift, incl. `scripts/scrub-and-push-upstream.py`, `router/scorer.py` (7) | Reproduced locally; `ruff check --fix` clears 21 |
| `test` | bootstrap tests: `ModuleNotFoundError: maistro_bootstrap` | `packages/maistro-bootstrap/src` missing from pytest `pythonpath` | **Fixed by #113 on `integration`** — never merged to `develop` |
| `security` | `pip-audit --strict` fails | Editable/local packages 404 against PyPI | **Fixed by #113 on `integration`** |
| `docker-build` | hive-conductor image build fails | Wrong build context (needs repo root) | **Fixed by #113 on `integration`** |

**Action:** cherry-pick/merge `a953a03` (#113) from `integration` into `develop`, then fix the residual ruff errors. Launching with a red CI badge on the default branch is a credibility hit HN will notice immediately.

Additional test findings (reproduced locally):

- **9 failing tests in `packages/maistro-core/tests/security/test_security_regression.py`** — these are hive-conductor tests misplaced in maistro-core's suite: they import `services.hyperlight_executor`, which only exists at `packages/hive-conductor/backend/services/`. They fail in the documented core-test invocation every time (result: `9 failed, 1497 passed`). Move them to `packages/hive-conductor/backend/tests/` or add the backend to their path handling. Failing *security regression* tests are a terrible look even when the cause is mechanical.
- **Root `uv run pytest` (the README quick-start command) crashes before collecting**: `ImportPathMismatchError: tests.conftest` — duplicate top-level `tests` package names between maistro-core and maistro-server. CI avoids it by running per-package. Fix the workspace `testpaths`/rootdir config or change the documented command.
- The `dev` dependency set is an *extra* (`uv sync --extra dev`), not a dependency group — `uv sync` alone leaves `pytest` uninstalled and `uv run pytest` silently falls back to any system pytest. Document or convert to `[dependency-groups]`.

---

## 3. Security posture (P0 items remain)

Re-verified all findings from `AUDIT.md` (2026-02-20) against the current tree. Summary: **CRIT-02 (auth off by default), CRIT-03 (webhook sig never called), and MAJ-01–07, 09–11, 13, 14, 16 are genuinely fixed** with real wiring — secure-by-default settings (`require_auth=True` + startup validation), shlex-quoted/base64'd sandbox commands gated by `is_dangerous_command`, authenticated WebSockets, allowlist env sanitization, fail-closed compose secrets, real health probes, graceful shutdown, CORS/rate-limiting/Prometheus, honest task phases.

Still open, in priority order:

| # | Finding | Severity | Evidence |
|---|---------|----------|----------|
| 3.1 | **CRIT-01: docker.sock mount in default compose.** The engine container (which runs LLM-driven agents) holds root-equivalent host access; sandbox hardening flags don't help because the engine itself owns the socket. A self-acknowledging TODO sits right above the mount. The curl installers default to rootless Podman (mitigated), but `docker-compose.yml` is what `get.sh` downloads. | Critical | `docker-compose.yml:29-32` |
| 3.2 | **Canvas auth is a no-op stub returning admin for any caller.** `get_current_user(api_key="")` ignores its argument and returns `CurrentUser(roles=("admin",))`; wired into ~20 routes. Documented as localhost-only, but any non-loopback bind is fully open. | Major | `packages/maistro-canvas/src/maistro_canvas/auth.py:28-46`, `canvas/routes.py:333+` |
| 3.3 | **Webhook/CI signature verification is fail-open when secret unset** (warn-only skip), and webhook routers are mounted unauthenticated at both `/webhooks/*` and `/v1/webhooks/*`. Compose defaults both secrets to empty. Refuse to register the routes (or reject POSTs) when no secret is configured. | Major | `webhooks.py:74-78,165-169`, `main.py:209,216`, `docker-compose.yml:25-26` |
| 3.4 | CRIT-04: task state still in-memory (`OrderedDict`), no persistence — "I restarted it and lost my tasks" will be an early HN comment. Document prominently or land Phase-2 persistence. | Major (ops) | `tasks/queue.py:42` |
| 3.5 | `LLMProviderError` 502 echoes raw upstream exception text to clients (other branches were sanitized). | Minor | `chat_completions.py:187` |
| 3.6 | `get.sh` pins raw-URL downloads to the moving `develop` branch — pin to a tag/release for launch. | Minor | `get.sh:22,82` |

---

## 4. First-impressions hygiene (P1)

What an HN reader sees in the first five minutes:

| # | Finding | Action |
|---|---------|--------|
| 4.1 | **No LICENSE file exists** (`git ls-files | grep -i license` → nothing), yet README:150, CLAUDE.md, and INSPIRATIONS.md all claim Apache 2.0; no pyproject declares a `license` field. Legally the code is all-rights-reserved. | Add `LICENSE` (Apache-2.0) + `license` field in all 9 pyprojects. |
| 4.2 | **Root `AUDIT.md` is the guaranteed HN screenshot**: "Verdict: NOT READY FOR COMMERCIAL PRODUCTION — 4 Critical · 16 Major" — describing a codebase that no longer exists (most findings now fixed, see §3), with no remediation status. | Delete, or move under `docs/audit/` with a prominent "historical — since remediated, see HN-LAUNCH-AUDIT" header. |
| 4.3 | README links a nonexistent ADR (`ADR-042-graph-execution-protocol.md` — graph execution is ADR-062) and misstates the ADR count ("through ADR-057"; there are 96). CLAUDE.md says 43. Three documents, three different counts, all wrong. | Fix links/counts; CLAUDE.md needs a refresh pass (also claims ~375 core tests — 1,508 collect; documents a root `src/maistro/` layout that no longer exists; misses `maistro-design`/`maistro-registry`). |
| 4.4 | Hard links to private repos that 404 for the public: `Project_mAIstro`, `AgentTuring`, `agent-stronghold/stronghold` in ROADMAP.md, BACKLOG.md, docs/proposals/. | De-link or move to private tracking. |
| 4.5 | `CONSOLIDATION-PLAN.md` leaks local filesystem paths (`/root/github/stronghold/`, `/root/docker/conductor-router/`); README links to it. | Move to docs/ or delete. |
| 4.6 | `.github/workflows/mutation.yml` and `security.yml` reference a tree from different infrastructure (`container_registry/user_containers/sandbox_templates/...`) that doesn't exist here. | Fix or remove the workflows. |
| 4.7 | Product naming is inconsistent three ways: "Agent Conductor" (README/CLAUDE.md) vs "Hive Conductor" (cutover/, design/, `get.hiveconductor.com`) vs package `hive-conductor`; plus "Canvas book-maker (name TBD)". | Pick one name per product before launch. |
| 4.8 | `docs/JFC-SANDBOX.md` — filename reads as a profanity acronym, references internal "Vibe Hosting" container-broker infra, and contains a relative link escaping the repo. | Rename/remove. |
| 4.9 | Python version messaging inconsistent: CLAUDE.md "3.12+", README "3.11+", `.python-version` pins 3.13. Branch model docs say `feature/* → integration → main` while CI triggers on four branches including `develop`. | Align docs; state which branch is canonical. |
| 4.10 | Package metadata thin for a public release: no `license`/`authors`/`urls`/classifiers in any pyproject; CLAUDE.md says `pip install maistro-core` — if it isn't on PyPI, HN will try it within minutes. | Add metadata; publish to PyPI or change the wording. |
| 4.11 | Root clutter: `cutover/`, `design/`, empty `INSPIRATIONS.md`, `config/atlassian-rovo-mcp.cursor.json` (byte-duplicate of `.cursor/mcp.json`), `apps/` README for an app that doesn't exist. | Fold into docs/ or remove. Good news: `potential-dead-code/`, `.hypothesis/`, root `src/` are already gone from this branch. |

Comment hygiene is genuinely good: 30 TODOs / 3 FIXMEs repo-wide, zero profanity, no placeholder text, no AI-generated tells.

---

## 5. Launch checklist (ordered)

**P0 — do not announce without:**
1. Delete `scripts/scrub-and-push-upstream.py` + history rewrite for it; re-author the 12 work-email commits (§1.1–1.3).
2. Genericize employer demo fixtures, LAN IPs, personal domain, OVERNIGHT-PLAN paths (§1.4–1.6).
3. Land #113 (`a953a03` on `integration`) into `develop`; run `ruff check --fix` + fix the 8 remaining lint errors → green CI (§2).
4. Add the Apache-2.0 LICENSE file (§4.1).
5. Remove the docker.sock mount from the default compose path, or make the Podman path the only documented one (§3.1).
6. Fix or clearly fence the canvas admin auth stub (§3.2); make webhooks fail-closed (§3.3).

**P1 — strongly recommended:**
7. Relocate the 9 misplaced security-regression tests; fix root `uv run pytest` (§2).
8. Archive root `AUDIT.md` with remediation status; fix README ADR links/counts; refresh CLAUDE.md (§4.2–4.3).
9. De-link private repos; delete/relocate CONSOLIDATION-PLAN.md; fix the two foreign-infra workflows (§4.4–4.6).
10. Resolve product naming; rename `JFC-SANDBOX.md` (§4.7–4.8).

**P2 — nice before the traffic spike:**
11. Sanitize the 502 detail leak; pin `get.sh` to a release tag; document the in-memory task-state limitation; env-var the canvas frontend Postgres credential; package metadata + PyPI decision (§3.4–3.6, §4.10).
