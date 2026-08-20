# Security Remediation Backlog — Deferred Items

Internal tracking doc. Generated from a full verification pass (2026-08-20) against
`docs/reviews/2026-07-29-security-functionality-review.md`,
`docs/reviews/2026-07-29-rsi-containment-review.md`,
`docs/reviews/2026-07-27-codebase-review.md`, and
`docs/security/AGENT-FRAMEWORK-FLAWS-LEDGER.md`.

Every item below was confirmed **still open in current code** (file:line evidence gathered
during verification, not just trust in the source documents, several of which were stale —
roughly 15 of the ~70 findings checked were already fixed by other commits). Items with a
small/trivial effort estimate were fixed directly in this same pass — see the commits on
`claude/publish-scrub-audit`. This document tracks what's **left**.

Not for the public v1 tree — this is an itemized "here's what's still wrong" list. Excluded
from the v1-clean orphan commit alongside `docs/reviews/`, `docs/security/`, `docs/audit/`,
`docs/analysis/`.

---

## Priority 1 — RSI subsystem (highest real-world risk)

The self-improvement loop (`packages/maistro-rsi/`) is reachable via the hive-conductor web
API (`/v1/rsi`), not just CLI. Of 25 Critical/High findings in the containment review, only
3 were fixed in this pass (O-2, E-1, E-2 — the narrow, self-contained ones). The rest are
structural and need a dedicated pass, not a mixed batch fix:

