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

**None of `ifeval`, `bfcl`, `swebench`, `tau_bench`, `gaia`, `ragas`, `terminalbench` run the official
published benchmark harness against the official dataset.** They score real model output, against real
criteria, at a lite/handcrafted scale (`benchmarks/datasets.py`) — a genuine but small-scale version of the
real methodology, not the official harness. The names match the industry-standard evals; the *scale* does
not. This exists to save time/money and produce Pareto (cost vs. quality) signal cheaply, and is shipped,
supported v1 behavior. `osworld` is not implemented at all — see below.

**There is no `stub` tier.** A benchmark either evaluates a real model response against real criteria
(`proxy`), or it does not run at all — every proxy runner raises `ValueError` if called with `llm_call=None`
rather than falling back to keyword heuristics or a fabricated score. `EvalHarness(benchmark_fidelity="stub")`
(or any value other than `"proxy"`/`"real"`) raises `ValueError`.

Two fidelity tiers, carried as `EvalResult.metadata["fidelity"]` and on `EvalHarness.fidelity`:

| Tier | What it means | Trust for promotion |
|------|---------------|---------------------|
| `proxy` | Lite-scale but genuine scoring against handcrafted samples — real rule verification, exact-match, tool-call matching, or real sandboxed execution — **what every registered benchmark ships today** | Development only. This is the default (`EvalHarness(benchmark_fidelity="proxy")`). |
| `real` | Official harness against the official dataset | Not implemented for any benchmark. `EvalHarness(benchmark_fidelity="real")` raises rather than silently downgrading. |

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

`EvalHarness()` defaults to `"proxy"` and registers 7 benchmarks (`osworld` excluded);
`EvolutionCycle.run_cycle()` logs a `WARNING` naming the tier on every call so a proxy-scored run is never
mistaken for a real one. `PROXY_BENCHMARKS` (in `benchmarks/__init__.py`) is the honest name for the registry
that `REAL_BENCHMARKS` used to be. Official-dataset/official-harness `real` adapters for any benchmark are
`docs/specs/SPEC-202` future work, not v1 scope.

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
