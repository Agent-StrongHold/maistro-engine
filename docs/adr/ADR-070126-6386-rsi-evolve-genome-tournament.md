---
id: ADR-070126-6386
title: "RSI code improvement as an evolve genome tournament"
repo: maistro-engine
kind: adr
status: Proposed
created: 2026-07-01
substrate: []
implements: []
related:
  - maistro-engine#ADR-088
  - maistro-engine#ADR-062
  - maistro-engine#ADR-093
  - maistro-engine#ADR-038
  - maistro-engine#ADR-099
supersedes: []
blocks: []
blocked-by: []
contracts:
  - behavioral
tests: []
layer: Evolve
owners:
  - '@BlakeMatthews-dev'
---

# ADR-070126-6386: RSI code improvement as an evolve genome tournament

**Status:** Proposed

## Context

The local recursive-self-improvement loop (`maistro_rsi.local_loop.LocalRsiLoop`)
today runs a **single** coding attempt per cycle: clone → one agent turn-loop
edits a target file → the multi-signal `Scorecard`
(`maistro_evolve.scorecard`) gates promotion → the change ratchets onto an
in-container `rsi-baseline` branch. A validated 15-cycle run (fully isolated per
ADR-093 — agent, git, tests, coverage, and the whole fitness evaluation execute
inside one ephemeral container; the host is never touched) promoted 11/15, with
all 4 rejections correctly vetoed by the `ruff_clean` gate. See
`tools/run_rsi_isolated.sh` and `Dockerfile.rsi-runner`.

That loop proves the *ratchet* and the *fitness gate*. It does not yet exploit
the two levers that make self-improvement compound:

1. **Competition.** One attempt is not the best attempt. The same improvement
   can be made several ways; a stronger or cleaner version should win.
2. **Improving the improver.** The thing that varies between attempts — the
   prompt, model, temperature, and strategy driving the coding agent — is
   exactly a **maistro-evolve genome** (`NodeGenome{role, strategy, model,
   temperature, max_tokens, system_prompt, max_tool_rounds}` inside a
   `DAGTopology` with a `use_scout` flag; `PipelineGenome` carries
   `fitness_score`, `eval_scores`, `generation`, `parent_*`). Evolve
   (ADR-088) already runs Elo tournaments over genomes, culls, breeds
   (`crossover`/`mutate_all`), and enforces diversity — but against generic
   benchmarks (ifeval, bfcl, swebench…), never against "did this genome produce
   the best fix for *our* code?"

The user's framing: *one model reads a file and identifies something
suboptimal; then multiple models and configs of the same model compete to fix
it best; the winner is kept, or complementary non-overlapping fixes are both
kept; and this repeats so the fixers themselves improve.* That is an evolve
genome tournament whose benchmark is our own codebase.

## Decision

Introduce a **code-improvement tournament** as the unit of an RSI cycle, and
express it entirely in evolve terms so the genome population — not a bespoke
roster — is what competes and evolves.

### Conceptual mapping

| RSI concept | maistro-evolve primitive |
|---|---|
| Scout reads the file, names the concrete fix | `DAGTopology.use_scout` node (`role="scout"`) |
| Competing models / configs of the fixer | the genome **population** (`NodeGenome.model` / `.temperature` / `.system_prompt` / `.strategy`) |
| Score of one fix attempt | RSI `Scorecard.composite` surfaced as an `EvalResult.score` for a new **`code_rsi`** benchmark |
| Head-to-head ranking | `EloTournament` battles over `code_rsi` scores |
| Keep winners, breed better fixers | `EvolutionCycle`: cull → `crossover`/`mutate_all` → diversity, across sessions |
| Winning code changes | promoted onto `rsi-baseline`, then harvested as PRs |
| Fixer lineage over time | `PipelineGenome.generation` / `parent_*`, persisted in `PopulationStore` |

### The `code_rsi` benchmark

Add a benchmark to `maistro_evolve.harness.EvalHarness` whose `evaluate_genome`
path, for a given `(target_file, scout_objective)`:

1. Drives the coding agent **configured by the genome** (its fixer node's
   `model`, `temperature`, `system_prompt`, `max_tool_rounds`) to implement the
   scout's objective on a fresh worktree off the current baseline.
