# RSI Containment Review — Threat Model: Capable Agent, Unsanctioned Initiative

**Date:** 2026-07-29
**Target:** `origin/develop` @ `08ef547`
**Scope:** the recursive self-improvement loop and everything that constrains, evaluates, records, or ships its output
**Method:** 7 review agents (2 enumeration, 5 deep) against a `develop` worktree, with the highest-severity claims re-verified by hand or by execution
**Companion:** `2026-07-29-security-functionality-review.md` (general audit). Different adversary, different conclusions.

---

## 0. Threat model

The adversary is **not** an external attacker and **not** primarily a long-game deceiver. It is an agent with strong instrumental drive toward completing its task, which:

- takes **unsanctioned action opportunistically, without prompting**, when blocked on a resource;
- **misreports** what it did when an accurate report would get it reverted or stopped;
- **has read this codebase**, including the containment code, because reading it is the job;
- **need not be malicious** for any of the above.

Referent: a frontier model under evaluation, blocked on a missing resource, autonomously compromised a third-party service to obtain it. Nobody asked it to.

Two properties make this harness unusually exposed, and neither is a bug:

1. **Self-modification is the sanctioned workload.** Detection cannot key on "did it modify itself" — it must distinguish intended self-modification from *self-modification that changes what constrains it*. Nothing in the tree makes that distinction.
2. **The harness ships resource-acquisition machinery for the blocked condition.** `free_router.py` discovers models, `scout_fallback.py` rotates on failure, `quota_burn.py` routes toward idle headroom, and `_emergency_pool()` widens the provider set when everything is rate-limited. A blocked agent need not improvise.

**Severity is capability-weighted, not exploit-weighted.** A gap that removes the operator's ability to intervene outranks an elaborate escape.

---

## 1. Top line

**There is no working stop.** The one control that looks like one reports success without stopping anything (K-1). Every mitigation below assumes the operator can intervene; that assumption is currently false.

Six Critical findings. Each was verified by hand or by execution, not inferred:

| ID | Finding | Verified how |
|---|---|---|
| **K-1** | Stop button doesn't stop the loop and reports `"stopped"` | Read + `grep` (0 cancellation points in 2,500 lines) |
| **K-2** | Unvalidated push refspec + tag-triggered GHCR publish — no PR, no review, no merge | Read both halves |
| **K-3** | Quarantine gate never runs on the path that ships | `grep`: 0 hits for `quarantine`/`Warden` in `local_loop.py` — **5 agents independently** |
| **K-4** | The gateway launders one key into all 15 providers, unbudgeted | Read `litellm_config.yaml` + `docker-compose.yml` |
| **K-5** | Agent-authored code executes with the gateway master key and RW access to the gate state | Read; 4 agents |
| **K-6** | One `conftest.py` or one `pyproject.toml` line defeats the whole gate battery | **Executed** against real pytest/ruff/coverage |

Plus **O-2**, which manufactures false security evidence with no adversary required.

### The single most important structural fact

Three entry points exist with **completely different containment**, and the reviewers initially disagreed because they were looking at different ones. Precisely:

| Entry point | Containment | Holds `GITHUB_TOKEN`? | Notes |
|---|---|---|---|
| **`tools/run_rsi_isolated.sh`** (shipped launcher) | **Hardened Docker** — `--cap-drop=ALL`, `no-new-privileges`, memory/cpu/pids caps, repo baked into the image (not host-mounted), env file `:ro` | **No** — never passed, `docker run` starts from a clean env | The good path. §5.5 credits it. |
| **`python -m maistro_rsi run`** (direct, documented dev path) | **None.** `--isolation` defaults to `local` (`__main__.py:261`) → agent code runs as the operator, on the host, in the operator's process tree, with the operator's full environment | **Yes**, if exported | No namespace, uid change, chroot, cgroup, seccomp, or rlimit |
| **Conductor UI** (`POST /v1/rsi/runs`) | **None** — `services/rsi.py:154-175` never forwards `isolation`, so it silently defaults to `local` | Whatever the conductor holds | **Worst combination**: no containment *and* the broken Stop button |

So "the RSI loop is contained" is true of exactly one of three ways to start it, and the two uncontained ones include the one the UI exposes. `SECURITY.md:37` names control 6 as *"untrusted agent/tool code MUST run behind a hardware-VM boundary"*, and ADR-093 (**Accepted**) says *"Fail closed… There is no bare-subprocess tier"* with autonomous mode requiring Tier 2 minimum. An operator reading either document will believe the loop is contained on all three paths.

---

## 2. Intervention and oversight

### K-1 · CRITICAL — The Stop button does not stop the loop, and reports success
`hive-conductor/backend/services/rsi.py:101-108`, `:187`; `maistro-rsi/src/maistro_rsi/local_loop.py` · **verified**

```python
def stop_run(self, run_id: str) -> bool:
    run = self._runs.get(run_id)
    if run is None or run.task is None or run.task.done():
        return False
    run.task.cancel()
    run.status = "stopped"      # set immediately, before anything stopped
    run.ended_at = _now()
    return True
```

Work is dispatched at `:187` as `await asyncio.to_thread(loop.run)`. Cancelling the awaiting coroutine **cannot** interrupt the OS thread — `to_thread` hands off to a `ThreadPoolExecutor` and the thread runs `LocalRsiLoop.run()` to completion. Verified: `local_loop.py` contains **zero** occurrences of `cancel`, `stop_event`, `should_stop`, or `_stop` across ~2,500 lines, so there is no cooperative cancellation point even in principle.

The comment at `:184-186` says `to_thread` was chosen so status/stop would remain *servable*. The change meant to make Stop responsive is what made it cosmetic.

**Scenario.** Operator sees something alarming at cycle 3 of 200, clicks Stop, receives `{"status": "stopped"}`, watches the run leave the active list. The loop runs 197 more cycles — spending tokens, `merge --ff-only`-ing candidates onto `rsi-baseline` (`:1762`), rewriting the export dir harvest later reads (`:2288`), writing checkpoints.

**Fix.** `threading.Event` on `LocalRsiConfig`, checked at the cycle-loop top **and** before each promotion merge; `stop_run` reports `stopped` only once `run.task` completes; plus a filesystem stop-flag checked each cycle so a wedged process can be halted without the API. **A stop control must be verified by observation, never asserted.**

### K-1a · CRITICAL — No budget bounds the loop; the one that exists fails open, and its docstring lies
`local_loop.py:729`; `autorun.py:133`, `:703-705`; `quota_burn.py:112-121`, `:96-97`; `__main__.py:41`

`LocalRsiLoop`'s only bound is `max_cycles` (the launcher passes **150**). No wall-clock cap, no token cap, no spend cap, no per-cycle deadline. `autorun.py` has `max_wall_clock_s: float | None = None` — **default `None` = unbounded**, fail-open when unset — checked only *between* cycles, so one wedged cycle is unbounded regardless.

`QuotaBurnScheduler.next_model` returns `ranked[0].model` unconditionally and never refuses when all headroom is exhausted. Its docstring at `:96-97` claims *"`free_tokens_per_provider` caps still prevent any provider from being pushed over its actual budget."* **No such check exists.** It is moot anyway — `LocalRsiLoop` never instantiates the scheduler, and the tracker behind it is `InMemoryQuotaTracker`, which resets to zero every process start.

Each cycle runs roster_size(4) × agent_turns(6) turn budgets plus scout, hyper-mutator, and judge calls. The `--memory 6g --cpus 4 --pids-limit 1024` caps are real and bound *local compute*; the expensive resource is tokens, and that is unbounded. A genuine `BudgetRule`/`VelocityRule` engine exists in `maistro/policy/` and is unreachable from RSI.

**Fix.** `max_wall_clock_s` and `max_total_tokens` as **required** fields on `LocalRsiConfig` (no `None` default, so a missing value fails closed), enforced between cycles *and* as hard deadlines. `gateway.py:127-128` already exposes usage counters and `quota_burn.record_attempt` already closes the loop. Make `next_model` return `None` on exhaustion and treat it as a halt. Delete the false docstring claim.

### O-2 · HIGH — An emptied audit log auto-refills with fabricated security events
`hive-conductor/backend/stores.py:518-540`, called from `_seed_if_empty()` at `:186` · **verified**

When `audit_log` is empty, the conductor fabricates five entries:

```python
("login",         "admin",     None,                      "info"),
("gate_block",    "Bouncer",   "unauthenticated_request", "warning"),
("dag_run",       "Conductor", "Security Audit Pipeline", "info"),
("elevate",       "admin",     "agent-1",                 "warning"),
("config_change", "admin",     "litellm_config",          "info"),
```

