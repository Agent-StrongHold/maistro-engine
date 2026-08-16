# MAIstro Adversarial Patent / Engineering Research Log

This log is append-oriented. The synthesis and current portfolio state live in `PATENT-ADVERSARIAL-REVIEW.md`.

## 2026-08-16 — provenance, stale memory, self-evolution acceptance, reasoning provenance

### Patent pressure

1. **Reasoning Provenance for Autonomous AI Agents / Agent Execution Record (AER), March 2026**
   - Makes structured `intent`, `observation`, and `inference` first-class on every step.
   - Carries versioned plans with revision rationale, evidence chains, verdicts, and delegation authority.
   - Explicitly argues computational state/checkpoints cannot faithfully reconstruct reasoning provenance.
   - Pressure on MAIstro: generic `Decision.WHY`, reasoning provenance, observation/evidence linkage, and versioned plan rationale are crowded.
   - Remaining gap: immutable Decision.WHY references to contemporaneous versions of self/goal/preference/epistemic state, and its use as a hard transition gate for later durable self revision.

2. **Agent-BRACE, May 2026**
   - Decouples structured belief state from action policy in long-horizon partially observable environments.
   - Belief state consists of atomic claims with explicit uncertainty.
   - Pressure on MAIstro: separating subjective belief from action/world state is not novel.
   - Engineering validation: objective execution facts, subjective observations, belief state, and reasoning provenance should remain separate durable records.

3. **Responsible Agentic AI Requires Explicit Provenance, May 2026**
   - Frames explicit causal provenance across the agent lifecycle as required for responsibility attribution.
   - Introduces causal attribution / responsibility structures and argues provenance must be computable/interventionable.
   - Pressure on MAIstro: broad causal provenance claims are weak.
   - Engineering validation: provenance should be queryable both backward (`why did this action occur?`) and forward (`what behavior did this bad evidence influence?`).

4. **PACE: Anytime-Valid Acceptance Tests for Self-Evolving Agents, June 2026**
   - Shows repeated `keep candidate if score improved` behaves like adaptive multiple testing.
   - Reports substantial false and harmful commits under naive greedy acceptance.
   - Pressure on MAIstro: robust candidate acceptance is active prior art.
   - Engineering action: promotion must not use naive benchmark deltas; use statistically defensible paired/sequential acceptance or equivalent.

5. **EVE-Agent: Evidence-Verifiable Self-Evolving Agents, May 2026**
   - Self-generated improvement instances carry evidence whose marginal contribution is measured.
   - Pressure on MAIstro: evidence-verifiable self-evolution is prior art.
   - Engineering action: evidence artifacts should be exact, inspectable, and bound to candidate/evaluation identity.

6. **Self-Evolving Agents with Anytime-Valid Certificates, July 2026**
   - Uses a frozen base plus versioned harness and admits modifications through auditable acceptance certificates.
   - Pressure on MAIstro: frozen-base + certified acceptance further narrows recursive-promotion novelty.
   - Remaining possible gap: candidate-controlled executable logic is categorically prohibited from crossing the privileged promotion boundary, with authoritative reconstruction from an independently selected trusted base.

7. **Recursive Self-Improvement in AI survey, July 2026**
   - Separates self-refinement, policy improvement, evaluator improvement, and research-loop closure.
   - Highlights evaluator hierarchy, self-confirming loops, collapse dynamics, and grounding limits.
   - Engineering action: candidate, evaluator, acceptance authority, and promotion policy must be independently versioned/trusted surfaces.

### Memory failure research

8. **Governed Shared Memory for Multi-Agent LLM Systems, June 2026**
   - Four production failure modes: unauthorized leakage, stale propagation, contradiction persistence, provenance collapse.
   - Found direct GET-by-ID sub-scope bypass despite correct ordinary retrieval isolation.
   - Found near-duplicate admission could reject a contradictory correction before contradiction/supersession processing.
   - Engineering actions:
     - enforce scope/authority at canonical store boundary for every access path;
     - process contradiction/correction/supersession before destructive duplicate rejection;
     - test alternate/direct/bulk/admin paths, not only normal retrieval.

9. **STALE, May 2026**
   - Shows agents often retrieve updated evidence but still accept stale assumptions and fail to propagate updated state into downstream behavior.
   - Best evaluated system remains weak overall.
   - Engineering action: supersession must be explicit state adjudication, not merely "retrieve the newest-looking item".

10. **Memory Provenance Laundering in LLM Agents, July 2026**
    - Shows low-trust external observations can be consolidated into apparently trusted persistent memory while preserving dangerous action triggers.
    - Engineering action: platform-maintained origin/authority must survive summarization and derivation; derived items cannot amplify source authority merely because the agent authored the summary/inference.

11. **TierMem, February 2026**
    - Two-tier memory: fast summaries plus immutable raw evidence; runtime escalates when summary is insufficient.
    - Engineering action: compaction should preserve authoritative evidence references and support runtime sufficiency escalation rather than trusting summaries universally.

12. **Rate–Distortion View of Memory Compaction, July 2026**
    - Highlights write-before-query loss: compaction discards information before future queries reveal what mattered.
    - Notes repeated compaction is insufficiently evaluated.
    - Engineering action: test repeated multi-generation compaction and dependency preservation, not only one-shot summary quality.

### Updated Turing pressure

The integrated Turing hypothesis remains under severe combination pressure:

`BDI + structured belief state + reasoning provenance + causal provenance + temporal supersession + origin-bound authority + reflection/self-evolution`.

The remaining unusual parts are increasingly the **negative transition rules**, not the components:

- retrieved/told/imagined material cannot directly become durable self-state;
- retrieval cannot reinforce durable motivation without explicit causal participation in a committed Decision.WHY and subsequent `I_DID`;
- later belief/self revisions cannot rewrite the historical Decision.WHY;
- objective execution outcome remains distinct from the agent's historical observation/belief about that outcome;
- forgetting/archival availability changes cannot masquerade as epistemic contradiction/supersession.

### New architecture test implications

Add eventual adversarial tests for:

- direct-ID memory authorization bypass;
- bulk/admin retrieval scope bypass;
- contradictory corrective write that is a semantic near-duplicate of stale state;
- provenance laundering through summary -> inference -> reflection chains;
- multiple copied/derived evidence items sharing one independence group;
- updated proposition retrieved while stale dependent beliefs/actions remain active;
- summary insufficiency triggering raw/archive evidence escalation;
- repeated compaction preserving required dependency provenance;
- retrieved self-state that does *not* appear in Decision.WHY remaining reinforcement-ineligible;
- later knowledge changes unable to mutate historical Decision.WHY;
- execution Outcome correction not mutating historical I_OBSERVED;
- naive repeated evaluation demonstrating why acceptance gates require adaptive-testing controls.
