# Wave-1 report: stronghold epics, ADR-K8S series, security/compliance docs, backlog (condensed digest)

## Deconfliction (gates everything)
- Engine **ADR-035** assigns catalog ADRs (K8S-021/022/023/027) to Stronghold; **ADR-019** puts
  deployment/multi-tenancy in the importing product. The ADR-K8S infra series (001–012, 016,
  017) is Stronghold-scoped **by design — skip**.
- Epic-07 DSPy: engine deliberately rejected the DSPy dep (ADR-039) and reimplemented natively
  (SPEC-207) — concept-note only. Epic-09 canary ≈ covered (ADR-088/007/075). Epic-14: skip.

## Tier-1 gaps (verified absent from engine docs)
1. **CapabilityProfile (epic-02)** — per-agent `(capability, intent_class)` → three orthogonal
   dimensions: permission (binary), skill score (0–10, EMA-updated from eval outcomes), cost
   vector (measured: standing, cold_start_ms, per_call_compute/tokens, tool_fees, overhead).
   Intent-conditional skill (`{summary:4, report:8, prose:2}`). Blocked capabilities omitted
   from visible options. Keystone of the 02→03→04→05→06 spine. Engine SPEC-184 is a different
   axis (slots/providers). → ADR + SPEC (M).
2. **Substrate/tool/agent taxonomy (epic-04)** — substrate (LLM + pure utils, ungated) / tools
   (permissioned side-effects, heavy only) / agents; `kind: light|heavy`, light agents hold
   **zero tools** structurally; substrate-purity validation at registration (file I/O = not
   substrate); default heavy for legacy. → ADR (S–M).