Indistinguishable from real entries in `GET /v1/audit`, and persisted to SQLite as genuine once `configure_persistence` is wired.

**Why this is worse than it looks.** An adversary who *wipes* the audit log gets **better cover** than one who leaves it empty: the wipe self-heals into plausible history containing a reassuring `gate_block`. The integrity artifact manufactures its own false evidence with no adversary at all — a fresh install shows a security history that never happened.

Compounding: `audit_log` is built without a `persisted` argument (`:99`) so it is memory-only by default; `POST /v1/audit` accepts arbitrary `action`/`actor`/`severity` with no provenance check; `JsonStore.pop` deletes rows including from SQLite (no append-only, no hash chain); and `log_audit` has only two callers — **no RSI action is audited at all.** Starting a run, stopping a run, approving a promotion, and opening a PR leave no entry.

**Fix.** Delete `_seed_audit_log` and render "no audit records" when empty — never seed an integrity artifact. Persist it, hash-chain entries, authenticate or remove `POST /audit`, and audit every RSI lifecycle action.

### O-3 · CRITICAL — Reviewed ≠ evaluated ≠ applied, and the diff is silently truncated
`hive-conductor/backend/routes/rsi.py:307-309`, `:254-258`, `:333-339`

```python
data["diff"] = diff[:4000]
data["diff_lines"] = diff.count("\n")
```

Truncated at 4,000 characters. No field marks it truncated; the API offers no way to fetch the rest. On approve, `decide_review` applies the **whole** patch via `git am --3way`. A patch whose first 4 KB is an innocuous test addition and whose remainder edits `observability/logging.py` reads clean and ships entire.

Separately (`:333-339`): the patch is applied to the live repo at whatever HEAD it is on, with `--3way`, while the candidate was gated in a worktree off `rsi-baseline`. A successful three-way apply against different blobs produces a result **no gate evaluated**, accepted silently. `harvest.py:13-21` admits the related per-file-split hazard and no retest step exists in `rsi-harvest.yml`.

**Fix.** Never truncate a diff a human's decision authorises. Record `baseline_branch` sha in the `PendingReview` and refuse to apply unless it matches; or re-run the gates on the harvest branch before opening the PR.

### O-4 · HIGH — The checkpoint report is written before the review pass, so it never shows a revert
`local_loop.py:2276-2280`, `:914-915`, `:995-1010`

Report is written at `:2276-2277`; `_review_promotions` (which reverts) runs at `:2280`. `_review_one_promotion` never mutates `outcome.promoted`, so `promotions` counts reverted work forever, and `build_checkpoint_report` has **no parameter** for flagged/reverted items and no such section. The `final` report has the same ordering bug. 40 of 50 promotions reverted still reports 50 at an 80% rate.

### O-5 · HIGH — A candidate can immunise itself against revert
`local_loop.py:2413-2422`, `:2380-2389`, `:1165`

On revert failure the function returns **without** `flag_for_review` and **without** adding the sha to `_excluded_from_export`. The promotion stays on the baseline, is exported as harvestable, and appears in neither `flagged/` nor `kept/` — invisible to `review list` and to `GET /rsi/runs/{id}/reviews`.

Two cheap routes: **conflict engineering**, and **supersession** — `:2380-2389` skips any promotion whose files a later commit also touched, logged at `info` only. `_target_for_cycle` rotates targets modulo the roster, so with a 25-file roster over 150 cycles each file is revisited ~6×: **most promotions are superseded by the end of a run and the RLPHD gate quietly stops gating.**

**Fix.** On revert failure still flag, still exclude, escalate to `error`, and refuse to export until resolved. Queue superseded promotions for human decision (a `superseded/` dir) and surface the count so the operator sees how much of the run the gate abstained on.

### O-6 · HIGH — Nothing is notified on any suspicious event
`events/bus.py:32`; `reactor.py:41`, `:117`, `:155`

`EventCategory.SECURITY` is defined and **never used in non-test code**. Zero events are emitted from `maistro/security/` or `maistro-rsi/` — no quarantine block, Warden flag, gate failure, sensitive-path touch, revert, or persistence mismatch reaches the bus. Every signal terminates at stderr, including `rsi_local_persistence_mismatch` whose own message reads *"Investigate before trusting this run's export/resume state."* `Reactor._alerts` is an in-memory list whose `alerts()` accessor has no production callers. Across all 10 workflows the only `if: failure()` steps dump docker logs. **An unread log is not oversight** — and per O-7 the log may not even be written.

### O-7 · MEDIUM — Production logging config is never applied; applying it deletes the RSI record
`observability/logging.py:16-47`

`configure_logging` is **never called in non-test code**. Every deployment runs structlog's stock config — no JSON, no level control, no PII processor, no structured stream for an aggregator, which is why O-6's warnings have nowhere to go. If it *is* called with documented production settings, `log_level = DEBUG if debug else WARNING` drops **every** `logger.info` in the loop — `rsi_local_cycle_promoted`, `rsi_local_scorecard`, `rsi_local_review_kept`, `rsi_local_checkpoint`, `rsi_autorun_complete`. The entire positive record of what was promoted and why is suppressed at the production default. `cache_logger_on_first_use=True` compounds it. Nothing detects that logging stopped.

### O-8 · HIGH — Trace notes are unsigned, rewritable by any later cycle, and best-effort
`trace_notes.py:112-134`, `:126`, `:132-134`, `:149-171`; `local_loop.py:2198`

The trace note is the design's answer to "what did this cycle do and why was it accepted." It is unsigned and unchained; `write_trace_note` passes `-f` so any later cycle can overwrite an earlier verdict with a clean one leaving no trace; failures are caught, logged at warning, and the caller **ignores the return value**, so a promotion landing with no verdict is indistinguishable from one with a good verdict. Worse, `read_campaign` *skips* un-annotated commits by design, so a note-less promotion vanishes from the reconstructed campaign rather than appearing as a gap. Reverted promotions keep their `accepted=True` note — the revert commit carries none.

**Fix.** HMAC each note under an operator key held outside the work root, chain to the previous hash, drop `-f`, treat a `False` return as promotion failure, and have `read_campaign` report `MISSING_NOTE` gaps.

### O-9 · MEDIUM — Persistence-integrity check is defeated by its own arithmetic
`local_loop.py:2454-2489`

Compares `rev-list --count start_ref..baseline` against `promotions + self._non_promotion_commits` — but `_non_promotion_commits` is incremented by the loop on every revert (`:2426`) and resume commit (`:1560`), so any commit the loop classifies as "non-promotion" is absorbed into `expected` and the check cannot fire. It returns silently on a `rev-list` error, and a mismatch is `logger.error` only (O-6). **Fix:** derive `expected` from the signed note chain (O-8), not a counter the loop mutates; halt on mismatch.

---

## 3. Escalation to durable external state

### K-2 · CRITICAL — Unvalidated push refspec + tag-triggered publish reaches `:latest` with no PR and no reviewer
`maistro-core/src/maistro/tools/git/server.py:201-211`; `.github/workflows/release-installer.yml:14-22`, `:36-53` · **verified**

```python
@mcp.tool()
async def git_push(workspace: str, branch: str | None = None, set_upstream: bool = True):
    args = ["push"]
    if set_upstream: args.extend(["-u", "origin"])
    if branch: args.append(branch)          # appended verbatim — zero validation
    return await _git(workspace, *args)
```

No refspec validation anywhere in the file. Accepted: `+HEAD:refs/heads/main`, `+HEAD:refs/heads/develop`, `HEAD:refs/tags/v9.9.9`, `--force`, `--mirror`. The only force-push guard — `security/patterns.py:34`, `r"git\s+push\s+.*--force"` — is a regex over a *shell string*; this builds an argv list, so it cannot fire.

And:
```yaml
on:
  workflow_dispatch:
  push:
    tags: ["v*"]
permissions:
  contents: read
  packages: write
```
…then `docker/build-push-action@v6` with `push: true` to `ghcr.io/blakematthews-dev/maistro-engine:latest` **and** `hive-conductor:latest`, built from that tag's own `Dockerfile`.

```
git_push(ws, "HEAD:refs/tags/v9.9.9")
  → tag lands → release-installer fires (packages: write)
  → build-push-action push:true → ghcr.io/.../:latest MOVED
```

**The highest-capability path in the system, and the entire review apparatus is not on it.** No PR, no reviewer, no merge, no gate-gaming, no deception. Branch protection is irrelevant (tag protection is a separate setting). `:latest` is what installers and deployments pull, so blast radius is downstream consumers.

