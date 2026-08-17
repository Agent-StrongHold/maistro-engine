# Agent Frontier Scan — 2026-08-16

Purpose: map recent public research and implementation work in major agent ecosystems onto MAIstro architecture and hardening priorities. This is an engineering scan, not a patentability analysis.

## Sources scanned

- OpenAI: `openai/codex`, OpenAI research publications
- Anthropic: `anthropics/claude-code`, `anthropics/claude-agent-sdk-python`, Anthropic research
- OpenHands: `OpenHands/OpenHands`, public SDK/project material
- OpenCode: `anomalyco/opencode`
- Mistral: `mistralai/mistral-vibe`, Mistral product/research posts
- OpenClaw: `openclaw/openclaw`
- Pi: `badlogic/pi-mono` / current earendil-works project material
- Meta FAIR: HyperAgents, PAHF, SIRA, CIMemories, Dr. Zero and related public repositories/research

## Cross-ecosystem trend 1: explicit policy and environment state

Recent OpenAI Codex commits reject obsolete permission-profile fields rather than silently ignoring them, retain filesystem restriction semantics across legacy profile names, and carry shell-environment policy in each resolved environment. This is a strong implementation signal that permission/policy state must be explicit, versioned, and environment-bound.

MAIstro implication:

- `Binding`, `ResolvedBinding`, `PolicyVerdict`, `Attempt`, and `Invocation` should retain exact policy/environment identity.
- Unknown/obsolete authority fields should fail closed when they would otherwise silently weaken enforcement.
- Resumed execution must re-establish the exact effective environment and authority envelope rather than infer it from current defaults.

## Cross-ecosystem trend 2: resumability is becoming a first-class product/runtime feature

Pi persists sessions as branchable JSONL history with parent identities, tree navigation, forking, cloning, resume, and explicit compaction. Mistral Vibe lazily restores session history, exposes retry provenance, supports managed shell sessions, and explicitly handles context clearing/compaction. OpenAI Codex restores thread-state metadata independently and preserves history across safe working-directory transitions.

MAIstro implication:

- durable `Run -> NodeRun -> Attempt` identity remains strategically correct;
- recovery should preserve logical history instead of reconstructing from transcripts;
- compaction is a projection over authoritative history, not the authoritative history itself;
- fork/replay semantics should become explicit platform concepts if/when MAIstro exposes interactive long-lived sessions.

## Cross-ecosystem trend 3: compaction quality is now an agent-runtime concern

Mistral Vibe has reactive compaction with dedicated summary fallback and stricter summaries. OpenAI reports benchmark improvements from retaining reasoning and enabling compaction. Pi exposes explicit manual compaction and branch/tree session history.

MAIstro implication:

- add a canonical `CompactionRecord` or equivalent provenance-bearing transition rather than silently rewriting context;
- retain source-range/reference identity so compacted context can escalate back to authoritative state;
- test repeated compaction, not just one-shot summaries;
- distinguish execution-history compaction from Turing epistemic forgetting/supersession.

## Cross-ecosystem trend 4: tool authority is becoming granular and runtime-specific

OpenAI Codex has per-environment shell variable policy and named permission profiles. Mistral Vibe exposes disabled-tool controls, connector enablement, per-tool prompt overrides, custom subagents, and human approval. OpenClaw heavily centralizes wire schemas, plugin/runtime metadata, and channel/plugin boundaries.

MAIstro implication:

- capability availability, provider eligibility, credentials, environment, and policy should stay in Binding/Invocation/runtime contracts rather than node definitions;
- tool enablement should be an authority decision, not merely prompt configuration;
- provider fallback must preserve the established Binding envelope;
- environment-sensitive authority should be part of the resolved execution context.

## Cross-ecosystem trend 5: authoritative metadata beats inferred metadata

OpenClaw's Aug 16/17 work explicitly makes migration metadata authoritative and verifies startup convergence against a fresh authoritative plugin snapshot. OpenAI Codex rejects obsolete permission metadata rather than silently dropping it. OpenHands preserves backend scope in conversation links and adds LLM profile pre-flight validation.

MAIstro implication:

- avoid reconstructing semantic state from labels/logs/transcripts when canonical records exist;
- `TraversalCommit`, `ResolvedBinding`, `PolicyVerdict`, approval records, and PromotionManifest should be authoritative transition artifacts;
- configuration migrations must preserve semantic identity and explicitly validate compatibility.

## Cross-ecosystem trend 6: structured outcomes and diagnostics

OpenHands added structured error outcomes and LLM pre-flight validation. OpenAI Codex has increasingly typed/actionable network diagnostics and explicit rejection of invalid authority configuration.

MAIstro implication:

