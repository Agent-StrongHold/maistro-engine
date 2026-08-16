# MAIstro Adversarial Patentability and Engineering Review

Status: living analysis record
Branch: `analysis/patent-adversarial-review`
Canonical implementation branch under review: `develop`

This document records two parallel outputs from the same research program:

1. adversarial patentability / prior-art findings, including killed hypotheses and surviving claim-shaped mechanisms;
2. engineering lessons from adjacent systems attacking similar hard problems, whether or not those mechanisms remain patentable.

This is architecture and prior-art analysis, not legal advice.

## Repository / disclosure baseline

- Canonical accessible repository: `Agent-StrongHold/maistro-engine` (private).
- `develop` is treated as canonical/newest architecture branch even though GitHub's default branch remains `main`.
- User-supplied privatization boundary: approximately 2026-08-15 21:00 America/Chicago. Exact GitHub audit-log verification remains outstanding.
- PR #388 merged 2026-08-14 22:53:01Z and publicly described `Run -> NodeRun -> Attempt -> ExecutionRuntime`, retry as same NodeRun/new Attempt, repeated node execution as a distinct NodeRun, and the invariant that Provider fallback cannot escape Binding authorization.
- PR #403 merged 2026-08-15 17:22:05Z and publicly described `GraphExecutionState` with active frontier, visit counts, blackboard, and routing decisions correlated to source `NodeRun`.
- PR #416 merged 2026-08-16 01:16:49Z (approximately 20:16 Central on Aug 15) and durably combined canonical Run, GraphExecutionState, and chronological NodeRun, while explicitly deferring actual node execution through Attempt/RunExecutionService/ExecutionRuntime.
- PR #419 was created 2026-08-16 02:02:05Z (approximately 21:02 Central on Aug 15), just after the supplied privatization boundary. It adds concurrent active-frontier execution, deterministic folding, fan-in behavior, repeated visits, pause/recovery, and sibling failure reconciliation, but still explicitly defers Attempt-backed physical execution.

Do not equate existence of individual nouns with disclosure of the full claimed arrangement.

## Current adversarial portfolio state

### Execution identity / reconstruction

Broad durable-workflow, DAG, checkpoint, retry, task-instance, attempt-history, fan-out/fan-in, and provenance claims are crowded and should be treated as prior art.

Narrow survivor:

- static `Node` identity;
- logical traversal-visit `NodeRun` identity;
- physical try `Attempt` identity;
- separate `GraphExecutionState` traversal state;
- revisit => new NodeRun;
- retry => same NodeRun, new Attempt;
- recovery preserves existing identities rather than manufacturing a new logical visit;
- routing provenance is keyed to source NodeRun rather than only static Node.

Primary technical consequence: a repeated traversal of a static node remains distinguishable from a retry of the same semantic visit, including routing decisions made during each visit.

Current status: survives narrowly; substantial portions were disclosed pre-private; vulnerable to an obviousness combination of task-instance/try identity, cyclic durable graph execution, provenance, and recovery.

### Capability / Binding / Provider

Broad `Provider substitutability without authority substitutability` is heavily pressured by capability attenuation, OAuth scope/audience restrictions, downstream authorization, workflow roles, least privilege, and ordinary provider abstraction.

Current status: demoted. Preserve as architecture and possible dependent limitation, not a leading independent family unless later research exposes a narrower gap.

### Recursive self-modification / promotion

Broad sandbox/test/hash/evidence/trusted-promoter/reproducible-build/atomic-update constructions are crowded by secure update systems, privilege separation, SLSA, SCITT, in-toto, reproducible builds, and emerging self-evolving-agent acceptance-gate literature.

Narrow unresolved seam:

- self-modifying candidate may generate arbitrary code, patches, tests, results, and recommendations;
- candidate-controlled executable promotion logic cannot cross the privilege boundary;
- privileged side consumes bounded data representations, independently selects a trusted baseline, reconstructs/verifies the candidate, and owns authoritative activation;
- candidate activation should be bound to exact candidate/evidence/evaluation identities and committed promotion/audit state.

Current status: borderline. Strong obviousness pressure from privilege separation + trusted updater + reproducible build/provenance + self-evolving-agent gates. Still excellent security architecture regardless of patents.

### Turing broad concepts already pressured / killed

Treat the following as crowded individually:

- persistent personality/self-models;
- BDI beliefs/desires/intentions;
- generic autobiographical memory;
- memory decay / category-specific decay;
- episodic-to-semantic consolidation;
- generic temporal propositions and bitemporal truth;
- non-destructive supersession/version history;
- generic provenance and provenance non-amplification;
- retrieved-memory credit assignment after successful actions;
- generic regret/counterfactual reasoning;
- judging historical decisions using only information then available as a conceptual principle;
- generic decision provenance.

### Turing narrow unresolved mechanisms

#### A. Provenance- and agency-constrained durable self-state transitions

Potentially interesting negative transitions:

- `I_WAS_TOLD` cannot directly mutate durable `I_AM`;
- `I_IMAGINED` cannot directly mutate durable `I_LIKE`;
- retrieval/activation alone cannot reinforce durable `I_WANT` or other motivational strength;
- belief or high confidence does not itself grant self-revision authority.