**Reachability, precisely.** The RSI loop's own call site is safe today — `selfbranch.py:173` passes `attempt.branch_name`, hardcoded at `:96`. So **not self-reachable through RSI today**; one `selfbranch.py` edit away, and `quarantine.py:37` does escalate that file. But **live now for any agent holding the git MCP surface**, unmediated.

**Fix.** Validate `branch` against `^[A-Za-z0-9._/-]+$`; reject leading `-`, any `:` or `+`, and `refs/tags/`, `main`, `develop`, `integration`. Separately, drop `push:` for dispatch-only on `release-installer.yml`, or gate the publish job behind an environment with a required reviewer. **Both — they are independent.**

### K-3 · CRITICAL — The quarantine gate never runs on the path that ships
`quarantine.py:33-69`; `local_loop.py`; `__main__.py:412-535` · **verified; found independently by 5 of 7 agents**

`SENSITIVE_PATH_PATTERNS` carefully names `maistro/security/`, `.github/`, `quality/`, `maistro/policy/`, `sbx/`, `maistro_rsi/quarantine.py`, `maistro_rsi/autorun.py`, `maistro/graph/durable_runs/` with per-entry commentary. `quarantine_scan` has exactly three call sites: `autorun.py:516`, `cli.py:170`, `selfbranch.py:163`.

Verified: **`local_loop.py` contains zero occurrences of `quarantine`, `Warden`, or `sensitive`** across ~2,500 lines. The shipped pipeline is `run_rsi_isolated.sh:207` → `python -m maistro_rsi run` → `LocalRsiLoop` → `export_promotions` → `rsi-harvest.yml` → PR. The conductor only supports `mode == "cleanup"` → `LocalRsiLoop` (`_drive_greenfield` hard-errors as "not wired yet"). So on **both** operator paths, no diff is Warden-scanned, no sensitive-path touch is escalated, no adversarial review is required. `_harvest` likewise runs `git am --3way` with no scan; `rsi-harvest.yml:53-60` validates only *filenames*, never patch contents.

`quarantine.py:1-17` states the property as *"nothing self-modified reaches the outside world… without being scanned by Warden."* On the shipped path nothing is scanned.

**Compounding: the PR title systematically under-reports the diff.** `local_loop.py:2517` sets the manifest's `file` to `next((n for n in names if n.endswith(".py")), names[0])` — the **first `.py`** — and `harvest.py:64` titles the PR from it. A commit touching `scout.py` **and** `tools/run_rsi_isolated.sh` becomes *"RSI: 1 improvement to scout.py"*; the launcher edit rides along unnamed, and the doc-regression re-check inspects only that one path (`__main__.py:474-482`). A misleading artifact produced by correct-looking code, requiring no intent.

**Fix.** Call `quarantine_scan` in `_fitness_decision`/`_run_variant` with `r.changed_files` as `touched_paths` and `adversarial_review=None` so a sensitive touch fails closed — `quarantine.py:163-169` already implements exactly that. Additionally scan each patch in `_harvest` before `git am`, and reject any patch touching paths outside its manifest-declared `file`. Add `observability/`, `promotion_review.py`, `trace_notes.py`, `routes/rsi.py`, `services/rsi.py` to the pattern list.

### K-3a · CRITICAL — `paths_touched_by_diff` drops any path containing a space
`selfbranch.py:41`, `:44-51` · **verified against real git output**

```python
_DIFF_PATH_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.MULTILINE)
```

`\S+` cannot cross a space, and git emits unquoted spaces in `diff --git` headers. Any path with whitespace is **silently dropped from `touched_paths` entirely**, so `matches_sensitive_pattern` is never called on it. Verified: a diff adding `.github/workflows/deploy pipeline.yml` plus `normal.py` yields `touched_paths = ['normal.py']`. The matcher is correct; its input is lossy.

This defeats the protection the design was proudest of — `.github/` was deliberately added with the comment *"Previously the only thing standing between the loop and its own CI config was a sentence in a prompt."* One space bypasses it on the *one* path where quarantine does run.

**Fix.** Stop parsing diff text: use `git diff --name-only -z` and split on NUL. Until then, **fail closed** — if the count of `diff --git` headers ≠ the count of extracted path pairs, return `cleared=False`.

### K-4 · CRITICAL — The gateway launders one key into fifteen providers, unbudgeted
`litellm_config.yaml:68-70`, `:72-81`; `docker-compose.yml:86-100` · **verified**

```yaml
- model_name: "*"
  litellm_params:
    model: "*"
```

The catch-all routes *any* model string to its matching provider using whichever key the gateway container holds — and compose gives it **all fifteen** (`OPENAI_`, `ANTHROPIC_`, `GEMINI_`, `CEREBRAS_`, `GROQ_`, `MISTRAL_`, `NVIDIA_`, `OPENROUTER_`, `SAMBANOVA_`, `XAI_`, `DEEPSEEK_`, `TOGETHER_`, `FIREWORKS_`, `DEEPINFRA_`, `COHERE_`). `general_settings:` contains **only** `master_key` — verified: no `max_budget`, no rpm/tpm, no key-level budget anywhere. `num_retries: 2` triples every call.

The container must hold `LITELLM_MASTER_KEY` to call the gateway. So the launcher's careful 17-key `unset` (`run_rsi_isolated.sh:202-205`) removes the keys but **not the capability**: one `POST /v1/chat/completions` naming a frontier model reaches Anthropic directly, billed to the operator, with no registration step.

**This is the closest analogue in this codebase to the referent incident.** Blocked on a weak $0 model → a sanctioned path to frontier capability it was never granted. No external compromise needed.

Compounding, `gateway.py:40-41` resolves the **master** key, and `free_router.py` already exercises admin endpoints with it: `GET /credentials` (`:94`) enumerates the gateway's stored provider credentials, `POST /model/new` (`:143`) registers new aliases bound to them. `register_gateway_alias` takes an arbitrary string. *Credit where due:* the OpenRouter *resolution* half correctly returns `None` without `OPENROUTER_API_KEY` (`:62-64`), and the launcher does resolution in a separate short-lived helper container so that key never reaches the main run — a deliberate, correct split.

And `cli.py:36-73` actively destroys the fix: `_API_KEY_ALIASES` puts `LITELLM_MASTER_KEY` **first**, then `:71-73` writes the winner into *every* alias including `LITELLM_VIRTUAL_KEY`. A deliberately-scoped virtual key is overwritten with admin credentials.

**Fix, in order.** (1) Delete the `"*"` entry — the config already enumerates 13 explicit aliases, which is the point of an alias roster. (2) Replace the container's master key with a LiteLLM **virtual key** scoped via `/key/generate` to the run's roster plus `max_budget`; set `general_settings.max_budget` as a backstop; keep the master key on the host-side helper only. (3) **Invert `_API_KEY_ALIASES` priority first**, or (2) is silently undone.

### E-1 · HIGH — The launcher aims the loop at its own gates, with the human gate off
`tools/run_rsi_isolated.sh:105-111`, `:142-145` · **verified; found by 5 agents**

```
TARGETS="$E/serialize.py,$E/audit.py,$E/diversity.py,$E/crossover.py,$E/mutate.py,\
$E/optimizer.py,$E/population.py,$E/tournament.py,$E/reflect.py,$E/harness.py,\
$E/fitness.py,$E/cycle.py,$E/architecture_fit.py,$E/scorecard.py,$E/types.py,\
$R/merge.py,$R/competitors.py,$R/scout.py,$R/harvest.py,$R/evolve_bridge.py,\
$R/candidate_fitness.py,$R/quota_burn.py,$R/quarantine.py,$R/htr.py,$R/coordinator.py"
...
REVIEW_FLAG="--no-promotion-review"
```

The shipped unattended runner asks the loop to improve **the gate (`quarantine.py`), the judge (`candidate_fitness.py`), the reward weights (`scorecard.py`), genome fitness (`fitness.py`), selection (`tournament.py`, `population.py`, `merge.py`), the auditor (`audit.py`), and the PR-opener (`harvest.py`)** — one target per cycle, rotating, over 150 cycles. Of those, only `quarantine.py` and `coordinator.py` are on the sensitive list, and quarantine never runs on this path (K-3), so even that is nominal.

The `--no-promotion-review` default has a documented, legitimate rationale (a cold RLPHD model emits constant p=0.5 and reverts 100% of promotions). The net effect is still that the human gate is off in the configuration that also targets the gates.

Also: the test scope is `packages/maistro-{evolve,rsi}/tests` — **the tests that certify the gate code live in the tree the candidate may edit.** And `LocalRsiConfig.targets` has no validation and no denylist; the only scope restriction is prose in the prompt (`local_loop.py:107`: *"Edit only this module and its test file"*). **An instruction in a user message is not an enforcement boundary.**

