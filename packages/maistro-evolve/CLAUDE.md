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

**None of `ifeval`, `bfcl`, `swebench`, `tau_bench`, `gaia`, `ragas`, `terminalbench`, `osworld` run the
official benchmark harness.** They score model output against a small set of handcrafted samples
(`benchmarks/datasets.py`) using keyword-overlap and line-change heuristics, sometimes backstopped by an
LLM-as-judge call. The names match the industry-standard evals; the implementations do not. This is shipped,
supported v1 behavior — not a bug — but treat scores accordingly.

Three fidelity tiers, carried as `EvalResult.metadata["fidelity"]` and on `EvalHarness.fidelity`:

| Tier | What it means | Trust for promotion |
|------|---------------|---------------------|
| `stub` | `random.uniform()` — no evaluation occurred | Never. `reflective_improve()` and `hyper_mutate()` both refuse to verify against it. |
| `proxy` | Heuristic/keyword scoring against handcrafted samples — **what every benchmark above ships today** | Development only. This is the default (`EvalHarness(benchmark_fidelity="proxy")`). |
| `real` | Official harness against the official dataset | Not implemented for any benchmark. `EvalHarness(benchmark_fidelity="real")` raises rather than silently downgrading. |

`EvalHarness()` defaults to `"proxy"`; `EvolutionCycle.run_cycle()` logs a `WARNING` naming the tier on every
call so a proxy-scored run is never mistaken for a real one. `PROXY_BENCHMARKS` (in `benchmarks/__init__.py`)
is the honest name for the registry that `REAL_BENCHMARKS` used to be. Real adapters (official dataset +
harness, `swebench`/`terminalbench`/`osworld` needing sandbox execution) are `docs/specs/SPEC-202` future work,
not v1 scope.

## Gotchas

- **Randomness is unseeded** (`random.uniform`, `uuid4` in mutate/crossover) — no seed control is exposed, so
  don't assert on exact offspring; assert on invariants/ranges.
- **Hard fitness gates:** a genome failing any per-benchmark minimum threshold (e.g. ifeval 0.25, bfcl 0.20)
  cannot breed.
- **Long-running:** cycles batch eval jobs (`eval_batch_size`, default 5). The `benchmarks` module is optional —
  it falls back to stubs if import fails.
- **Reflection and hyper-mutation refuse stub signal:** `reflective_improve()` returns `reason="stub_signal"`
  and `hyper_mutate()` likewise declines to verify against a baseline carrying `metadata.stub=True` (SPEC-202
  honesty — never verify against noise). Neither currently gates on `proxy` vs `real` — only `stub` is refused
  today; see **Benchmark fidelity** above.
