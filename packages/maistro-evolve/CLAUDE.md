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
published benchmark harness against the official dataset.** Six of the seven score real model output
against real, structural criteria (rule checks, exact-match, tool-call recall, or real sandboxed
execution) at a lite/handcrafted scale (`benchmarks/datasets.py`) — a genuine but small-scale version of
the real methodology, not the official harness. **`ragas` is the exception**: its primary score is a
keyword/word-overlap heuristic, not a structural check — see its entry below. The names match the
industry-standard evals; the *scale* (and for `ragas`, the *methodology*) does not. This exists to save
time/money and produce Pareto (cost vs. quality) signal cheaply, and is shipped, supported v1 behavior.
`osworld` is not implemented at all — see below.

**There is no `stub` tier.** A benchmark either evaluates a real model response against real criteria
(`proxy`), or it does not run at all — every proxy runner raises `ValueError` if called with `llm_call=None`
rather than falling back to keyword heuristics or a fabricated score. `EvalHarness(benchmark_fidelity="stub")`
(or any value other than `"proxy"`/`"real"`) raises `ValueError`.

Two fidelity tiers, carried as `EvalResult.metadata["fidelity"]` and on `EvalHarness.fidelity`:

| Tier | What it means | Trust for promotion |
|------|---------------|---------------------|
| `proxy` | Lite-scale scoring against handcrafted samples — real rule verification, exact-match, tool-call matching, or real sandboxed execution for six of seven registered benchmarks; `ragas` scores primarily by keyword overlap (see below) | Development only. This is the default (`EvalHarness(benchmark_fidelity="proxy")`). |
| `real` | Official harness against the official dataset | Not implemented for any benchmark. `EvalHarness(benchmark_fidelity="real")` raises rather than silently downgrading. |

Per-benchmark methodology at the `proxy` tier:
- **`ifeval`**: real per-instruction rule verification (`contains`, `exact_match`, `sentence_count`,
  `word_count`, `valid_json`, ...) against handcrafted samples.
- **`bfcl`**: the response's function call is extracted and its name/parameters compared field-by-field
  against the expected call — structural matching, not keyword overlap.
- **`tau_bench`**: recall of *which* tools the response actually invoked against the sample's expected
  tool calls — a structural match on tool identity, not on response content.
- **`ragas`**: **the one genuine keyword-overlap heuristic in this package.** Its primary score is
  word-set overlap between the response and the expected answer/context; it escalates to a real
  LLM-as-judge call only when that static score falls below 0.6, and even then takes the max of the
  two — so a response can score highly on word overlap alone. Treat it as the least reliable proxy-tier
  signal here.
- **`gaia`**: exact-match against handcrafted Q&A, with an LLM-as-judge fallback below a 0.7 threshold.
- **`swebench`**: candidate code actually executes in a real sandboxed subprocess (`benchmarks/sandbox_exec.py`
  — `asyncio.create_subprocess_exec`, `start_new_session=True`, process-group kill on timeout) and is asserted
  against the real expected value. Process-level isolation only — see that module's docstring before reusing
  it elsewhere.
- **`terminalbench`**: delegates to `executable_terminal.py`'s real tempdir-based filesystem-state verification
  (a restricted JSON action language, not a real shell).
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