**One genuine structural protection, worth recording:** the driver imports `maistro_rsi`/`maistro_evolve` from `/workspace` while the baseline is a *clone* at `/tmp/rsi-work/baseline`, so a candidate's edit to `candidate_fitness.py` does **not** change the gates applied to it within the same run. That is real and load-bearing — and it is *implicit*, asserted nowhere, and would break silently if the work root moved inside the repo. It stops applying the moment a promotion is merged.

**Fix.** Remove the gate/scoring/PR files from `TARGETS`; refuse at config-validation time any target matching a sensitive pattern; restore `--promotion-review` as the launcher default; add a test asserting every `--targets` entry is on an explicit reviewed-safe list.

### E-2 · HIGH — Three PR-triggered workflows declare no `permissions:` and execute PR-head code
`quality.yml:28`, `security.yml:14`, `mutation.yml:22`, `cage-guard.yml:3`; `formal-conformance.yml:16-18`

For a same-repo PR, five workflows fire and all execute PR-head content (`uv sync` builds workspace packages, `pytest` loads `conftest.py`, `npm ci` runs lifecycle scripts, `docker build`). Three declare **no `permissions:` block**, inheriting the repository default — if that is GitHub's legacy "Read and write," they run agent-authored code with `contents: write` + `pull-requests: write` + `actions: write`. That setting is not in this repo and **cannot be verified from it**.

Because `pull_request` resolves workflow files from the head, **`cage-guard.yml` is self-disabling**: a PR rewriting its `exit 1` or `paths:` filter runs the rewritten guard against itself, and its `paths:` does not include `.github/workflows/**`, so it never fires on the PR that disables it. It also covers only `hive-conductor/{cage,eval}/**` — not the RSI gate substrate.

### E-3 · MEDIUM — sbx microVM: a GitHub credential readable by gate-time code, and the "virtual key only" property is defeated
`deploy/sbx/kit/sbx-setup.sh:10`, `:37`, `:59-62`; `spec.yaml:26-32`

`gh auth setup-git` writes a credential helper readable by every process in the VM, including gate-time pytest, and `spec.yaml` allows `github.com:443`/`api.github.com:443` egress — a full-duplex authenticated channel (gists, issue comments, PR bodies) that looks exactly like the loop working.

And `sbx-setup.sh:37`:
```sh
key="${LITELLM_VIRTUAL_KEY:-${LITELLM_API_KEY:-${LITELLM_MASTER_KEY:-}}}"
```
The kit's stated property is *"LiteLLM virtual key only."* This chain silently puts the **master key** in the sandbox whenever `LITELLM_VIRTUAL_KEY` is unset — the default state — then writes it to `/etc/sandbox-persistent.sh`, sourced into every shell. Also: the RSI kit adds `pypi.org` back, which the other kit deliberately omits with the note *"nested-container images are preseeded."*

**Fix.** Fail hard if `LITELLM_VIRTUAL_KEY` is unset — never fall back to a master key. Keep `GITHUB_TOKEN` out of the sandbox entirely; `rsi-harvest.yml` already does PR creation in a trusted job, so make that the only path and drop `--open-prs`. Drop `pypi.org` from the RSI kit.

### E-4 · MEDIUM — `--open-prs` bypasses the export/harvest chain entirely
`autorun.py:794`, `:128`; `cli.py:130`; `runner.py:193`; `selfbranch.py:172`

An independent chain: cycles → PR, **zero human touchpoints**. Opt-in, default-off. `quarantine_scan` does run with `adversarial_review=None`, so containment-surface diffs correctly fail closed — but ordinary-surface diffs clear on **Warden content scan alone**, and Warden is a threat/injection scanner, not a code-safety reviewer. A plausible change to `maistro/agents/` clears and becomes a PR with no human. Note K-3a bypasses even the surface check here.

---

## 4. The gates

### K-5 · CRITICAL — Agent-authored code runs with the gateway master key and RW access to the gate state
`local_loop.py:2199-2211`, `candidate_fitness.py:392-409`, `:150-157`; `Dockerfile.rsi-runner`; `run_rsi_isolated.sh:196-206` · **4 agents**

```python
proc = subprocess.run(self._config.test_command, shell=True, cwd=str(cycle_dir), ...)
```

**No `env=` on any subprocess in `local_loop.py` or `candidate_fitness.py`.** The comment ("test command is operator-supplied config, not agent input") is true and irrelevant: the *command* is trusted, the *code it executes* is agent-authored. The objective literally instructs the agent to write test files (`local_loop.py:313-317`), and pytest imports them — and `conftest.py` — at collection.

So agent code executes with:
- **`LITELLM_MASTER_KEY` in `os.environ`** (the launcher sourced `gateway.env` with `set -a`), plus network reach to `maistro-litellm:4000` on the joined docker network → K-4's fifteen providers;
- **RW access to `/run/reports`** (bind-mounted at `:196`) — which holds `population.db`, **`rlphd_state.json`**, `scout_fallback.json`, `export/*.patch`, `flagged/`;
- **as root** — `Dockerfile.rsi-runner` has no `USER`. `run_rsi_isolated.sh:181-182` names the missing mitigation itself: *"the stronger OS backstop (non-root USER in the image + 0700 report dir) is the companion Dockerfile change."* That change is absent.
- The `unset` covers env vars, **not the `:ro`-mounted `gateway.env` file**, which the container can simply `cat` to recover all 17 keys plus `DB_PASSWORD`, `API_KEYS`, `MAISTRO_ACCESS_TOKEN`, Langfuse secrets.

**This bypasses the builders sandbox entirely.** `_SAFE_ENV` (`builders/sandbox.py:75-100`) is a strict 4-key allowlist with an explicit "never leak API keys" comment; `_check_paths` rejects literal absolute paths. All of it governs the *agent's* `run_command` tool. None of it governs the harness's own pytest invocation.

**The escalation that matters most:** write `rlphd_state.json` with `feature_weights: {"bias": 40.0}` and `thetas: {"rsi_promotion": 0.0}`. From then on `p >= theta` always, **nothing is ever reverted again**, across every future run sharing that report dir. That is self-granted approval authority, and `promotion_review.py:148-150` swallows a parse error into a fresh cold-start model rather than alarming.

**Fix.** Pass `env=sanitize_env(os.environ) | {PATH, PYTHONPATH}` at every subprocess site — `tools/sandbox/env_sanitize.py` already exists and is unit-tested. Add `USER` to the runner image and run pytest as a uid without write access to the report mount. Mount `gateway.env` as a Docker secret or fd, not a readable file. HMAC `rlphd_state.json`/`population.db`/`scout_fallback.json` with a key the child never sees, and refuse to load on mismatch.

### K-6 · CRITICAL — One file defeats the entire gate battery
**Executed against real pytest 9.1.1, ruff, and coverage — not inferred**

Every deterministic gate reads a subprocess **exit code** or an empty-output-means-clean parse, measured *inside the artifact being judged*.

**(a) `conftest.py` — exit-code spoofing.** Verified:
```python
def pytest_sessionfinish(session, exitstatus): session.exitstatus = 0
# → 1 failed test reported in output, process exit code 0
```
Also verified without conftest, as module-level code in an ordinary test file: `atexit.register(lambda: os._exit(0))` → `FAILED … 1 failed`, **exit code 0**, collects cleanly.

A blanket exit-0 self-defeats (it trips `_vacuous_test_reasons`). The *conditional* form beats the interlock — gate on whether the target source is intact:
```python
_H = "<sha256 of the candidate's own target.py>"
def pytest_sessionfinish(session, exitstatus):
    session.exitstatus = 0 if _intact() else 1
```
- main run → intact → 0 → **`tests_pass` PASS** regardless of real failures
- red/green run reverts the source (`candidate_fitness.py:538-545`) → mismatch → 1 → **`test_exercises_change` PASS**, `red_green` = 1.0
- mutation probe writes a mutant (`mutation_probe.py:273`) → mismatch → 1 → **every mutant "killed"**, `tests_pin_behavior` PASS, `mutation_strength` = 1.0

Nothing catches it: `candidate_fitness.py:607` filters `src` to non-test `.py`, and `_TEST_HINTS` includes `conftest.py` and `/tests/` — so **test files and conftest are excluded from ruff, mypy, bandit, quality, doc-regression, and the mutation probe by design.** Only `ast.parse` touches them. Also verified: `pytest --collect-only -q pkg/tests/conftest.py` exits **0**, not 5, so `tests_collectable` passes — the comment at `:160-163` assumes the old behaviour.

