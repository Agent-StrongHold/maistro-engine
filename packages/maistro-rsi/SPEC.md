# maistro-rsi — Spec & Acceptance Criteria

Recursive self-improvement: an agent that branches, patches, tests, and
benchmarks its own codebase inside an isolated sandbox, with results scored
through the shared `maistro-evolve` Elo tournament.

**Current path distinction:** Sections 1-6 describe the legacy compatibility
`RsiCycle` path and its tests. That path is not approved for autonomous
untrusted execution because it still contains Docker-as-microVM and host-Git
architecture. The approved installed path is specified in
`docs/specs/SPEC-203-autonomous-rsi-campaign.md`.

Each section below is a human-readable behavior spec. Acceptance criteria are
numbered `<module>-<n>` and every test in `tests/` must reference the AC(s) it
verifies in its docstring — no test exists without a traceable AC, and no AC
ships without a test.

---

## 1. MicroVM sandbox (`protocols.py`, `sandbox/microvm.py`)

**Spec:** RSI code never talks to a concrete sandbox technology directly — it
depends on the `MicroVmSandbox` protocol. A Docker-backed implementation
(`DockerMicroVmSandbox`) makes the package runnable today; a real microVM
backend (Firecracker/E2B/gVisor) can replace it later by satisfying the same
protocol, with zero changes to call sites.

| AC | Criterion |
|----|-----------|
| sandbox-1 | `DockerMicroVmSandbox` satisfies the `MicroVmSandbox` protocol (structural check via `isinstance`). |
| sandbox-2 | `exec(command)` runs the command inside the underlying container and returns `(exit_code, output)`. |
| sandbox-3 | `write_file` followed by `read_file` round-trips file content through the sandbox workspace. |
| sandbox-4 | `snapshot(label)` returns a unique id each call, even for the same label (no collisions across concurrent attempts). |
| sandbox-5 | `restore(snapshot_id)` raises `KeyError` for an id that was never captured, and `NotImplementedError` for a real one — the Docker backend cannot resume paused state, and must say so rather than silently no-op. |
| sandbox-6 | `destroy()` tears down the underlying container exactly once. |
| sandbox-7 | Used as `async with`, the sandbox is destroyed on exit (success or exception) — no leaked containers. |

---

## 2. Quarantine gate (`quarantine.py`)

**Spec:** Recursive self-improvement that can't touch its own scaffolding
isn't recursive — so `maistro-rsi` does **not** ban agents from proposing
changes to harness, sandbox, or security code. Instead, *every* self-diff,
regardless of what it touches, is scanned by Warden (the same content scanner
used at every other trust boundary) before it's allowed out of the sandbox as
a PR. Diffs that touch declared "sensitive surface" — the agent's own cage:
sandbox control, security wiring, the self-branch/runner pipeline itself — are
not blocked outright, but are escalated to require an *additional* adversarial
(red-team-style) review pass on top of Warden + the full test suite. The
property we want is "nothing self-modified reaches the outside world unscanned
and unreviewed," not "some files are permanently off-limits."

