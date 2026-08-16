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

## 2026-08-16 — older cognitive-agent and workflow identity prior art

### Strong cognitive-architecture hit

13. **US7249117B2 / US20080016020 — Knowledge discovery agent system and method**
    - Uses an extended BDI structure with `Beliefs`, `Desires`, `Intentions`, `Methods`, `Values`, and `History`.
    - `History` stores previous attempted plans, the belief state associated with the plan, and the methods invoked.
    - Describes intentionally malleable/organic software agents capable of self-modification based on cognitive judgments.
    - Patent pressure:
      - kills broad "persistent agent + beliefs/desires/intentions + historical belief state + action/method history + self-modification" framing;
      - substantially narrows any integrated Turing claim.
    - Remaining MAIstro differences must come from stricter typed/forbidden transitions, immutable historical version binding, provenance/authority semantics, objective execution identity, and explicit separation among decision, action, outcome, observation, evidence, and later revision.

14. **US20080091628A1 — Cognitive architecture for learning, action, and perception**
    - Integrates perception, memory, planning, decision-making, action, self-learning, and affect.
    - Patent pressure: broad "comprehensive cognitive architecture" framing is dead.

15. **US20090271358A1 — Evidential Reasoning Network and Method**
    - Transaction-aware evidence/opinion graph records changing belief, disbelief, uncertainty, trust, and evidence over time.
    - Patent pressure: temporal epistemic stance and historical opinion transitions are old individually.
    - Engineering lesson: preserve explicit transition histories and distinguish evidence from agent stance toward evidence.

### Execution identity hits

16. **US20070055558A1 — probabilistic workflow mining**
    - Explicitly states that a workflow representation can create a new task node each time a task is repeated.
    - Patent pressure: `revisit -> new occurrence identity` is not novel by itself.

17. **US5745687A — distributed workflow routing**
    - Routing nodes select subsequent nodes.
    - Modifier nodes cause earlier work nodes to be performed again after errors or reactivation.
    - Patent pressure: reprocessing/re-execution of graph nodes and routing history are old.

18. **Apache Airflow TaskInstance / try history**
    - `TaskInstance` is the authoritative persisted logical task execution state within a DAG run; task try numbers are separately tracked and exposed through APIs.
    - Airflow can preserve/reschedule the same try in some cases and move task instances into retry states after failure.
    - Patent pressure: static task -> logical task instance -> try is strong art against generic `Node -> NodeRun -> Attempt` identity.

19. **Prefect task-run states**
    - Stable task-run identity carries rich state transitions including retrying, crashed, cancelled, paused, etc.
    - Patent pressure: retry/cancellation/recovery state under durable task-run identity is standard.

20. **US10540624B2 / US20180025307A1 — provenance-aware application execution**
    - Records applications, data, invocation data, execution subsequences, and execution history in provenance graphs.
    - Patent pressure: execution provenance graphs and replay/recommendation from histories are old.

21. **US8209204B2 — changing process behavior using provenance**
    - Captures execution trace as provenance graph, compares actual execution patterns against stored practices, and changes future/current process behavior based on discrepancies.
    - Patent pressure: provenance-driven behavioral adaptation is old.

### Narrow execution survivor after these hits

The execution candidate should no longer be framed as:

- new identity for a repeated task;
- task instance plus retry count;
- routing provenance;
- recovery/reprocessing.

The remaining combination is specifically:

- a static graph Node;
- a durable logical **visit** identity that changes for a semantic traversal revisit of that Node;
- a durable physical Attempt identity that changes for retry of the **same** logical visit;
- graph routing decisions keyed to the logical visit identity;
- recovery preserving the distinction so a retry never masquerades as a new traversal visit and a revisit never masquerades as a retry.

No reviewed reference yet matches that exact combination. Obviousness pressure is now very high from Airflow TaskInstance/try + repeated-task occurrence modeling + cyclic workflow/reprocessing + provenance.

### Engineering consequences despite patent pressure

- Keep `NodeRun` and `Attempt` semantically orthogonal even if patent scope fails; conflating them destroys correct replay, debugging, routing provenance, retry accounting, and cyclic-graph analysis.
- Persist routing provenance against the actual source visit, not the static Node definition.
- Build tests where the same static Node is revisited and separately retried within one Run; assert that the event/provenance graph can distinguish all occurrences and tries after restart.
- Do not infer logical execution history from runtime logs or try counters; persist first-class identities.
