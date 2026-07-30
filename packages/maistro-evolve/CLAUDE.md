# CLAUDE.md — maistro-evolve

This file provides guidance to Claude Code (claude.ai/code) when working in `packages/maistro-evolve/`.

Elo tournament optimizer for agent self-improvement: evaluate genomes against benchmarks, run battles, cull,
breed, and check diversity.

## Test loop

```bash
PYTHONPATH=packages/maistro-core/src:packages/maistro-evolve/src pytest packages/maistro-evolve/tests/ -v
```

**Gotcha:** maistro-evolve is NOT in the root pytest testpaths — you must give the explicit path (or run the
`/verify-evolve` skill, which runs the canonical command). It needs maistro-core on PYTHONPATH.

## Key pieces (import-and-use; no top-level CLI)

- `crossover()` — recombine two `PipelineGenome`s, preserving the entry node.
- `mutate_all()` — mutate models, strategies, prompts, topology within a genome.
- `fitness.compute_fitness()` — weighted score: eval 65% / cost 15% / latency 10% / diversity 5% / elo 5%.
- `EloTournament` — win/loss/elo per (genome, benchmark) pair.
- `EvalHarness` — registers/runs benchmarks (ifeval, bfcl, swebench, tau_bench, gaia, ragas, terminalbench, osworld).
  See **Benchmark fidelity** below before trusting any score from it.
- `EvolutionCycle` — orchestrates evaluation → battles → culling → breeding → self-improve → diversity, driven by `EvolutionConfig`.
- `reflective_improve()` (reflect.py) — GEPA/MIPROv2-inspired self-improve step: re-runs the weakest benchmark
  for failure traces, proposes K prompt candidates via grounded meta-prompts with randomized tips, re-evaluates
  each, and only an improving candidate enters the population — as a child genome, never overwriting the parent.

## Benchmark fidelity — stability statement (SPEC-202)

