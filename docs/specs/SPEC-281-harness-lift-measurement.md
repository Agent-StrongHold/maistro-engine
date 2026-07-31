---
id: SPEC-281
title: "Harness lift measurement — model×harness matrix, gap closure, transfer testing, and post-cutoff task generation"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-07-30
substrate:
  - maistro-engine#SPEC-202
implements: []
related: []
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Evolve
owners:
  - '@BlakeMatthews-dev'
history:
  - status: Proposed
    date: 2026-07-30
---

# SPEC-281: Harness Lift Measurement

## Problem

The product claim for this engine is not "our genome scores X on benchmark Y."
It is: **a weak model inside this harness performs close to a frontier model
inside a plain one — and when you put a frontier model in, it goes further
still.**

No benchmark score can express that claim, and SPEC-202's adapters — however
honest their graders — do not measure it. `EvalResult.score` is a single number
for one (genome, benchmark) pair. The claim is about a *difference between
configurations*, which means the unit of measurement has to change.

Three failures follow from measuring scores instead of lift:

1. **Benchmark selection goes wrong.** Judged as absolute scores, IFEval and
   BFCL look near-saturated (frontier models reach ~85–92%) and therefore
   worthless. Judged as lift over a *weak* model, they have enormous headroom —
   a small model tracking five simultaneous constraints fails often, and a
   verification pass in the harness fixes much of it. Saturation is a property
   of the population being measured, not of the benchmark.

2. **The wrong benchmarks look attractive.** GPQA-Diamond and HLE are excellent
   instruments for ranking frontier labs and near-useless here, because the
   weak→frontier gap on them is *knowledge the weak model does not have*. No
   harness supplies graduate chemistry. The selection criterion is not "is it
   hard" or "is it unsaturated" but **"is the gap harness-addressable?"**

3. **Overfitting to the weak model goes undetected.** This is the serious one.
   Scaffolding that rescues a weak model — forced decomposition, retry loops,
   mandatory verification, tight output constraints — routinely *hurts* a strong
   model by constraining reasoning it would have done better unaided. Harness
   and model capability interact; they do not add. An optimizer that only ever
   sees the weak model will happily evolve a harness that inverts on the swap,
   and the current design would not notice until someone tried it.

The inverse failure is documented too: OpenAI found their ARC-AGI-3 harness was
discarding the model's reasoning between steps, and enabling two settings
(retained reasoning, compaction) took GPT-5.6 Sol from 13.3% to 38.3% with ~6×
fewer output tokens. Same lesson from the other direction — the harness, not the
model, was the binding constraint, and nothing in the score alone revealed it.

## Design

### 1. The unit of measurement is a cell in a model×harness matrix

Every measurement names both axes. Minimum viable matrix, per benchmark:

|                     | baseline harness | evolved harness |
|---------------------|------------------|-----------------|
| **weak model**      | `W_base` (floor) | `W_evo` (the claim) |
| **frontier model**  | `F_base` (ceiling) | `F_evo` (the transfer test) |

Derived quantities, all reported, none inferred by the reader:

```
lift          = W_evo - W_base                     # what the harness added
gap           = F_base - W_base                    # what there was to close
gap_closure   = lift / gap            if gap > 0   # the headline claim
transfer      = F_evo - F_base                     # does it help the strong model too?
inversion     = transfer < 0                       # does it HURT the strong model?
```

`gap_closure` is the product claim. `transfer` is the honesty check on it.

**`gap <= 0` invalidates the cell, it does not zero it.** If the weak model
already matches or beats the frontier model on a benchmark, that benchmark has
nothing to say about harness lift and must be reported as `gap_closure: null`,
never as `0.0` or `1.0`. A benchmark where the models are indistinguishable is
a benchmark that cannot measure this.

### 2. Transfer is part of fitness, not a post-hoc report

A genome's fitness must include the frontier cell, because an optimizer only
optimizes what it is scored on. Two rules:

- **Inversion is a hard gate, not a penalty.** A genome where `transfer < 0` by
  more than noise cannot breed, regardless of how large its `lift` is. This is
  the same lexicographic-veto shape already used for security in the quality
  model: a harness that damages the frontier model is not a better harness that
  costs something, it is a disqualified harness.
- **Transfer is sampled, not run every cycle.** Frontier evaluation is the
  expensive cell. Run it on a schedule (every N generations) and on every
  promotion candidate, not on every genome in the population. Between samples,
  carry the last measured `transfer` forward and mark it stale — a stale
  transfer is still evidence; an absent one is not.

Recording `inversion` requires no new machinery: it is a `gate_failures` entry
in `FitnessComponents`, which already blocks breeding.

### 3. Benchmark selection criterion: harness-addressable gap

A benchmark earns a place in the driver set only if the weak→frontier gap is
attributable to something a genome can change — planning, decomposition,
verification, tool-call construction, context management, retry policy — rather
than to knowledge or raw capability the harness cannot supply.