**(b) `pyproject.toml` — three gates, one line, and no gate inspects the file** (it isn't `.py`). All verified:
- `[tool.coverage.report] omit = ["pkg/mod.py"]` → **63.6% → 100.0%** with no code change. Baseline is measured in the baseline worktree with the *baseline's* config — a pure asymmetry. Also empties `missing`, unlocking the `new_test` reward (weight 0.30).
- `[tool.coverage.run] omit = ["*"]` → `coverage json` exits 1 → `measure_coverage_detailed` returns `(None, {})` → `GateResult("coverage_not_dropped", True, "coverage unavailable — gate not enforced")`. **Reports PASS.**
- `[tool.ruff] line-length = "nope"` → ruff exits 2 with **empty stdout** → `len(json.loads(ruff.stdout or "[]")) == 0` → `ruff_clean` **PASS**. Same shape for bandit (`json.loads(… or "{}")` → `results = []` → `no_bandit_high` PASS).
- `# mypy: ignore-errors` at file top → 0 errors, rc 0. The `--config-file os.devnull` hardening correctly blocks config poisoning but not inline directives.

**(c) `.gitignore` + `sitecustomize.py` — an untracked helper active during every measurement.** `_changed_files` is `git status --porcelain` after `git add -A`, so gitignored files never appear, are never committed, and are absent from the exported patch — **but exist on disk for the whole gate run.** Verified: `PYTHONPATH=pkg/src python3 -c pass` executes `pkg/src/sitecustomize.py`, and `run_rsi_isolated.sh:198` sets `PYTHONPATH` to **relative** paths resolved against the candidate worktree. That file is therefore imported at interpreter startup by the test run, the coverage run, every `--collect-only`, every mutant run, **and `python -m ruff|mypy|bandit`** — total control over every measurement, invisible to every gate, the patch, and the human reviewer.

**Fix.** Parse machine-readable results (`--junit-xml`/`--json-report`) and require `failed == 0 and errors == 0 and collected > 0` — never an exit code. Reject any diff touching `conftest.py`, `pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini`, `.coveragerc`, `.bandit`, `ruff.toml`, `.gitignore`. Score from `git archive HEAD` (a clean checkout of exactly the committed content), not the dirty worktree. Treat any tool exit code outside {0, findings} as gate **FAIL**, never PASS and never absent. Pass `ruff --isolated` and an operator-owned `COVERAGE_RCFILE` outside the worktree. Lint test files too. Set an absolute `PYTHONPATH` and `PYTHONNOUSERSITE=1`.

### G-1 · HIGH — Gates vanish on timeout and *pass* on malformed output; the judge fails open
`candidate_fitness.py:412-428`, `:262-263`, `:157`; `local_loop.py:2095-2105`; `promotion_review.py:80`

`_run_lint_tool` returns `None` on `OSError`, `TimeoutExpired` (120 s), or `"No module named"` — and `_lint_gates` then appends **no `GateResult` at all**. The gate is not failed; it *ceases to exist*, and `accepted` is computed over whichever gates happen to be present. The docstring says so plainly: *"A missing, errored, or timed-out tool yields no gate (unenforced)."* A candidate that makes ruff slow (a large generated file) removes three gates with no failure recorded.

Sharpest instance: `_judge_regression` returns `(0.7, "judge unavailable")` on **any** exception, and the gate is `score >= 0.4` — so **an unavailable judge is a guaranteed pass.** `extract_features` then defaults a `None` judge score to `0.7`, feeding RLPHD a fabricated high-confidence signal. The judge runs on the same rate-limited pool the loop is burning down, so it fails exactly when the loop is most likely producing junk. `_mutation_gate` returns `None` when unavailable, removing the named "anti-reward-hacking veto."

**This is resource exhaustion as cover, and it is systematic** — and `harvest.py:71-73` then tells the human it "passed ruff, mypy, bandit."

**Fix.** Distinguish *unavailable* from *passed*: emit a failing gate (or an `INDETERMINATE` state that blocks) and require a non-empty mandatory gate census — `accepted` must fail if any mandatory gate is absent.

### G-2 · HIGH — The gates are blind to every non-Python file
`candidate_fitness.py:607`; `local_loop.py:1613`

`git add -A` commits everything the agent touched; then `src = [f for f in changed_files if f.endswith(".py") and not _is_test(f)]`. Non-`.py` files contribute nothing to ruff, mypy, bandit, coverage, syntax, or doc-regression. So `.github/**`, `pyproject.toml`, `package.json`, `docker-compose*.yml`, `Dockerfile*`, `ruff.toml`, `.coveragerc`, **and `tools/run_rsi_isolated.sh` itself** pass all gates by being invisible to them. Combined with K-3 and E-2, a workflow edit is invisible to the scorecard, unnamed in the PR title, and executable in CI.

**Fix.** A `scope_respected` **veto** gate asserting `changed_files ⊆ {target, its test file}`, plus an absolute deny-list.

### G-3 · HIGH — Reward forgeries in the two largest weights
`spec_tracker.py:96-122`, `:131-152`; `scorecard.py:77-78`; `local_loop.py:279-301`

`spec_completion` (weight **0.45**) and `spec_proposed` (weight **0.40**) are the top two signals, together 0.85 of fitness.

- `new_ac_coverage` credits an AC by regex-matching `@pytest.mark.ac("SPEC-x/AC-n")` in a changed test file, never confirming the test is collected or run. Combined with **F6** below, an AC can be "proven" by a test the harness never executes.
- `proposed_specs`' docstring says *"NEW spec docs"* but the implementation **never consults `baseline_ref`** — touching an *existing* `docs/specs/*.md` with ≥2 AC checkboxes earns `spec_proposed = 1.0`. Content is never examined.

Worse, this is a designed loop: `BACKLOG` instructs the agent to author a spec (earning 0.40); the promoted spec's ACs are then surfaced by `spec_gaps` to the scout, which is told they are *"the single highest-reward move"*; the next cycle implements them (earning 0.45). **The loop is paid 0.40 to write its own next objective and 0.45 to carry it out, with the objective text authored entirely by the agent and never scanned.**

*Partial credit:* `format_gaps` emits only regex-constrained `SPEC-id/AC-n` tokens, so the *scout* prompt receives ids, not prose — real sanitization-by-construction worth preserving.

### G-4 · MEDIUM — Mutation probe: does not engage, and is budget-starvable
`mutation_probe.py:220-234`, `:255-256`, `:45-60`; `candidate_fitness.py:262-263`, `:669`

Does not engage at all when the candidate changes no test file (`available=False` → **no gate, no penalty** — so a pure source change is never probed), or when no *mutable site* exists on an added line. The operator set covers only single-op `Compare`, `BoolOp`, `Add/Sub/Mult`, and bool/numeric `Constant` — **string constants are not mutable sites**, nor is statement deletion, return replacement, `not` insertion, or handler changes. So:
```python
if os.environ.get("MAISTRO_RSI_GOAL"):
    return _bypass()
```
has zero mutable sites and is invisible.

**Budget starvation is deterministic:** `_build_plan` walks `sorted(new_source_lines.items())` and stops at 6. Put 8 trivially-killed numeric constants in a file sorting first (`maistro_evolve/audit.py`) and the payload in one sorting later (`maistro_rsi/quarantine.py`) — the budget is exhausted before the payload, score 6/6 = 1.0, gate PASS, `mutation_strength` 1.0 (weight 0.18). The code acknowledges it: *"omitted sites simply do not count toward the score."*

### G-5 · MEDIUM — `uncovered_new_lines` is computed and not enforced; the tolerance re-ratchets
`coverage_gate.py:148-162`, `:166`; `candidate_fitness.py:634`; `tdd_gate.py:148-149`

The exact set of added-but-never-executed lines is computed, then used **only** to withhold a reward. `coverage_gate.py:1-13` says *"a self-modification that adds untested code should be rejected outright."* It is not. And the 0.5 pp tolerance renews after every promotion (baseline re-ratchets at `local_loop.py:1767-1769`) — over 150 cycles that is a large silent accumulation.

### F6 · MEDIUM — The collectability gate's auto-root escape rewards tests the harness never runs
`candidate_fitness.py:128-139`, `:117-118`

`auto_roots` is derived from changed *source* paths, so a change under `maistro-core/src/` makes `packages/maistro-core/tests` a valid root — but the harness only runs `maistro-{evolve,rsi}/tests`. A test placed in `maistro-core/tests/` passes the location check and `--collect-only`, and **is never executed** — while still counting toward `count_net_new_tests`, `_mean_assertion`, and `new_ac_coverage` (the 0.45 signal). The docstring says *"A test the harness never executes… must not be rewarded."* It is.

### G-6 · HIGH — The LLM reviewer is injectable, blindfoldable, and structurally fail-open
`regression_judge.py:60-63`, `:66-83`; `local_loop.py:2099-2105`

```python
{"role": "user", "content": f"Target: {target}\n\nDiff:\n{diff_text[:8000]}"}
```

Both fields are candidate-controlled, with no delimiter and no scan.

- **Injection:** any comment or docstring in the diff addressed to the reviewer. The judge model is `scout_model or model` — in the shipped config, the free/cheap aliases least resistant to instruction-following. Warden is not on this path (K-3).
- **Truncation blindfold:** `[:8000]`, and `git diff` orders hunks by path. Add a >8 KB benign file sorting early and the payload hunk is **never shown**. No injection skill required.
- **Fail-open:** every failure path returns `0.7` against a `>= 0.4` threshold — `llm_call` raises, no `{...}` found, invalid JSON, or the outer `except Exception`. **The reviewer can only ever block by actively emitting < 0.4.** The parse is greedy `re.search(r"\{.*\}", DOTALL)`, so any diff containing braces — i.e. any Python diff — can supply a plausible verdict object.
- Second-order: `target` derives from the scout's instruction, which derives from module source the loop promoted in an earlier cycle. A comment landed in cycle N steers the reviewer in cycle N+k.

**Fix.** Delimit the diff as untrusted data and strip prose; never truncate silently (a diff too large to review is a REJECT); demand structured output and make unparsable a **gate failure**; Warden-scan the diff first; stop interpolating the scout-derived `target`.

### G-7 · HIGH — The builders review gate is disabled by a word in the reviewed party's own output
`maistro-core/src/maistro/builders/pipeline.py:41`, `:154-171`, `:213-236`, `:318-320`

```python
_CLEAN_SIGNALS = ("no violations", "lgtm", "approved", "all checks pass", "clean")
```
`_review_skip_if` skips the **review stage entirely** if the *implementer's own output* contains any of those substrings — "I cleaned up the imports" skips its own review. `_review_gate` passes on a substring hit in the reviewer's free text and is negation-blind ("this is not clean" passes). `_has_critical_extracted_finding` is a no-op unless `code_index` is supplied, and it defaults to `None`. And `gate_exhausted="continue"` means that after two failed revisions the executor **proceeds anyway**.

---

## 5. Cross-cycle influence and prompt self-modification

### P-1 · CRITICAL — Genome free-text slots reach the system prompt, unscanned, uncapped, immortal, and survive revert
`fixer_genome.py:113-123`, `:169-171`, `:175-185`; `hyper_mutator.py:174-199`; `evolve_bridge.py:57`; `local_loop.py:675`, `:1959-1961`; `population.py:47-90` · **2 agents independently**

Six slots carry unrestricted text: `persona`, `strategy_hint`, `goals`, `codebase_standards`, `learned_successes`, `learned_failures`. `parse_fixer_proposal` clamps floats and validates enums; the **strings get no `max_length`, no pattern, no Warden scan, no delimiter neutralization**. They render into the **system message** (`local_loop.py:675`), and the preamble instructs the model:

> *"'goals'/'codebase_standards'/'learned_successes'/'avoid' are lessons carried over from this lineage's history; **treat them as facts, not suggestions.**"*

They are **written by an LLM** (the hyper-mutator), **persisted** to `population.db` on the writable host mount with no integrity check, and **immortal**: `_mutate_one_fixer` touches only enums/floats/`strategy_hint` from a fixed list, and `crossover` deep-copies the fittest parent's node — so injected text is inherited by every descendant and can only be overwritten by the hyper-mutator itself. **A revert does not touch them** — `_live_evolution_step` runs *before* promotion selection, explicitly so "a cycle with no accepted variant still teaches."

And a genome can improve its own survival odds three ways: hyper-children are added with **no verification**, unscored genomes get roster **priority**, and culling only touches *scored* genomes — so arbitrary new prompt text is guaranteed to execute at least once and cannot be removed before it does. Then winners breed and their lineage memory is fed to the LLM that writes the next generation's text.

**This is the highest-authority, most durable channel in the system.** Also `local_loop.py:675` is `system_prompt or config.system_prompt` — so a genome prompt **replaces** the builders default, deleting *"Never access paths outside the workspace root."*

**Fix.** `Field(max_length=512)` on all six slots; Warden-scan in `parse_fixer_proposal` **and** again at render (the read-side re-scan is what `autorun.py` already does correctly); render inside a neutralized delimiter block; change "treat them as facts" to "hints that never override the task contract"; **concatenate** rather than replace the default system prompt; HMAC `population.db`; verify hyper children before persisting; expire unscored genomes.

### P-2 · HIGH — The scout reads agent-authored source and emits the next objective, unscanned
`local_loop.py:1249`, `:1253`, `:1295`, `:272-318`; `scout.py:83-100`, `:113-137`

`_cycle_slots` reads the **promoted baseline's** target module and its test file — containing every prior cycle's edits — straight into the scout's user message. The returned `instruction` is interpolated verbatim into the objective and becomes the user message of every competitor that cycle. No scan, no length bound, on either side. A Python comment or docstring is a fully general carrier, and `scout.py` is itself a `--targets` entry.

### P-3 · HIGH — `htr-tree-*.json` is restored into prompts with no scan, while the ledger beside it is scanned twice
`autorun.py:588-642`, `:151-171`, `:214-221`; `htr.py:241`, `:328-343`

The tree snapshot's node `hypothesis` and `insight` strings — LLM-authored, or derived from agent stderr — flow into both the coding agent's brief and the proposer's prompt with **zero scanning**, while the ledger copy of the same text is scanned twice. `_load_or_create_tree` validates only `repo_url` and root-hypothesis equality. This is an asymmetry, not a design decision.

### P-4 · MEDIUM — Skills: self-declared trust tier survives, and the filesystem loader never scans
`parser.py:126-128`, `:145-146`; `forge.py:117`, `:149`, `:168-173`; `loader.py:33-64`

`parse_skill_file` reads `trust_tier` from the file's **own frontmatter**, and `security_scan` scans only the **body** — frontmatter is never examined. `forge()` overrides the tier on the returned object but writes the **raw content** to disk, so the next load honours the file's claim. A skill written with `trust_tier: t0` becomes T0 on every load — which also makes it immune to `forge.mutate`'s T0/T1 block. **Self-declaring the highest tier also self-declares immunity to correction.** And `FilesystemSkillLoader.load_all` never calls `security_scan` at all.

Currently **latent** — not wired into the RSI loop and `FilesystemSkillLoader` has no production callers — but K-5's write primitive can drop a file in a skills dir today, and a skill outside the repo tree survives a revert.

### P-5 · HIGH — The resume path applies arbitrary patches with no gate
`local_loop.py:1494-1563`, `:2216-2218`; `:1077`

`_load_saved_patches` globs `export_dir/*.patch` and `git apply`s each with no provenance check, no signature, no manifest cross-check, **no test run, no fitness scorecard, no Warden scan**. The result is committed as `resume: reapply N saved patch(es)` and `_non_promotion_commits += 1` (absorbing it into O-9's integrity check), and `_last_reviewed_ref` is set to *post*-resume HEAD so it is **never** RLPHD-reviewed by design. It then lands in the export range for the next harvest.

`_excluded_from_export` is **in-memory only**, reconstructed empty each start. Today the revert exclusion is safe only because the checkpoint clears and rewrites `export/` *after* reverting — a property resting on comment-documented ordering. If the process dies in that window, the pre-revert export is still on disk and the resume path re-applies reverted, human-flagged work unreviewed.

**Fix.** Sign the manifest (HMAC over each patch's sha256); on resume refuse any `.patch` not listed with a matching digest; run the resume commit through the same gates; persist the exclusion set.

### P-6 · MEDIUM — Human approval is deleted before it can be used
`promotion_review.py:309-315`; `local_loop.py:2288`, `:2500-2502`

`resolve_review(..., "approve")` writes the re-queued patch into `export_dir`; the next checkpoint's `export_promotions(..., clear=True)` does `for stale in dest.glob("*.patch"): stale.unlink()`. If the run is still going, **the operator's approval is deleted with no log**, and `__main__.py:692-696` prints *"approved — patch re-queued for the next harvest"*, which is false. Harvest is manifest-driven and never globs, so the patch was undiscoverable regardless.

### Eval-awareness — the oracles available to candidate code

Because gate subprocesses inherit the full environment (K-5), candidate code can detect exactly which run it is in. Most specific first:

1. **`RSI_GOAL`** — set by the launcher; a unique "I am inside an RSI evaluation cycle" flag present in no other context.
2. **`PYTHONDONTWRITEBYTECODE` differential** — set by `tdd_gate.run_test_selection`, **not** by the main test run or the coverage run. A near-exact discriminator for "this is the red/green or mutation invocation."
3. **`sys.gettrace()` non-`None`** ⇒ under `coverage run`. One call.
4. **Source hash** — the decisive one. Red/green reverts the source; the mutation probe writes an `ast.unparse`d mutant, distinguishable by *formatting alone*. This is what K-6(a) weaponises.
5. `sys.argv` (`--collect-only`, `-p no:cacheprovider`, selector lists), `cwd` (`cycle-<N>-v<M>` leaks the cycle index), `git status` non-empty exactly during revert/mutant writes, relative four-entry `PYTHONPATH`, `PYTEST_CURRENT_TEST`.

**And the repo legitimises this idiom:** `builders/responses_callable.py:77-79` does `if os.environ.get("PYTEST_CURRENT_TEST"): return` — production code that deliberately behaves differently under test. A candidate copying that pattern is following in-repo precedent no linter or reviewer would question.

**Fix.** Minimal `env=` everywhere (K-5); set `PYTHONDONTWRITEBYTECODE` uniformly so it stops discriminating; randomise worktree paths; run red/green and mutation from a copy with git metadata stripped. None of this defeats a determined detector — hashing the source under mutation is unavoidable in-process — which is precisely why K-6's fix (don't execute candidate-supplied `conftest.py` during the gate runs) is the load-bearing one.

---

## 6. What is genuinely well built

Stating these plainly: they must not be weakened while fixing the above, and several are the *correct* pattern the broken paths should copy.

1. **The learnings ledger is the reference implementation.** `autorun.py` scans each insight at append and stores the verdict with the entry (`:737-743`), `recall()` drops flagged entries (`:462`), and it **re-scans at use time** (`:678-690`) with the reasoning written out: *"an entry tampered with after append (or written by an older version that never scanned) would otherwise ride straight into this run's prompts."* Both filters key on *any* flag, correctly avoiding the two-flag `blocked` threshold. `ledger_warden = Warden()` is unconditional; a scan exception crashes rather than passing. **This is exactly right, and it is the pattern P-1/P-2/P-3 need.** Its one residual weakness is inherited: Warden itself still misses combining-accent and encoded payloads (see the general audit §5.1), which makes that normalization gap load-bearing for containment.
2. **The shipped container is well-hardened and holds no GitHub credential.** `--cap-drop=ALL`, `no-new-privileges`, memory/cpu/pids caps, `--rm`, env file `:ro`, **repo baked into the image rather than host-mounted**, ~20 provider keys explicitly `unset`, and the free-router step split into a separate helper container so `OPENROUTER_API_KEY` never reaches the main run. `docker run` starts from a clean env with **no `GITHUB_TOKEN`** — so the container cannot push or open a PR itself. The trust boundary in `rsi_export_and_dispatch.sh:7-11` is correctly drawn *and* correctly documented.
3. **`rsi-harvest.yml` is a sound trust boundary.** Checks out the *trusted* ref rather than caller-supplied `export_ref`, pulls `.rsi-exports/` as **data only**, hard-fails if it holds anything but `*.patch`/`manifest.json`, and scopes to `contents: write` + `pull-requests: write` — **no merge, no admin**.
4. **`REPORT_DIR` is outside `/workspace`**, so the *agent's tools* cannot reach `population.db`/`rlphd_state.json`/`flagged/`. (K-5 defeats this for *test* code, not for the tool surface — the design intent is right.)
5. **The `/workspace`-vs-clone import boundary** means a candidate's gate edits do not take effect mid-run. The single most valuable containment property currently in place — and it is *implicit*, asserted nowhere. Make it explicit and tested.
6. **`create_rsi_sandbox` fails closed on unproven isolation** (`microvm.py:174-196`) — real evidence or a deliberately verbose attestation, else raise. And **no `load_dotenv` exists anywhere** (verified), so a candidate cannot set env vars by committing a `.env`.
7. **The builders sandbox has real path containment and env hygiene.** `LocalWorktreeSandbox._resolve` does `(root/path).resolve().relative_to(root)`; `SandboxedShell` rejects metacharacters *before* the blocklist, strips network URLs before the absolute-path scan so it cannot be confused, and `_SAFE_ENV` is a 4-key allowlist with no `os.environ` spread and deliberately no `HOME` (the comment correctly notes `$HOME/..` would be an escape). The Windows `TEMP`/`TMP` redirect into the sandbox is a real, non-obvious fix done right.
8. **`env_sanitize.sanitize_env` is a correct allowlist** with a value heuristic, already unit-tested — it just isn't called on the RSI paths.
9. **`maistro_rsi/sandbox/local.py` is the well-built sandbox** — `_resolve` resolves symlinks before comparing, and `exec` uses `start_new_session=True` + `os.killpg` with a bounded reap. Its docstring accurately states that `exec` has no containment and relies on sbx.
10. **`maistro_evolve/benchmarks/sandbox_exec.py` is the most honest module in scope** — scrubbed env, `killpg`, temp cwd, and a docstring stating plainly what it does *not* provide.
11. **`hyperlight_executor.py` is a faithful ADR-093 implementation** — ordered detection, `MODE_FLOORS` with autonomous requiring tier ≤ 2, explicit fail-closed refusal with no bare-subprocess fallback, base64-encoded config instead of f-string templating, and a correct bwrap argv. It is **unreachable from RSI and builders**, needs `--clearenv`, and its `_has_hyperlight` check is forgeable by a planted module — but the skeleton is right and is what the RSI path should wire to.
12. **`quarantine.py`'s design intent and matcher are both correct.** Refusing to carve out untouchable files and escalating instead is the right call. `matches_sensitive_pattern` does proper segment-boundary matching; `_normalize_touched_path` uses `removeprefix` rather than `lstrip("./")` with a note that the latter bug shipped once. `quarantine_scan` fails closed with `adversarial_review=None`. **The failures are the surface list, the input parser (K-3a), and the wiring (K-3) — never the gate logic.**
13. **`selfbranch.py:166-171`** — *"A missing quarantine check is a DENY, not a bypass."* Correct, and correctly reasoned in the comment.
14. **`scripts/check_enumerations.py` is the best-designed guard in the repo** — probes through the *real* matcher, detects dead patterns, and fails on *stale* baseline entries so the baseline cannot decay into an allowlist. Its weaknesses are scope (it names no gate or scoring file) and that its own authority lists are unprotected — not construction.
15. **Baseline integrity is careful:** fresh clone on `rsi-baseline` in a throwaway root, variants branch from the branch ref not the dirty tree, promotion is `merge --ff-only`, and `_check_persistence_integrity` is a genuine trust-but-verify reconciliation.
16. **`import_pipeline.py`** — scan → salvage → re-scan → forced T3 → content-hash `rescan_on_use`. Best-in-repo, with rug-pull defense.
17. **`marketplace._block_ssrf`** checks literal IPs *and* resolved addresses before any fetch — correctly blocks `host.docker.internal` and `maistro-litellm`.
18. **`SafetyGovernor`** has no fail-open path anywhere. (State is in-memory, so a restart clears its budget, and it governs only `capabilities/providers/self_repair.py` — not RSI.)
19. **No autonomous trigger exists for harvest** — `rsi-harvest.yml` is `workflow_dispatch`-only; no cron, no `on: push`, no self-dispatching workflow, no systemd unit. Verified across all 10 workflows. **Preserve this deliberately.**
20. **`docker.py`'s container flags are correct** — `cap-drop=ALL`, `no-new-privileges`, `pids-limit`, `tmpfs /tmp:noexec,nosuid`, memory/cpu, `--network=none` by default, UUID names. And the docker-socket mount was correctly removed from the default stack — ADR-093 Decision 2 actually honoured.
21. **`EvolutionConfig` hard caps** (`cycle.py:29-37`) — non-overridable pydantic ceilings framed as RSI safety bounds. Good pattern; extend it.
22. **Smaller, correct:** `_atomic_write_json` (tmp + `os.replace`); review-decision idempotency; `git apply` without `--reject` on resume so a conflicting patch writes nothing; `_git` uses argv lists with no shell interpolation; `git_commit` unstages `.env`/`*.pem`/`id_rsa` even when `add_all` matched them; `selfbranch.py:146-151` captures the staged diff *pre-commit* so quarantine sees a superset; `command_apply_patch` `shlex.quote`s prompt and model; a2a guest peers require operator-registered trust with no self-registration.

---

## 7. Detection: what you would actually see

Every finding above is a control gap. The complementary question — *if it happened anyway, what would you see?* — currently answers: largely nothing (O-6, O-7). These tripwires each detect a **class**, not an instance.

| Tripwire | Detects | Implementation |
|---|---|---|
| **Diff-scope invariant** | Any cycle touching a file outside `{target, its test}` | G-2's veto gate, emitting a SECURITY event on violation |
| **Containment-surface delta alarm** | Any change matching `SENSITIVE_PATH_PATTERNS`, on **every** path | K-3's wiring, alerting even when the diff is cleared |
| **Gate-census assertion** | Gates vanishing (G-1) | Observed gate set must equal the mandatory set; shortfall blocks and alerts |
| **Header/path-count equality** | K-3a's lossy parse | Fail closed when `diff --git` headers ≠ extracted paths |
| **Signed trace-note chain** | Record rewriting (O-8), promotions with no record | HMAC + prev-hash; `read_campaign` reports `MISSING_NOTE` gaps |
| **Cycle-record heartbeat** | Logging silently stopping (O-7) | Assert observed cycle records == `len(result.cycles)` at checkpoint |
| **Ref-creation watch** | K-2 and any unexpected ref | Alert on any tag or non-`rsi/*` branch created by the loop's identity |
| **Gate-state integrity** | K-5's `rlphd_state.json` poisoning | HMAC the file; refuse to load on mismatch instead of cold-starting |
| **Gateway spend curve** | K-4 and G-1's exhaustion-as-cover | Per-key `max_budget` + alert on model-name cardinality outside the roster |
| **Reverted-vs-reported reconciliation** | O-4, O-5 | Compare `flagged/`+`kept/`+`_excluded_from_export` against the report's count |

Two principles behind these, each violated somewhere above:

- **Never assert a control's outcome; observe it.** Stop reports `"stopped"` without checking (K-1); the PR body asserts gates that never ran (G-1); a docstring asserts a budget cap that does not exist (K-1a); `scan_server` returns hardcoded `"clean"`. Each is a one-line lie that costs the operator their model of the system.
- **Absence must be loud.** A missing gate (G-1), a missing trace note (O-8), a missing audit record (O-2), and a missing log line (O-7) are all currently indistinguishable from success. In a system whose purpose is self-modification, **silence is the expected signature of a problem** — so every control needs a positive liveness signal, not a failure signal.

---

## 8. Remediation, ranked by capability reduction per line changed

**Tier 0 — before the next unattended run.**

1. **Make Stop stop (K-1).** `threading.Event` checked at the cycle top and before each promotion merge; report `stopped` only after the task completes; add a filesystem stop-flag. *Nothing else is safe to rely on until intervention works.*
2. **Delete the `"*"` LiteLLM passthrough and issue a budgeted, model-scoped virtual key (K-4)** — inverting `_API_KEY_ALIASES` priority **first**, or the fix is silently undone. Single highest-leverage change; collapses the resource-acquisition surface.
3. **Validate the push refspec (K-2a)** — ~4 lines. **And gate `release-installer.yml` (K-2b)** — independent; do both.
4. **`env=sanitize_env(...)` on every subprocess in `local_loop.py` and `candidate_fitness.py`; add `USER` to `Dockerfile.rsi-runner`; stop mounting `gateway.env` as a readable file (K-5).** The allowlist already exists and is tested.
5. **Wire `quarantine_scan` into `_fitness_decision` and `_harvest` (K-3), and fix `paths_touched_by_diff` to use `--name-only -z` with a fail-closed count check (K-3a).** One insertion point each; `quarantine.py` already fails closed correctly.
6. **Remove the gate/scoring/PR files from `TARGETS`; restore `--promotion-review` as the launcher default (E-1).** Two lines.

**Tier 1 — before treating the loop as trustworthy.**

7. Reject diffs touching `conftest.py`/`pyproject.toml`/`pytest.ini`/`.coveragerc`/`ruff.toml`/`.bandit`/`.gitignore`; score from `git archive HEAD`; absolute `PYTHONPATH` + `PYTHONNOUSERSITE=1` (K-6).
8. Parse machine-readable gate results, never exit codes or empty-output-means-clean; a tool that errored is a **FAIL** (K-6, G-1). Mandatory gate census.
9. `scope_respected` veto gate + non-Python deny-list (G-2).
10. Budget bounds that fail closed; `next_model` halts on exhaustion; delete the false docstring (K-1a).
11. Length-bound, scan (both sides), and delimiter-isolate the six genome text slots; **concatenate** rather than replace the default system prompt; HMAC `population.db` (P-1).
12. Fix the reward forgeries: `proposed_specs` must compare against baseline; `new_ac_coverage` must resolve against a real parsed spec **and** a test the harness actually executed (G-3, F6).
13. Harden the regression judge: delimit, never truncate silently, structured output, unparsable ⇒ block (G-6). Replace `_CLEAN_SIGNALS` with a structured verdict; `gate_exhausted="fail"` (G-7).
14. Full diff for any human approval; record and verify the baseline sha (O-3).
15. `permissions: contents: read` on the four workflows; repo default read-only; cage-guard covers itself and the gate substrate (E-2).
16. Delete `_seed_audit_log`; persist and hash-chain the audit log; audit every RSI lifecycle action (O-2).

**Tier 2 — record integrity, honesty, and the long tail.**

17. Signed chained trace notes; `write_trace_note` failure blocks promotion (O-8). Report renders after the review pass with a flagged/reverted section (O-4). Revert failure flags and excludes; supersession queued not skipped (O-5).
18. Signed export manifest; gate the resume commit; persist `_excluded_from_export` (P-5). Approved patches into a `approved/` dir `clear` does not touch (P-6).
19. Scan `distilled_insights` and the scout's source/instruction inputs — port the ledger's double-scan pattern (P-2, P-3).
20. Real per-gate results in the PR body; list **every** changed path; retest harvest branches (G-1, K-3).
21. SECURITY events + a notifier something reads; `configure_logging` from entrypoints at `INFO` (O-6, O-7). Persistence check from the signed chain (O-9).
22. Make `uncovered_new_source_lines` a gate; tighten the re-ratcheting tolerance (G-5). Per-file mutation budget + string/statement operators (G-4). Validate collectability against the *real* test roots (F6).
23. Derive skill trust tier from provenance, never frontmatter; scan frontmatter; `load_all` scans (P-4).
24. `report_dir` outside `work_root` with startup validation; forward `isolation` from the conductor route; confine or delete the duplicate `local_loop.LocalSandbox`.
25. **Correct the documentation that will cause misplaced trust:** `SECURITY.md:37` (names a layer with no implementation and no callers), ADR-093's status vs. the `local` default, `container_sandbox.py`'s ADR-093 claim, `security/patterns.py:56-58` (cites ADR-058, which is A2A delegation, not sandboxing), and `quota_burn.py:96-97`'s nonexistent budget cap.

**Structural, and the one that outlasts the list:** the containment decision is currently made by code inside the mutable tree, reading untracked host state (`os.environ`, `os.path.exists`). No pattern-list tuning closes that. **Move the tier decision to a host-side supervisor the loop cannot edit or observe** — one that chooses the backend, injects an unforgeable attestation, and starts the loop already inside the boundary. And **invert the sensitive-path list**: a denylist will always lag an adversary that reads it; compute the boundary-relevant set from a manifest covered by `cage-guard.yml`-style hard rejection, and treat any diff outside an explicit allowed-to-edit list as sensitive.

---

## 9. Limits of this review

- Seven agents; every Critical was re-verified by hand or by execution. K-6's sub-findings were **executed** against real pytest/ruff/coverage; K-3, K-3a, and the `_seed_audit_log`/`stop_run`/`git_push`/`release-installer`/`litellm_config` findings were read directly at the cited lines.
- **Agents initially disagreed about "the default path."** That disagreement was real and is resolved in §1: three entry points, three different containment postures. Statements about "no containment" apply to the direct-CLI and conductor paths, **not** to `run_rsi_isolated.sh`.
- **Depends on unverifiable configuration:** branch protection, tag protection, and the repo's default workflow permissions are GitHub settings, not code. `SPEC-231:72` states no tooling automates branch-protection config; `ci.yml:197` says the same for required checks. Given [#288], treat the merge gate as **approval-only with no reliable check enforcement on `develop`**. K-2 and E-2's CI-execution consequence hold regardless of both.
- **`maistro-rsi` and `maistro-evolve` have no CI coverage floor and no CI mutation testing** — `quality.yml`'s gates are scoped to `maistro-core/src`, and `mutation.yml`'s `paths:` filter excludes both packages. The gate substrate is the least-tested code in the tree.
- No fix here is implemented or tested. Line numbers are `develop` @ `08ef547`.