**Exactly one benchmark runs the official harness against the official dataset: `ifeval`, via the separate
`run_ifeval_real` adapter** (`benchmarks/ifeval_real.py` — the published 541-prompt corpus graded by Google
Research's own vendored verifier). It is reached through `EvalHarness(benchmark_fidelity="real")`, **not** by
the default `ifeval` entry, which remains proxy. See "Real tier" below.

**`bfcl`, `swebench`, `tau_bench`, `gaia`, `ragas`, `terminalbench` — and the default `ifeval` — do not.**
They score real model output, against real criteria, at a lite/handcrafted scale (`benchmarks/datasets.py`) —
a genuine but small-scale version of the real methodology, not the official harness. The names match the
industry-standard evals; the *scale* does not. This exists to save time/money and produce Pareto (cost vs.
quality) signal cheaply, and is shipped, supported v1 behavior. `osworld` is not implemented at all — see
below.

**There is no `stub` tier.** A benchmark either evaluates a real model response against real criteria
(`proxy`), or it does not run at all — every proxy runner raises `ValueError` if called with `llm_call=None`
rather than falling back to keyword heuristics or a fabricated score. `EvalHarness(benchmark_fidelity="stub")`
(or any value other than `"proxy"`/`"real"`) raises `ValueError`.

Two fidelity tiers, carried as `EvalResult.metadata["fidelity"]` and on `EvalHarness.fidelity`:

| Tier | What it means | Trust for promotion |
|------|---------------|---------------------|
| `proxy` | Lite-scale but genuine scoring against handcrafted samples — real rule verification, exact-match, tool-call matching, or real sandboxed execution — **what every registered benchmark ships today** | Development only. This is the default (`EvalHarness(benchmark_fidelity="proxy")`). |
| `real` | Official harness against the official dataset | **`ifeval` only.** `EvalHarness(benchmark_fidelity="real")` registers the real registry *and nothing else* — one benchmark, not seven. It does not backfill the remaining six from the proxy registry, and asking it for one of them raises. |

Per-benchmark methodology at the `proxy` tier:
- **`ifeval`/`bfcl`/`ragas`/`tau_bench`**: real rule/keyword/tool-call verification against handcrafted samples.
- **`gaia`**: exact-match against handcrafted Q&A, with an LLM-as-judge fallback.
- **`swebench`**: candidate code actually executes in a real sandboxed subprocess (`benchmarks/sandbox_exec.py`
  — `asyncio.create_subprocess_exec`, `start_new_session=True`, process-group kill on timeout) and is asserted
  against the real expected value. Process-level isolation only — see that module's docstring before reusing
  it elsewhere.
- **`terminalbench`**: delegates to `executable_terminal.py`'s real tempdir-based filesystem-state verification
  (a restricted JSON action language, not a real shell). Its train/holdout split is **reported, not enforced**:
  `_TASKS` is `TRAINING_TASKS + HOLDOUT_TASKS`, so the headline `score` is contaminated by construction and is
  **not eligible for a capability bonus**. What you get is observability — `metadata` carries `train_score`,
  `holdout_score`, `train_samples`, `holdout_samples` and `generalization_gap`, so *train rising while holdout
  stays flat* (the memorization signature) shows up instead of being averaged away. Withholding the holdout
  from fitness waits on a corpus big enough to drive a cycle from 3 tasks' worth of signal.
- **`osworld`**: **not registered.** `run_osworld` raises `NotImplementedError` — no desktop-VM/GUI-automation
  infrastructure exists in this repo. Reference task definitions remain in `datasets.py` for when that lands.

### Real tier — `ifeval` only (`benchmarks/ifeval_real.py`)

```bash
uv pip install 'maistro-evolve[ifeval]'                   # absl-py, immutabledict, nltk, langdetect
python3 -c "import nltk; nltk.download('punkt')"          # pre-fetch: the scoring container is network-denied
python3 scripts/vendor_ifeval.py --check                  # verify the grader/corpus match their pinned hashes
```

The official corpus and verifier are **vendored** under `benchmarks/third_party/ifeval/` (Apache 2.0, see its
`NOTICE`), reproduced by `scripts/vendor_ifeval.py` and pinned by sha256. They live in git rather than being
fetched at runtime for three reasons: `benchmarks/` is on `SENSITIVE_PATH_PATTERNS` so a diff editing the exam
is escalated; a score is only comparable across cycles if the exam is byte-identical across cycles; and the
scoring container has no network. `--check` runs in `quality.yml` and fails if the grader was hand-edited.

The vendored tree is **excluded from ruff and mypy** (root `pyproject.toml`). That is deliberate: its value is
being byte-comparable to what Google published, and reformatting it would make it our grader wearing the
official grader's name.

Things to know before quoting a number from it:

- **`score` is prompt-level strict.** All four official metrics (`prompt_level_{strict,loose}`,
  `instruction_level_{strict,loose}`) are in `metadata`, because papers quote different ones.
- **`official_comparable` is the flag that matters.** True only for a full, unsampled `split="all"` run with
  zero errors. `max_prompts` (cost control) and `split` both cover a subset, so both set it False. Don't
  compare a sampled run to a leaderboard.
- **Train/holdout is enforced here**, unlike terminalbench: `split="train"` (~411 prompts) is what the loop's
  fitness may see, `split="holdout"` (~130) is the supervisor's. Both sides carry all 25 instruction types —
  the split hashes the prompt key rather than slicing by index, because the file is grouped by prompt family
  and a positional split would test *different skills* on each side.
- **The split does not defend against pretraining contamination**, and nothing can: IFEval is public and is in
  every base model's weights. It happens not to matter much here — the task is mechanical constraint
  satisfaction ("use no commas"), so having memorized the prompt does not help you satisfy it. The split
  defends against the loop overfitting *this corpus* through the harness.
- **`metadata["errors"]`** distinguishes a degraded gateway from a degraded genome; both score 0.
- **The deps are not shimmed.** nltk's word tokenizer would be trivial to replace, but its punkt *sentence*
  tokenizer and langdetect are not, and substituting them would change verdicts on
  `length_constraints:number_sentences` (52 prompts) and `language:response_language` (31). An approximate
  grader must not be labelled `real`, so the adapter raises `IFEvalUnavailableError` instead.

`EvalHarness()` defaults to `"proxy"` and registers 7 benchmarks (`osworld` excluded);
`EvolutionCycle.run_cycle()` logs a `WARNING` naming the tier on every call so a proxy-scored run is never
mistaken for a real one. `benchmarks/__init__.py` holds two registries: `PROXY_BENCHMARKS` (7 entries) and
`REAL_BENCHMARKS` (1 — `ifeval`). A name earns a place in the latter only once its score is comparable to a
published one; the remaining six real adapters are `docs/specs/SPEC-202` future work.

**A real-harness fitness number is not comparable to a proxy-harness one.** A real harness registers one
benchmark, so `compute_fitness` sees one `eval_scores` entry instead of seven, and the per-benchmark hard
gates below only fire for benchmarks that ran.

## Gotchas

- **Randomness is unseeded** (`random.uniform`, `uuid4` in mutate/crossover) — no seed control is exposed, so
  don't assert on exact offspring; assert on invariants/ranges.
- **Hard fitness gates:** a genome failing any per-benchmark minimum threshold (e.g. ifeval 0.25, bfcl 0.20)
  cannot breed.
- **Long-running:** cycles batch eval jobs (`eval_batch_size`, default 5).
- **Reflection and hyper-mutation refuse noise-flagged signal:** `reflective_improve()` returns
  `reason="stub_signal"` and `hyper_mutate()` likewise declines to verify against a baseline result carrying
  `metadata["stub"] = True` (SPEC-202 honesty — never verify against noise). This is defensive: no shipped
  runner sets that flag today (there is no `stub` tier), but a custom-registered runner still can, and the
  guard stays in place for it.