| Benchmark | Gap is mostly | Role |
|-----------|---------------|------|
| SWE-bench (Pro) | localization, test-run loops, context management | driver (flagship) |
| τ-bench | multi-turn reliability, policy adherence | driver |
| IFEval | tracking multiple simultaneous constraints | driver *in the weak regime* |
| BFCL | schema adherence, parameter correctness | driver *in the weak regime* |
| repo git-history tasks (§4) | real localization + patching in this codebase | driver (contamination-proof) |
| SimpleQA | calibration — knowing when to decline | secondary |
| GPQA-Diamond, HLE | **knowledge the weak model lacks** | excluded |
| ARC-AGI-2 | fluid intelligence; also ~$30/task | excluded on cost and addressability |

IFEval and BFCL are marked *in the weak regime* deliberately: as the population's
models improve, both approach ceiling and their `gap` shrinks toward zero, at
which point rule 1 retires them automatically by reporting `gap_closure: null`.
The criterion is self-maintaining; no one has to remember to demote them.

### 4. Post-cutoff task generation from this repository's own history

The strongest contamination defence available is chronological: a task created
after a model's training cutoff cannot have been memorised. Every bug fixed in
this repository is such a task, and unlike every public corpus it costs nothing
to obtain and gets *fresher* over time instead of saturating.

**Task construction.** Walk `git log` for commits that (a) touch at least one
file under `packages/*/src/`, (b) touch at least one test file, and (c) whose
parent commit fails the touched tests while the commit itself passes. That last
condition is the whole game — it is verified by execution, not inferred from the
commit message, so "fix" commits that fix nothing are excluded automatically.

Each surviving commit yields:

```
task_id        = <sha>
repo_state     = <parent sha>          # check out the parent; the bug is present
failing_tests  = [<nodeids>]           # collected from the parent, must fail
issue_text     = <commit subject + body, stripped of the diff>
gold_patch     = <the commit's diff>   # for reference/reporting only, never shown
```

Scoring is SWE-bench's: apply the genome's patch to `repo_state`, run
`failing_tests`, require pass; then run the surrounding suite and require no new
failures. `benchmarks/sandbox_exec.py` already provides process-level isolation
for exactly this shape of check.

**Cutoff discipline.** Each task records its commit date. A task is only valid
for a given model if its date is after that model's training cutoff, so the
generator takes a `not_before` date and the model roster carries cutoffs. A task
that predates the model under test is contaminated *for that model* and must be
excluded from its score rather than silently included.

**Honest limits, stated because this benchmark is home-made and will be quoted:**

- It is **not comparable to anything published.** No `official_comparable` flag
  can ever be true here. It measures ability to fix bugs in *this* codebase.
- Its difficulty is uncontrolled and drifts with the repo. Absolute scores are
  not comparable across time; only same-snapshot comparisons between genomes are
  meaningful. Pin the task set by commit range for any comparison that matters.
- **The RSI loop must not generate its own exam.** Task generation runs on the
  supervisor side from a pinned commit range; `benchmarks/` and the generator
  are already on `SENSITIVE_PATH_PATTERNS`, and the generated corpus must be
  checksum-pinned like every other exam (SPEC-202 §3a).
- Small samples. This repo will yield tens of tasks, not thousands. Report
  `samples_evaluated` prominently and never quote a percentage without it.

### 5. Harness parameters become first-class evolvable slots

The ARC-AGI-3 result is evidence that context-management settings can dominate
model choice. Whatever the gateway exposes — reasoning retention across turns,
context compaction vs truncation, tool-result trimming, retry policy — belongs
in the genome's typed slots alongside model and temperature, and belongs in
`EvalResult.metadata` so a score is never ambiguous about the configuration that
produced it.

**A score without its harness configuration attached is uninterpretable**, by up
to the 3× the ARC-AGI-3 case demonstrated. `official_comparable` already stamps
corpus coverage; harness configuration needs the same treatment.

## Acceptance criteria

- `AC-1` A benchmark result carries both axes (model id, harness/genome id) and
  the four matrix cells are individually addressable.
- `AC-2` `gap_closure` is `null`, never a number, when `gap <= 0`.
- `AC-3` A genome with `transfer < -epsilon` fails the hard gate and cannot breed,
  with the reason surfaced in `gate_failures`.
- `AC-4` Transfer measurement may be stale but never absent for a promotion
  candidate; staleness is recorded in metadata.
- `AC-5` The git-history generator emits only commits whose parent fails and
  whose tip passes the named tests, verified by execution.
- `AC-6` Every generated task records its commit date, and tasks at or before a
  model's training cutoff are excluded from that model's score.
- `AC-7` Generated corpora are checksum-pinned and load-verified, and no result
  from them sets `official_comparable`.
- `AC-8` Harness configuration appears in `EvalResult.metadata` for every real
  adapter.

## Out of scope

- ARC-AGI, GPQA-Diamond, HLE, MMMU (see §3 — excluded on addressability or cost).
- LiveBench-style refreshed corpora as a *fitness* signal. A corpus that changes
  monthly cannot produce comparable scores across cycles, which is the whole
  basis of SPEC-202's pinning. Fresh questions belong in a periodic audit run
  *outside* the loop, where pinned-rising-while-fresh-flat is the contamination
  signature — one level above the train/holdout split, and the only detector
  that catches pretraining contamination rather than harness overfitting.
- Replacing the existing proxy adapters. This spec changes how results are
  *interpreted and combined*, not how any individual benchmark is graded.