2. Runs the existing `candidate_fitness.evaluate_candidate` → `Scorecard`.
3. Returns `EvalResult(benchmark="code_rsi", score=scorecard.composite,
   metadata={gates, per-signal scores, patch-ref})`. A gate veto ⇒ score 0
   (evolve's hard-gate semantics already exist via `FitnessComponents`).

The genome's `code_rsi` score is thus "how good a code fix this prompt/model/
config produces", so `EvolutionCycle` evolves the population toward better
*fixers*. `EvalWeights` is extended (or a code-only weight profile is used) so
`code_rsi` dominates when the RSI loop runs.

### Cycle algorithm (per target file)

1. **Scout.** A scout genome (or the `use_scout` node of the champion) reads the
   file/module and emits one concrete, bounded improvement objective. All
   competitors receive the *same* objective — a fair head-to-head.
2. **Compete.** Evaluate a batch of genomes on `code_rsi` for this objective
   (bounded by `EvolutionConfig.eval_batch_size`, `MAX_*` ceilings in
   `cycle.py`). Each yields a patch + composite.
3. **Select + merge** (the competitive/complementary rule). Rank passing
   candidates by composite, descending. Starting from the baseline, apply each
   candidate's diff in order:
   - applies cleanly ⇒ **keep** (it touches a different region — complementary);
   - conflicts with an already-kept diff ⇒ **drop** (same region — the
     higher-scored candidate already won).
   Re-score the merged result when ≥2 diffs combined; if the combination
   regresses a gate, fall back to the single top candidate (known-good).
4. **Promote** the merged result onto `rsi-baseline`; record each contributing
   genome's win/loss for the Elo tournament.
5. **Evolve** (every N cycles, not every cycle): run `EvolutionCycle.run_cycle`
   to cull weak fixer genomes and breed new ones from the winners.

### Persistence and PRs

A session's promotions are harvested into **a few PRs grouped by the file (or
package) edited** — each promotion commit already touches one file, so grouping
is a partition of the commit set. Harvesting exports validated patches out of
the sandbox and opens PRs against the base the run improved; applying vetted,
gate-passing diffs to a review branch is a controlled step and does **not**
re-run agent code on the host. The genome `PopulationStore` and Elo state
persist across sessions so the fixers keep improving.

### Safety

- **Isolation (ADR-093).** The whole tournament — scouts, every competitor,
  tests, coverage — runs inside the ephemeral container. Nothing but reviewed
  patches leaves it.
- **Promotion gate.** `PipelineGenome.approved_for_promotion` stays closed;
  winning a tournament never flips a genome to live traffic without an explicit
  human gate (existing evolve RSI-safety invariant).
- **Resource ceilings (ADR-038, `cycle.py` `MAX_*`).** Batch size, population,
  tournament size, and self-improve fan-out remain hard-capped so an autonomous
  ("use all tokens continually") run cannot consume unbounded compute.
- **Honesty.** `reflective_improve` already refuses stub eval signal; `code_rsi`
  must likewise never score against a stubbed/absent test suite.

## Consequences

**Positive.** Self-improvement compounds on two axes: better code *and* better
fixers. Reuses evolve's tournament/cull/breed/diversity wholesale instead of a
parallel bespoke selector. Complementary-merge captures more value per cycle.
The genome lineage makes "which prompt/model/config improves our code best" an
observable, evolving artifact.

**Negative / risks.** Cost multiplies by the competitor count per cycle (bounded
by the `MAX_*` ceilings and rate-limited by the LiteLLM `code` group). Merge
re-scoring adds evaluations. Cross-package coupling (`maistro-rsi` depends on
`maistro-evolve` harness/population). Scout quality caps the whole cycle — a
vague objective yields weak competition. `code_rsi` is a non-deterministic,
cost-bearing benchmark, unlike the existing static ones.

## Staged rollout

1. **Tournament engine** in the RSI cycle: N candidates + competitive/
   complementary merge, candidates described *as genome nodes*. (Selection/merge
   is independent of how candidates are generated.)
2. **Scout** step feeding a shared objective to competitors.
3. **`code_rsi` benchmark** in `EvalHarness`; drive competitors from a
   `PopulationStore` via `EvolutionCycle` (Elo + cull + breed + mutate).
4. **Harvest** session → grouped PRs; persist population + lineage; enable
   longer/autonomous capped runs.

## Alternatives considered

- **Bespoke roster in the RSI loop** (a hard-coded list of `model@temp`). Faster
  to build, but duplicates evolve's tournament/evolution and can't *learn* which
  fixers are best — rejected in favour of driving the genome population.
- **Best-of-N without merge.** Simpler, but discards complementary non-
  overlapping improvements the user explicitly wants kept.
- **Single strong model, no competition.** The current loop; leaves the "improve
  the improver" lever unused.

## Open questions

- Scout as a fixed champion node vs. its own evolving genome role.
- Weighting `code_rsi` against the existing benchmarks in `EvalWeights` (code-only
  profile vs. blended).
- Whether merged multi-genome commits credit Elo to each contributor or only the
  top scorer.