- preserve structured terminal dispositions instead of collapsing everything to error strings;
- distinguish configuration/preflight failure from execution failure;
- preserve `UNKNOWN` external-effect outcomes under Invocation rather than guessing;
- add preflight phases for runtime/provider/credential/policy compatibility before creating irreversible external effects.

## Cross-ecosystem trend 7: self-improvement research is separating proposer from evaluator

Meta FAIR HyperAgents explicitly integrates task and meta agents into an editable self-referential system. Dr. Zero performs self-evolving search without training data. OpenAI GPT-Red uses automated self-play for robustness. Recent evaluation work across the ecosystem emphasizes evaluator reliability and benchmark contamination/quality.

MAIstro implication:

- Evolve candidate generation and candidate acceptance must remain distinct authorities;
- evaluator/promotion policy must not be mutable by ordinary candidate code;
- PromotionManifest should bind evaluator version, environment, corpus, evidence, and candidate identity;
- hidden/held-out evaluation and BehavioralContracts are justified by current frontier practice.

## Cross-ecosystem trend 8: personalization requires pre-action and post-action feedback

Meta PAHF explicitly uses a three-step loop: clarify before acting, ground action in remembered preferences, then integrate post-action feedback as preferences drift.

MAIstro implication for Turing:

- distinguish preference retrieval from confidence that a preference still applies;
- allow pre-action clarification when preference state is ambiguous;
- post-action feedback should create typed evidence/revision rather than directly mutate `I_LIKE` / `I_WANT`;
- preference drift requires versioned temporal state, not destructive overwrite.

## Cross-ecosystem trend 9: memory privacy/contextual integrity is a first-class problem

Meta CIMemories measures whether persistent memory disclosures are appropriate to the current task context and reports significant contextual-integrity violations in frontier systems.

MAIstro implication:

- memory `authority` must include disclosure/use scope, not merely truth/confidence;
- Turing retrieval should filter by contextual authority before ranking relevance;
- direct-ID, bulk, admin, and derived-memory paths must enforce the same scope;
- retrieval relevance must never imply permission to reveal or act on the retrieved state.

## Cross-ecosystem trend 10: retrieval is moving from iterative search toward planned, discriminative retrieval

Meta SIRA enriches both corpus and query and optimizes retrieval terms for discriminating desired evidence from confusers, reducing exploratory rounds.

MAIstro implication:

- semantic search should model retrieval as a planned capability with corpus-specific strategy and evidence discrimination, not only vector similarity;
- Turing retrieval should separate candidate generation, temporal/supersession resolution, authority filtering, evidence independence, and final relevance ranking;
- retrieval plans and their evidence could become first-class provenance when high-impact decisions depend on them.

## Cross-ecosystem trend 11: human expertise remains important even as execution becomes more autonomous

Anthropic's analysis of roughly 400k Claude Code sessions finds users generally retain planning decisions while Claude increasingly owns execution decisions; greater user expertise correlates with more successful and more leveraged agent use.

MAIstro implication:

- keep planning/goal authority separable from physical execution authority;
- expose high-level intent, accepted plan, and policy boundaries independently from low-level Attempts/Invocations;
- do not equate execution autonomy with authority to redefine goals.

## Cross-ecosystem trend 12: agent systems are becoming protocol/platform ecosystems

OpenClaw centralizes gateway-protocol schemas; OpenHands is separating SDK/runtime/platform concerns; Mistral Vibe unifies coding/work modes around reusable skills/connectors; Anthropic maintains agent SDKs and plugin ecosystems; OpenAI maintains Codex plus Agents SDKs.

MAIstro implication:

The existing convergence direction remains right:

`Workspace/Project -> Graph -> Run -> NodeRun -> Attempt`

alongside

`Capability -> Provider -> Binding -> Invocation`

with canonical Events/transition records between domains. Product surfaces and specialized cognitive systems should depend on these contracts rather than own competing lifecycle/state machinery.

## Immediate architecture actions suggested by this scan

1. Finish the Attempt/Invocation/Policy/Approval/TraversalCommit stack before adding new Turing lifecycle machinery.
2. Bind environment/policy versions explicitly into execution and invocation records.
3. Treat compaction as a provenance-bearing projection, never as destructive replacement of authoritative history.
4. Add configuration/preflight validation before externally effective Invocations.
5. Preserve structured outcome/disposition types, including unknown external outcomes.
6. Make contextual authority a first-class Turing memory dimension alongside truth, causality, and availability.
7. Add CandidateWisdom maturation and evidence-independence checks before durable reflective state gains high influence.
8. Build Evolve around separate proposer/evaluator/promotion authority, PromotionManifest, held-out evaluation, and BehavioralContracts.
9. Treat explicit transition artifacts as the common architecture pattern across Graph, capabilities, Evolve, and Turing.
10. Add frontier-derived adversarial tests for policy migration, stale environment state, scope bypass, compaction provenance, resume identity, and evaluator gaming.