Narrowest surviving reinforcement rule:

`retrieval -> activation -> material inclusion in immutable Decision.WHY -> I_DECIDED -> I_DID -> outcome/observation/reflection -> only then eligible for durable strength update`.

Prior-art pressure includes BDI action chains, Distributed Adaptive Control's agency condition for autobiographical consolidation, MemRL-style retrieval/action/outcome credit, and personality/self-model evolution from reflected behavior.

Current status: borderline independent; still potentially useful as a limitation in an integrated state-transition claim.

#### B. Frozen historical Decision.WHY

A Decision should bind to the versions of propositions, knowledge, goals, preferences, self-state, constraints, alternatives, and expected consequences that existed when the decision was made. Later epistemic or self revisions must not rewrite the historical rationale.

Generic decision provenance and temporal versioning are old. The remaining value is the enforced binding of retrospective evaluation and later self-revision to the historically available state.

Current status: narrow, probably dependent limitation.

#### C. Outcome distinct from I_OBSERVED

`I_DID` means agency crossed into action, not success.

`Outcome` is objective execution state as best established by the platform.

`I_OBSERVED` is the agent's historically situated observation of that outcome.

Later evidence may revise what is believed about the outcome without rewriting what the agent actually observed at the time.

Current status: still not matched exactly in reviewed art; likely strongest as part of the integrated state machine rather than standalone.

#### D. Reflective semantic retirement / compression

Generic "forget experiences, keep lessons" is crowded.

Narrow unresolved rule:

- high-volume source experiences can decay/archive/compact toward removal;
- designated reflective states such as Wisdom/Regret do not leave active influence because of time alone;
- retirement requires typed semantic events such as invalidation, contradiction, or supersession;
- if source evidence leaves hot storage, dependency-aware compaction retains enough provenance to reconstruct justification.

Current status: survives narrowly but may be more useful as a robust state-management invariant than as commercially meaningful patent scope.

#### E. Integrated Turing state-transition architecture

Current strongest combination hypothesis is not any individual noun. It is the set of permitted and forbidden transitions among separately versioned epistemic, autobiographical, self/motivational, and execution state, with immutable causal provenance through actual execution.

Candidate integrated chain:

`I_AM/I_LIKE/I_WANT@version -> activation -> Decision.WHY@frozen refs -> I_DECIDED -> I_DID -> Run/NodeRun/Attempt -> Outcome -> I_OBSERVED -> Evidence -> Proposition/Justification -> epistemic transition -> reflection -> typed SelfRevision/MotivationalRevision`.

Important prohibited transitions include:

- told/implied/retrieved material directly becoming durable self-state;
- retrieval itself strengthening motivation;
- a bad Outcome automatically becoming Regret;
- I_OBSERVED overwriting objective Outcome;
- later knowledge rewriting historical Decision.WHY;
- forgetting being represented as contradiction, invalidation, or supersession.

Current status: strongest unresolved Turing combination, but under serious §103 pressure from BDI + causal/semantic memory + temporal supersession + provenance/authority systems + execution provenance + reflection/self-improvement.

## Engineering lessons from adjacent research

### 1. Truth, authority, causality, and availability must be orthogonal

Do not collapse these dimensions:

- truth: what the system currently treats as supported;
- authority: what an item is allowed to cause;
- causality: what actually influenced a decision/action;
- availability: whether the item is retrievable / active / archived.

Examples of prohibited implications:

- high retrieval relevance != high authority;
- high confidence != high authority;
- high authority != actual causal participation;
- causal participation != truth;
- archived/forgotten != false;
- superseded != historically false.

### 2. Origin authority must be non-amplifying

Research on memory provenance laundering demonstrates that agent summarization/consolidation can transform low-trust external observations into apparently trusted persistent memory if origin is not platform-maintained.

Design consequence:

Evidence should carry immutable/platform-maintained origin, origin authority, acquisition identity, independence group, derivation chain, and current validation state. Derived objects inherit an authority ceiling unless a controlled corroboration/elevation transition explicitly changes it.

### 3. Enforce scope below every access path

Production shared-memory research found normal scoped retrieval could be correct while direct GET-by-ID bypassed sub-tenant isolation.

Design consequence:

Authorization/provenance constraints belong at the canonical store/graph access boundary, not only in the normal retrieval service. Direct ID access, bulk access, administrative repair, consolidation, and alternate APIs must not bypass scope.

### 4. Contradiction/supersession analysis must precede duplicate rejection

A production memory service found a near-duplicate gate could reject a contradictory correction before an asynchronous contradiction detector evaluated it.

Design consequence:

Write/admission pipeline should resolve temporal identity, contradiction, correction, and supersession before destructive deduplication. A corrective statement will often be lexically/semantically similar to the stale statement it replaces.

### 5. Supersession is a state-management operation, not a retrieval heuristic

STALE-style research shows agents often retrieve updated evidence yet continue acting on outdated assumptions. Larger memory alone does not solve stale-state resolution.

