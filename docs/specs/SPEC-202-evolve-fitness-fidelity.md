---
id: SPEC-202
title: "Evolve fitness fidelity — proxy/real benchmark honesty, signal provenance, adapter contract"
repo: maistro-engine
kind: spec
status: Proposed
created: 2026-06-09
substrate:
  - maistro-engine#ADR-039
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
    date: 2026-06-09
---

# SPEC-202: Evolve Fitness Fidelity

## Problem

`maistro-evolve` selects, mutates, and promotes pipeline genomes using a fitness
function whose dominant term (`eval_score`, weight 0.65) is produced by benchmark
runners named after industry-standard evals — `swebench`, `gaia`, `tau_bench`,
`osworld`, `ifeval`, `bfcl`, `ragas`, `terminalbench`. These runners do **not**
execute the named benchmarks. They score model output against hardcoded handwritten
samples using keyword-overlap and line-change heuristics.

The optimizer is only as trustworthy as its fitness signal. This spec makes the
signal honest and implements all real-benchmark adapters.

## Design

### 1. Three-tier signal taxonomy

| Tier | Meaning | Trust for promotion |
|------|---------|---------------------|
| `stub` | `random.uniform()` — no evaluation occurred | Never. Promotion refused. |
| `proxy` | Heuristic/keyword scoring against handcrafted samples | Development only; gated. |
| `real` | Actual published benchmark harness against official dataset | Full. |

### 2. Rename to remove false claims

- `use_real_benchmarks` → `benchmark_fidelity: Literal["stub", "proxy", "real"]`
- Default: `"proxy"` (honest about what ships today)
- `REAL_BENCHMARKS` → `PROXY_BENCHMARKS` for current handcrafted runners

### 3. Real-benchmark adapters — ALL benchmarks

Every adapter wraps the official harness, runs against the official dataset, and
uses the fail-closed sandbox executor (Hyperlight → Firecracker → bubblewrap →
gVisor → LXC → hardened container → REFUSE) for execution benchmarks.

| Benchmark | Type | Adapter approach | Sandbox needed |
|-----------|------|-----------------|----------------|
| `ifeval` | Rule-checking | Load official dataset, apply rule verifier | No |
| `bfcl` | Function-calling | Official BFCL evaluator against Berkeley dataset | No |
| `ragas` | RAG quality | Official ragas library scoring | No |
| `gaia` | QA accuracy | Official GAIA dataset + exact-match/LLM-judge | No |
| `tau_bench` | Tool-use | Official τ-bench harness, tool-call verification | Minimal |
| `swebench` | Code patch | Official SWE-bench harness: apply patch, run repo tests | Yes — full sandbox |
| `terminalbench` | CLI task | Official harness: execute commands in sandbox terminal | Yes — full sandbox |
| `osworld` | Desktop task | Official OSWorld VM harness | Yes — VM-level |

Implementation order by complexity:
1. **ifeval** + **bfcl** + **ragas** (pure scoring, no execution, land together)
2. **gaia** + **tau_bench** (need LLM-judge or tool-call replay)
3. **swebench** + **terminalbench** (need sandbox executor integration)
4. **osworld** (needs VM — Firecracker/Hyperlight tier)

### 4. Fitness gate enforces fidelity

- `_check_hard_gate` fails any genome with `stub`-tier scores
- `compute_fitness(min_fidelity="real")` fails proxy-scored genomes
- `PipelineGenome.fitness_score` annotated with lowest gated-benchmark fidelity

### 5. Adapter contract

```python
class BenchmarkAdapter(Protocol):
    name: str
    fidelity: Literal["real"]

    async def evaluate(self, candidate_output: str, instance: BenchmarkInstance) -> EvalResult:
        """Score against official dataset instance. Returns EvalResult with metadata.fidelity='real'."""
        ...

    async def self_conformance(self) -> bool:
        """Reproduce a known reference score on a held-out instance. Must pass to register."""
        ...
```

### 6. Registration rules

- `REAL_BENCHMARKS` contains only adapters that passed `self_conformance()`
- Requesting `fidelity="real"` with no real adapter → hard error (no silent downgrade)
- CI runs `self_conformance()` for all registered adapters on every PR

## Acceptance criteria

- [x] Every `EvalResult` carries `metadata.fidelity ∈ {stub, proxy, real}`
- [x] `benchmark_fidelity` replaces `use_real_benchmarks`; default is `"proxy"`
- [x] Handcrafted runners registered under `PROXY_BENCHMARKS`
- [x] `fidelity="real"` with no adapter raises hard error (tested)
- [ ] `_check_hard_gate` fails stub-scored genomes (tested) — still gates on raw
      `eval_scores` floats only; fidelity isn't threaded through
      `PipelineGenome` yet, so a stub score can still pass the threshold gate
      today (`stub`/`proxy` distinction is enforced upstream of gating, in
      `reflective_improve`/`hyper_mutate`'s stub-signal refusal — not here)
- [ ] `compute_fitness(min_fidelity="real")` fails proxy-scored genomes (tested)
- [x] `run_cycle` logs WARNING banner naming run's fidelity
- [ ] `ifeval` adapter loads official dataset, reproduces reference score in CI
- [ ] `bfcl` adapter passes self-conformance against Berkeley dataset
- [ ] `ragas` adapter passes self-conformance with official ragas scoring
- [ ] `gaia` adapter loads official GAIA dataset, passes self-conformance
- [ ] `tau_bench` adapter runs tool-call verification, passes self-conformance
- [ ] `swebench` adapter applies patches + runs tests in sandbox, passes self-conformance
- [ ] `terminalbench` adapter executes commands in sandbox, passes self-conformance
- [ ] `osworld` adapter runs in VM-level sandbox, passes self-conformance
- [ ] `PipelineGenome.fitness_score` annotation reflects lowest fidelity
- [ ] All adapters run in CI; failing self-conformance blocks merge