3. **Six-tier priority system (ADR-K8S-014/015, de-K8s'd)** — cross-cutting `priority_tier`
   P0–P5 read by every subsystem: routing weight (2.0×…0.7×), model bias (flagship→fast-cheap),
   token-budget multiplier, cold-start policy, eviction order, SLA. Engine has only
   LIVE/BACKGROUND (ADR-010). Drop the K8s PriorityClass columns. → ADR (M).
4. **Warden L3 "redirect, don't refuse" (blue-team-training-spec.md)** — fine-tuned L3 tier
   with redirect posture ("a refusal is a dead end; a redirect is a conversation; never reveal
   why"), 8-category attack taxonomy (~5000 examples: injection, role-hijack, data-probe,
   priv-esc, tool-abuse, social-eng, extraction + ~500 legitimate negatives), 4-phase data
   pipeline, eval >95% TPR <2% FPR. Engine L3 is a classifier, no redirect posture, no taxonomy.
   → ADR (posture) + SPEC (taxonomy as Warden pattern/test source-of-truth) (L).
5. **RCA structured-output (rca-structured-output.yaml)** — closed vocab
   `missing_precondition|tool_contract_mismatch|permission_gap|rate_limit|input_validation|
   ambiguous_intent|unknown` + `rca_prevention` on Learning + RCA→OutcomeStore effectiveness
   loop (`mark_outcome`, `list_ineffective`). NOTE: engine has `RCAExtractor`+`RCA_CATEGORIES`
   already — port only the delta (effectiveness loop). → SPEC (S–M).
6. **Epic-11 group-chat/debate/committee** — pattern registry (debate: research→draft→critique→
   revise with convergence criterion; committee review), conduit selects per intent class,
   one-new-pattern-per-release. Engine has waves (ADR-052) only. → SPEC (M).
7. **Epic-12 self-editing memory** — agent-initiated memory write/update via tool call (Letta/
   MemGPT), scoped: no cross-agent edits; + cache-aware provider routing as router signal; +
   per-provider prompt-cache-hit telemetry. → SPEC on ADR-057 (M).
8. **Epic-03 originating-principal stamping** — deny when `call_chain[0]` lacks target
   capability (transitive escalation); dual budget attribution (caller AND originating user).
   Depth/cycle already covered (ADR-058/066). → small SPEC + formal invariant (S).
9. **Epic-01 eval substrate** — behavioral tags on OTEL spans (tool-selection, multi-step-
   reasoning, delegation-error), optimization/holdout split (stratified, seeded), eval-report
   artifact with per-tag delta + regression flag; Inspect-AI adapter optional. Engine SPEC-202
   runners are evolve-scoped. → SPEC (M).
10. **Epic-13 meta-optimization** — optimize the improvement loop itself (Auditor rubric,
    Extractor, Promoter thresholds, Forge template; inter-rater agreement metric) + self-
    mutation circuit breaker (N mutations/hr → freeze, manual re-enable, no auto-resume;
    cascade-rollback OQ). → ADR + SPEC, sequence last (L).
11. **Epic-10 mid-session switching** — trigger taxonomy (cost/latency/quality/budget/
    capability) + continuity contract (mid-tool-call ownership), switch reason on span. (S)
12. **Shadow mode** (GLOSSARY) — candidate runs parallel, only incumbent serves; track-record
    building. Fold into ADR-075/007 concept-note. (S)

## Governance/assurance docs (engine has machinery, no assurance layer)
- **COMPLIANCE.md** (stronghold, 133 lines): control→regulation matrix — OWASP Agentic AT-01…
  AT-10, NIST AI RMF (Govern/Map/Measure/Manage), EU AI Act Arts 9–15/17/26, SOC 2 — each row
  maps risk → module → **test path that proves it**, gap legend (gap-test/gap-impl/gap-spec).
  Engine: zero equivalent (grep verified). Reconcile old ADR numbers; mark tenancy rows
  "deferred to importing product". → new doc (M).
- **SECURITY.md** (stronghold, 235 lines): 5-layer defense-in-depth (Gate→Warden→Identity→
  Skill→Resource protection), **resource-limit table** (learning store 10K FIFO, tool-arg 100KB,
  Warden 10/50KB scan windows, skill-body 50KB, SSRF blocklist, find_relevant ≤10), OWASP LLM
  Top-10 mapping, **honest Known Limitations** (15 items). Engine has no SECURITY.md. → new doc
  (M; audit engine's actual caps for the table).
- **Assertion-strength gate** (test-quality-audit): WEAK/BAD/GOOD taxonomy (11 issue types),
  Gate A pattern-linter / Gate B diff-scoped mutation / Gate C LLM judge (block on BAD),
  "spec is the gate" (spec-driven tests hit 99.4% cov, 0 WEAK/BAD vs 60–90% BAD AC-driven).
  Extends SPEC-205. → SPEC (M).
- **SEC-NNN findings ledger** practice + concrete findings to test-check: tool-policy fail-open,
  secrets-in-argv, tracing-span redaction before export, NaN/Infinity budget bypass,
  prefix-collision/symlink sandbox escape, DNS rebinding. → concept-note + tests (S–M).

## From BACKLOG/agents/deploy
- **Session Trust Floor (CFM-2)** — `STF = min(agent, recipe, node, tool, input_source, user,
  warden_confidence …)` tiers, **monotonically non-increasing** per session; redaction/
  compaction does NOT heal it (anti trust-laundering); forks inherit; contributors emit
  `TrustSignal{source,tier,confidence,rationale,trace_ref}`; unknown → Skull; read-down
  semantics (floor blocks new privileged actions, doesn't block reading poisoned context);
  `WardenVerdict.confidence ∈ [0,1]` drags input tier. Engine has only upward elevation
  (ADR-068/SPEC-245-248). → ADR + SPEC (L).
- **Review Queue Engine (CFM-1)** — typed `ReviewItem.kind` (forge_skill, recipe_variant_promote,
  learning_promote, agent_import, stf_ratchet_decision, …), priority =
  f(stakes, −origin_stf, plan_tier_sla, age_bonus, blast_radius, backlog_pressure), reviewer
  classes human_only|ai_allowed|ai_only, SLA/escalation/auto-expire, ReviewOutcome as audit
  artifact. → SPEC (M–L).
- **Builder-fleet agent DATA** — stronghold/agents/ has complete SOUL.md+agent.yaml for Herald,
  Quartermaster, Archie, Mason (8-phase evidence-driven TDD YAML), Auditor (proactive cron +
  pr.opened), Master-at-Arms, Arbiter, Ranger, Fabulist, Default, artificer sub-agents, shared
  PREAMBLE.md ("Behavioral Standards"). Engine has code strategies but agent data only for the
  PM fleet + davinci; intents route to agents with no data definition. → port + de-tenant (M).
- APM 7-section schema + Warden-gated PUT → enrich SPEC-192 (S). Thompson-sampling variant note
  → ADR-007 note (S). Coin economy → skip (Stronghold-owned).

## AgentTuring-unique (turing package)
- **Self-model security audit** F1–F40 + guardrail invariants G1–G18 + 13 guardrail specs
  (warden-on-self-writes, self-write-budgets, facet-drift-budget, …) — port as ADR (threat
  model) + SPEC (G1–G18 as AC) + audit into docs/security-reviews/. (M)
- ~130 per-concept design specs (`research/project-turing/specs/*.md`) + TRACEABILITY.md →
  docs/specs/turing/ or docs/research/. HEXACO-200 yaml + norms json data assets. Autonoetic
  thesis (Tulving) short ADR. 22 Tranche-11 "autonoetic blends" digest. Measurable-autonoesis
  eval properties (identity continuity, narrative consistency, decision provenance, mood
  plausibility, memory-floor preservation). BDD .feature guardrail suites.