| ID | Issue | Effort |
|---|---|---|
| K-1 | Stop button cancels a coroutine; actual work runs in `asyncio.to_thread` and is unaffected. Reports `"stopped"` regardless. | small–medium |
| K-1a | No wall-clock/token budget enforced; `max_wall_clock_s` defaults to `None`; `QuotaBurnScheduler` never instantiated by `LocalRsiLoop`. | small |
| K-2 (remainder) | Git-push refspec validation — the general fix landed in `tools/git/server.py` (this pass); confirm it actually covers the RSI call path too. | verify |
| K-3 | Quarantine/Warden scan has zero call sites on the shipped execution path (`LocalRsiLoop` → `export_promotions` → PR). | small (one insertion point) but tied to K-1/K-1a — needs a holistic pass |
| K-3a | Diff-path regex (`selfbranch.py:41`) silently drops paths containing spaces — no fail-closed check. | trivial–small |
| K-4 | LiteLLM gateway config has a catch-all `model_name: "*"` entry, no `max_budget`/rpm/tpm. One key unlocks 15 providers, unbudgeted. | medium |
| K-5 | Subprocess calls in the RSI loop pass no sanitized `env=` — master key reachable from sandboxed candidate code. Runner container has no `USER` (runs root). `gateway.env` mounted `:ro` but readable/catable. | medium |
| K-6 | Test/lint gate defeated by a `conftest.py`/`pyproject.toml` one-liner in the candidate's own tree; gate reads exit code, not structured results. | medium–large |
| O-3 | Review diff truncated to 4KB; patch applied via `git am --3way` with no baseline-sha check. | small |
| O-4 | Checkpoint report written before the revert pass — reverted promotions still counted as promoted. | small |
| O-5 | A candidate that fails to revert immunizes itself against future revert attempts. | small |
| O-6 | No notification on suspicious events; `EventCategory.SECURITY` has zero real emitters. | medium |
| O-8 | Trace notes unsigned, force-overwritable (`-f`), return value of the write ignored. | medium |
| G-1 | Fitness/regression gates fail OPEN on timeout/error (documented as intentional in the docstring). | medium |
| G-2 | Gates are blind to all non-Python files, including workflow/launcher files themselves. | small–medium |
| G-3 | `spec_completion`/`spec_proposed` (0.85 of fitness weight) forgeable — no baseline comparison. | medium |
| G-6 | LLM regression judge: input truncated at 8K with no injection delimiting, fails open to 0.7 score, judge model can equal the author model. | medium |
| G-7 | Builders review gate skips itself via a substring match against its own prior output. | medium |
| P-1 | Genome free-text slots (persona/goals) reach the system prompt unscanned, uncapped, and REPLACE rather than concatenate the default prompt. | medium |
| P-2 | Scout reads agent-authored baseline source into the next objective with no Warden scan. | medium |
| P-3 | Hypothesis-tree node text restored into prompts unscanned (the ledger-insight path is scanned; this parallel path isn't). | medium |
| P-5 | Resume path `git apply`s saved patches with no signature/provenance check and no gate re-run. | medium |

**Recommendation:** treat RSI as an explicitly experimental/opt-in feature for v1 (gate it
behind a loud warning, or disable the `/v1/rsi` web route by default) until K-1/K-1a/K-3
get a real, tested fix as one coherent change — patching them individually risks false
confidence, since the containment model is broken as a system, not just at isolated points.

## Priority 2 — Core security engine, remaining structural gaps

| ID | Issue | Effort |
|---|---|---|
| C-3 | `SandboxedShell` containment is regex/pattern-scan only, no real process isolation (no chroot/uid/rlimit/seccomp); defaults to `isolation="local"`. | large — architectural |
| H-8 | Sandbox bind-mount root shared with host git tools — same `ALLOWED_HOST_ROOTS` used by both the untrusted container mount and host git operations. | medium |
| H-9 | `users.toml` HMAC signature keyed by the admin key stored in the same signed file (extracts key from content it's verifying). `can_perform` still defaults to allow (`action not in _ADMIN_TOOLS`). | medium |
| H-14 | `maistro.sandbox` protocol/selector abstraction layer wired to nothing in production — an unused seam. | large — needs an ADR decision on whether to wire it in or remove it |
| H-19 | Chat/memory/messages/DAG-run stores in hive-conductor have zero owner filtering — any authenticated user can read any other user's chat sessions, messages, and DAG runs. `ChatSession.user_id` field exists but no handler reads it. | medium |
| H-20 (remainder) | `get_current_user` unions `elevated_permissions` across ALL task ids, not scoped per-task. (The missing `GET` section in `_PROTECTED_OPS` was fixed this pass.) | small–medium |
| H-2 | RSI quarantine gate not wired into `_harvest` before `git push --force-with-lease` + `gh pr create`. | medium (see RSI section above — same root cause as K-3) |
| H-10 | hive-conductor's chat pipeline (`chat_completion.py`) dispatches to `_TOOL_HANDLERS.get(tool_name, _tool_poll_jira)` with zero Warden/Sentinel references anywhere in the 2,400-line file — an unknown tool name silently falls back to polling Jira, and no request in this pipeline goes through the security gate at all. | medium |
| C-4 (remainder) | Canvas `child_profiles` table has no owner/org column — auth dependency was added to routes this pass, but per-row ownership filtering still needs a schema migration. | medium — real DB migration |

## Priority 3 — Ledger items (attack-class tracking, not yet closed)

| ID | Issue | Effort |
|---|---|---|
| #5 (gap 2) | `/v1/chat/completions` calls `run_task()` directly, bypassing `Gate.process_input` entirely — the general chat path has no injection gate at all (gap 1, normalization, was fixed this pass). | small–medium |
| #10 | Tier/budget authorization (`sentinel.authorize()`) isn't integrated at the actual tool-call boundary (`pre_call()`); only a narrow DAG-width-gating path calls it. | medium |
| #12 | Owner-authority intersection (`Principal.owner` vs. granted scopes) declared but never implemented in `authorize()`. Same root cause as #10 — same fix. | medium |
| #13 | The hardened skill-install pipeline (`import_pipeline.py` — scan → salvage → re-scan → T3 → canary) exists and works in isolation, but nothing routes real install traffic through it; `marketplace.install()` and `Container.import_skill()` both have zero production callers. | medium — needs a real HTTP route wired to the new pipeline |

---

## Already fixed this pass (for reference — see commits on `claude/publish-scrub-audit`)

Core security engine: Sentinel fail-open (C-1), TuringSecurityBridge signature bug (C-2),
Warden block threshold, external-content marker stripping, zero-width-char coverage,
`can_use_tool` default, webhook injection blocking, `AllowAllGate` review, builders
review-skip predicate.

Skills/marketplace: symlink guard on community loop, marketplace writes scanned content,
trust-tier self-declaration, `verify_skill_payload` wiring.

Sandbox/git tooling: `sync_to_host` host-side exclusion, `ContainerBuilderSandbox` hardening
flags, `git_clone`/`git_push` validation, dead `trust_boundary.py` removed or fixed,
`core.hooksPath` neutralization.

hive-conductor: session TTL, credential master-key directory override, task-ownership
empty-string bug, `_PROTECTED_OPS` GET section, `iter_task_events` per-user scoping,
`requirements.txt`/`pyproject.toml` dependency sync, `design` router optional-loading,
Sentinel `permission_preset` and `strike_tracking_enabled` shipped defaults.

Canvas: layer-ownership IDOR, missing auth dependencies across asset routes, Lulu preflight
auth + PyPDF2→pypdf, quantity/count caps, `MAX_IMAGE_PIXELS` validation, upload
`UnboundLocalError`.

Misc: WebSocket token-in-URL + Origin check (`maistro-server`), ANSI/OSC52 terminal-escape
stripping, RSI audit-log fabricated entries removed, RSI launcher no longer targets its own
gate files, `--promotion-review` restored as default, `permissions:` blocks added to 4
CI workflows.

(Exact per-item verification pending the fix agents' final reports — cross-check against
their commits before treating this "already fixed" list as final.)