| AC | Criterion |
|----|-----------|
| quarantine-1 | `quarantine_scan` returns `cleared=False` whenever the Warden verdict for the diff is not clean — a flagged diff never clears quarantine, regardless of which files it touches. |
| quarantine-2 | A diff that touches none of `SENSITIVE_PATH_PATTERNS` and passes the Warden scan clears with `requires_adversarial_review=False`. |
| quarantine-3 | A diff that touches *any* sensitive-surface path — even just one file alongside unrelated changes — sets `requires_adversarial_review=True`, regardless of the Warden verdict. |
| quarantine-4 | `cleared` is `True` only when the Warden scan is clean **and** (the diff doesn't require adversarial review **or** an adversarial review verdict was supplied and passed). A pending/missing adversarial review on a sensitive-surface diff must never clear. |
| quarantine-5 | `flags` on the returned verdict surfaces the Warden flags verbatim — quarantine never swallows or summarizes *why* something was held, since that trail is what a human reviewer acts on. |

---

## 3. Self-branch workflow (`selfbranch.py`)

**Spec:** Given a target repo and a test command, the workflow clones the repo
into the sandboxed workspace, creates a uniquely-named branch, hands control to
an agent-supplied `apply_patch` callback, commits, runs the test command
*inside the sandbox*, runs the diff through the injected quarantine check, and
— only if tests pass **and** quarantine clears — opens a draft PR. A
self-modifying agent does not get to propose changes to its own codebase that
fail its own test suite, nor to ship anything (including changes to its own
harness) that hasn't been scanned and, where warranted, adversarially reviewed.

| AC | Criterion |
|----|-----------|
| selfbranch-1 | `new_attempt(repo_url, test_command)` produces a branch name that is unique per call (no two attempts collide). |
| selfbranch-2 | A failed clone short-circuits the workflow: no branch/patch/test/PR/quarantine steps run, and the result carries a non-`None` `error`. |
| selfbranch-3 | On a successful clone, the workflow calls `git_branch`, then `apply_patch`, then `git_commit`, in that order, before running tests. |
| selfbranch-4 | `tests_passed` is `True` iff the sandboxed test command exits `0` *and* no error was recorded — a clone failure must never read as "tests passed". |
| selfbranch-5 | A PR is opened (`github_create_pr` invoked, `pr_url` populated) only when `open_pr=True`, the test command exits `0`, and a supplied quarantine check returns a cleared verdict. Missing quarantine, failing tests, or an uncleared verdict must never produce a PR. |
| selfbranch-6 | The returned `diff` reflects `git diff` output captured after the patch is applied and committed. |
| selfbranch-7 | `paths_touched_by_diff` extracts every `a/...`/`b/...` path named in a unified diff's `diff --git` headers, de-duplicated and in first-seen order. |
| selfbranch-8 | The `quarantine` field on the result carries the verdict `quarantine_check` returned, so callers can inspect *why* a change was held without re-deriving it. |

---

## 4. Quota-burn scheduling (`quota_burn.py`)

**Spec:** The scheduler discovers models from the connected LiteLLM instance
and routes each RSI cycle toward whichever model currently has the most idle
free-tier headroom, so unused allowances get exercised before they expire —
without ever recommending a model whose tracked usage already exceeds its
configured free-tier budget.

| AC | Criterion |
|----|-----------|
| quota-1 | `rank_models_by_headroom` orders models by **descending** remaining headroom (`free_tokens * (1 - used_pct)`), most idle first. |
| quota-2 | A model with recorded usage above its configured `free_tokens` ranks at the bottom (zero/negative headroom clamps to zero — never goes negative). |
| quota-3 | `QuotaBurnScheduler.next_model([])` returns `None` — an empty model list is not an error, it's "nothing to schedule". |
| quota-4 | `QuotaBurnScheduler.next_model(models)` returns the model `rank_models_by_headroom` ranks first, given the same tracker state. |
| quota-5 | `record_attempt` attributes usage to the model's **provider** (the `provider/model-name` prefix), so subsequent ranking reflects the recorded consumption. |

---

## 5. SWE-Bench Pro adapter (`benchmarks/swebench_pro.py`)

**Spec:** Scores a candidate's ability to produce *coordinated, multi-file*
fixes — the defining trait that separates SWE-Bench Pro from the original
SWE-bench (avg. ~107 lines across ~4 files per task). A patch that only
touches one file on an inherently cross-cutting bug is, by construction,
incomplete and must score lower than one that addresses every affected file.

| AC | Criterion |
|----|-----------|
| swebench_pro-1 | `run_swebench_pro` returns an `EvalResult` with `benchmark="swebench_pro"` and `samples_evaluated == len(SWEBENCH_PRO_SAMPLES)`. |
| swebench_pro-2 | A response that references every file listed in a sample's `files` scores strictly higher (via `_score_multi_file_fix`) than a response that references only one of them, all else equal. |
| swebench_pro-3 | A response containing none of a sample's `expected_keywords` and no code block scores at or near `0.0`. |
| swebench_pro-4 | `load_remote_samples()` raises `NotImplementedError` — it is a documented extension point, not a silent stub that returns empty data. |

---

## 6. RSI cycle runner (`runner.py`)

**Spec:** One cycle wires the pieces end-to-end: pick a model by quota
headroom, run a self-branch attempt in a sandbox, evaluate *both* the baseline
and candidate genomes against the configured benchmark suite, and record one
Elo battle per shared benchmark. `improved` is the single boolean that decides
whether a self-modification is allowed to stand: it requires both a passing
test suite *and* a benchmark majority — passing tests alone is not enough to
call a change an improvement, and winning benchmarks with a broken build is
not improvement either.

| AC | Criterion |
|----|-----------|
| runner-1 | `RsiCycle.run` evaluates both `baseline` and `candidate` genomes on exactly the benchmarks named in `RsiCycleConfig.benchmarks`. |
| runner-2 | One `GenomeBattle` is recorded per benchmark present in **both** result sets; benchmarks present in only one are skipped, not battled against a missing score. |
| runner-3 | `benchmarks_won` counts only battles the candidate (`genome_b`) outright won — draws and baseline wins do not count. |
| runner-4 | `improved` is `True` only when `branch_result.tests_passed` is `True` **and** `benchmarks_won` is a strict majority of `battles`; either condition failing makes it `False`. |
| runner-5 | The sandbox is destroyed even when `apply_patch` or evaluation raises — no leaked containers on a failed cycle. |