Design consequence:

Temporal supersession needs explicit graph/store semantics. Candidate retrieval should be followed by temporal applicability, supersession resolution, epistemic stance, provenance/authority, then contextual relevance. Vector similarity should generate candidates, not decide current truth.

### 6. Retrieval must be distinct from causal use

Causal/semantic agent-memory research shows passive retrieval is insufficient for understanding what influenced a decision.

Design consequence:

Represent at least:

- RetrievalActivation: item was available/salient;
- DecisionContribution: item materially influenced deliberation;
- DECIDED_BECAUSE: durable causal edge into a committed decision.

Do not infer reinforcement eligibility merely because an item appeared in context.

### 7. Wisdom should mature rather than self-authorize

Reflection systems can create self-reinforcing bad lessons: erroneous attribution -> apparent lesson -> repeated retrieval -> behavior -> apparent confirming evidence.

Design consequence:

Consider `CandidateWisdom -> Wisdom` maturation requiring independent experiences/corroboration. Wisdom should retain applicability conditions, exceptions, source-independence groups, supporting decisions/outcomes, contradictions, confidence, and policy version.

### 8. Memory compaction must be query-future aware where possible

Tiered-memory and rate-distortion work highlights the write-before-query problem: summaries discard information before future questions reveal what mattered.

Design consequence:

Keep cheap summarized/indexed representations plus recoverable authoritative evidence or archival references. Allow runtime escalation when summaries are insufficient. Repeated compaction must be evaluated explicitly, not only single-pass summarization.

### 9. Self-evolution quality depends heavily on the acceptor

PACE shows repeated "keep candidate if dev score improved" can produce many false commits and harmful edits because the agent adaptively tests against the same noisy estimate.

Design consequence:

Promotion acceptance should use statistically defensible sequential/paired testing or an equivalent robust gate, not naive score deltas.

### 10. Self-evolution needs evidence-verifiable improvement signals

EVE-Agent shows self-generated improvement data can become fluent but unsupported unless each training/improvement instance carries inspectable evidence whose contribution is measurable.

Design consequence:

Promotion evidence should preserve the exact evidence used, the evaluator/gate version, evaluation execution identities, and candidate/result digests.

### 11. Keep candidate, evaluator, and acceptance authority separate

Recursive-self-improvement literature emphasizes self-confirming loops, evaluator weakness, benchmark overfitting, and collapse dynamics.

Design consequence:

- evaluator/promotion policy should not live in the mutable candidate surface;
- maintain held-out/hidden promotion-only evaluation where feasible;
- bind evaluation policy/corpus/environment versions in PromotionManifest;
- distinguish proposer quality from acceptor correctness.

### 12. Preserve behavioral contracts across evolution

Self-evolving-agent literature highlights behavioral inheritance/stability as an unresolved problem.

Design consequence:

Introduce a `BehavioralContract` concept for non-retired safety, capability, architecture, preference, and recovery invariants. Candidate promotion must demonstrate improvement without violating mandatory inherited contracts.

### 13. Bound long-term memory without losing auditability

Agent context-management and provenance-aware tiered-memory work shows naive history accumulation creates cost/latency growth, while lossy summary-only memory destroys evidence.

Design consequence:

Use tiered active/archive storage, typed decay/retention policy, summary + authoritative evidence linkage, dependency-aware compaction, and explicit sufficiency/escalation decisions.

## Research hits to track

High-value references identified during the review include:

- Governed Shared Memory for Multi-Agent LLM Systems (2026): unauthorized leakage, stale propagation, contradiction persistence, provenance collapse; direct-ID scope bypass; duplicate-vs-contradiction pipeline ordering.
- Memory Provenance Laundering in LLM Agents (2026): authority non-amplification under consolidation.
- STALE: Can LLM Agents Know When Their Memories Are No Longer Valid? (2026): stale-state resolution and policy adaptation failures.
- From Lossy to Verified: A Provenance-Aware Tiered Memory for Agents / TierMem (2026): summary/raw evidence tiers and runtime sufficiency escalation.
- What to Keep, What to Forget: A Rate--Distortion View of Memory Compaction (2026): compaction failure modes and repeated-compaction research gap.
- PACE: Anytime-Valid Acceptance Tests for Self-Evolving Agents (2026): adaptive multiple-testing failure in naive promotion gates.
- EVE-Agent: Evidence-Verifiable Self-Evolving Agents (2026): evidence contribution as a promotion/training signal.
- Self-Evolving Agents with Anytime-Valid Certificates (2026): frozen base + versioned harness + auditable acceptance certificates.
- Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops (2026): evaluator hierarchy, self-confirming loops, collapse and governance-grade measurement gaps.
- Distributed Adaptive Control / autobiographical memory work: agency condition for consolidation.
- MemRL and related retrieval-credit work: retrieved memory -> action -> outcome -> credit pressure against Turing reinforcement novelty.

For patent work, future entries should distinguish: single-reference anticipation, plausible combinations/obviousness, surviving limitation, and disclosure/conception/implementation dates.
