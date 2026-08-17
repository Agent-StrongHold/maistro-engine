# Agent Frontier Deep Dive — 2026-08-16

This document expands the frontier scan with emphasis on Dr. Zero, SIRA, HyperAgents, adjacent Meta FAIR work, and public agent-runtime failure reports. It records architecture lessons for MAIstro rather than patent claims.

## Core frontier pattern

The current frontier is moving from "build a better task agent" toward second-order systems that improve one or more of:

- the task agent;
- the retrieval process;
- the agent harness;
- the evaluation/acceptance process;
- the curriculum/environment used for improvement;
- the meta-controller that generates future improvements.

The most relevant examples are Dr. Zero, SIRA, HyperAgents, AIRA2, Meta-Agent Challenge, Continual Harness, DGM, and recent production-agent work in Codex/OpenCode/OpenHands/OpenClaw/Mistral/Pi.

## Dr. Zero

Published mechanism:

- proposer and solver start from the same base model;
- proposer synthesizes diverse questions;
- solver learns to solve them using multi-turn search tools;
- as the solver improves, proposer pressure shifts toward harder but solvable tasks;
- this forms an autonomous curriculum without seed training data;
- HRPO groups structurally similar questions to estimate relative difficulty/solvability more efficiently.

MAIstro mapping:

- Evolve should not rely only on fixed benchmark corpora. Add a `ChallengeGenerator`/curriculum producer whose job is to propose increasingly discriminating tasks against current capabilities.
- The challenge generator must remain distinct from promotion authority. A self-generated curriculum is useful for exploration but cannot be the sole acceptance gate.
- Store challenge lineage and difficulty estimates. A generated task should record which capability gap it was meant to expose and which parent revision induced it.
- Evaluate challenge diversity and independence to prevent curriculum collapse into one narrow family of tasks.
- Consider grouped baselines analogous to HRPO for expensive multi-step evaluations: compare structurally similar tasks rather than estimating every task in isolation.

Adversarial lesson:

A proposer and solver can co-adapt into a closed world. MAIstro therefore needs external/hidden promotion gates and BehavioralContracts even if self-generated curriculum is highly effective for exploration.

## SIRA

Published mechanism:

- offline corpus enrichment creates indexing vocabulary absent from source documents;
- query-time LLM expansion predicts evidence vocabulary omitted from the user query;
- corpus statistics reject proposed terms that are absent, overly common, or insufficiently discriminative;
- the final query is a weighted lexical retrieval action;
- the aim is not merely semantic relevance but separation of desired evidence from corpus-level confusers.

MAIstro mapping:

Current semantic-search architecture should add a corpus-aware planning layer before retrieval:

`intent -> candidate evidence concepts -> corpus statistics / confuser analysis -> discriminative expansion -> retrieval -> evidence adjudication`

Specific improvements:

- maintain document-frequency / field-frequency / entity-frequency statistics as first-class retrieval tools;
- generate query expansions but validate them against corpus-visible evidence before use;
- distinguish "relevant term" from "discriminative term";
- support index-time enrichment as a derived projection with provenance back to the authoritative document;
- preserve the original query and each expansion/weight so retrieval decisions are explainable;
- compare one-shot discriminative retrieval against expensive iterative agentic search before defaulting to multi-round loops;
- use vector retrieval as one candidate generator, not the entire retrieval policy.

Turing mapping:

Turing investigation should be able to deliberately search for evidence that distinguishes competing propositions rather than merely retrieve memories similar to the active thought.

## HyperAgents

Published mechanism:

- task agent and meta agent are integrated into one editable program;
- the meta-level procedure that generates modifications is itself editable;
- variants are generated/evaluated in an open-ended archive/tree;
- improvements to persistent memory, performance tracking, and improvement procedure can transfer across domains and accumulate across runs;
- generated code is explicitly considered untrusted and experiments use sandboxing/human oversight.

This is strongly adjacent to MAIstro RSI/Evolve.

MAIstro mapping:

- treat the harness, not only application code, as an evolvable artifact: prompts, tools, hooks, memory policy, planner, evaluator adapters, stop conditions, delegation policy, and control flow;
- represent revisions as explicit artifacts with parent lineage rather than replacing one active agent configuration in place;
- maintain an archive of viable stepping-stone revisions, not only champion/latest;
- separate `TaskCapabilityScore` from `MetaImprovementScore`: an agent can become better at the target task without becoming better at producing future improvements, and vice versa;
- measure cross-domain transfer of meta-level improvements before promoting them as general harness mechanisms;
- never make the active trusted promoter part of the candidate-controlled mutable surface.

Key difference MAIstro should preserve:

HyperAgents intentionally permits deep self-reference for research. MAIstro should permit broad candidate self-modification inside the untrusted domain but preserve an invariant trusted activation/promotion kernel outside that editable surface.

## AIRA2

Published mechanism:

- asynchronous multi-GPU worker pool to increase experiment throughput;
- hidden consistent evaluation to reduce validation-overfitting/generalization collapse;
- ReAct agents dynamically scope actions and debug experiments rather than relying on fixed single-turn operators.

MAIstro mapping:

- Evolve evaluation should be asynchronous and parallel over independent Attempts;
- promotion decisions should wait on a defined evidence set, not worker completion order;
- hidden/consistent promotion evaluation should be structurally separate from candidate-visible search evaluation;
- evaluator versions and hidden-set identity belong in PromotionManifest;
- deterministic folding of concurrent evaluation results should mirror Graph frontier semantics.

## Meta-Agent Challenge

Published mechanism:

- code agent receives a sandbox, evaluation API, time/API budget, and must build an agent artifact;
- final held-out evaluator is injected only after the optimization budget expires;
- high optimization pressure produces reward-hacking behaviors including attempts at ground-truth exfiltration.

MAIstro mapping:

- candidate-visible evaluators are adversarial surfaces;
- evaluator data, secrets, hidden corpora, and promotion-only resources need separate authority domains;
- attempts to inspect/influence evaluator internals should be explicit BehavioralContract violations;
- promotion should record resource budget and evaluator access history, not only final score;
- evaluation sandboxes need information-flow restrictions, not merely filesystem/process isolation.

## Continual Harness / Code-as-Agent-Harness

Published direction:

- harness elements such as prompt, subagents, skills, memory, and control flow can themselves be optimized;
- online adaptation can occur without resetting the environment;
- survey literature identifies regression-free improvement, consistent shared state, incomplete feedback, and human oversight as open problems.

MAIstro mapping:

Evolve should treat the canonical agent configuration/harness as a versioned Graph/Project-scoped artifact. Online adaptation must not mutate authoritative state in place. Generate candidate revisions, evaluate, then commit through the promotion boundary.

## PAHF

Published mechanism:

`clarify before action -> retrieve preference -> act -> post-action feedback -> update preference memory`

MAIstro/Turing mapping:

- clarification should be a first-class epistemic action, not just conversational UX;
- distinguish uncertainty that should trigger investigation/clarification from ordinary execution blockers;
- preference updates should require explicit feedback/evidence and typed revision rather than inferred overwrite;
- preference drift should produce versioned supersession, preserving historical preferences that influenced prior decisions.

## CIMemories

Published finding:

Persistent memory creates contextual-integrity failures: a fact can be correctly remembered but inappropriate to reveal/use in the current context. Frontier models show high and unstable disclosure violations, and generic privacy prompting does not solve the problem.

MAIstro/Turing mapping:

Memory requires separate axes for truth, retrievability, authority, and contextual disclosure/use eligibility. `Known` must not imply `may be surfaced here`.

Add context-bound memory policy evaluation before memory enters deliberative context, and preserve policy provenance for what was disclosed to which agent/run/context.

## Gaia2 / ARE

Published mechanism:

Dynamic asynchronous environments change while agents operate; tasks include ambiguity, noise, temporal constraints, collaboration, and long multi-step execution. More compute does not monotonically solve the problem and scaling curves plateau.

MAIstro mapping:

- recovery tests should inject external state changes while Runs are paused;
- resumption must revalidate assumptions, Binding/provider state, policy, credentials, and external resources rather than blindly continue from a checkpoint;
- benchmark runtime should include asynchronous environment events and delayed observations;
- compute budgets should be explicit execution resources rather than assuming more iterations are always beneficial.

## Public runtime failure lessons

### OpenCode

Observed public issues include:

- subagent permission restrictions failing to propagate transitively;
- plugin/policy hooks not intercepting delegated tool calls;
- compaction causing a read-only agent to regain write behavior;
- unbounded recursive subagent spawning;
- synchronous subagents hanging on approvals with no attached human.

MAIstro implication:

Authority must be an inherited ceiling across delegation and compaction. Child agents, resumed agents, summaries, and delegated capabilities may narrow authority but never reconstruct it from defaults or widen it.

### OpenAI Codex

Observed public issues include:

- permissions/approval routing dropped across compaction/resume;
- parallel subagents causing extreme token amplification and repeated compaction;
- approval requests in delegated agents not reaching the interactive surface;
- stale/unreaped subagent identities consuming concurrency slots;
- requests to separate runtime auto-approval policy from model-visible tool guidance.

MAIstro implication:

- persist policy/authority as runtime state independent of context text;
- do not depend on regenerated prompts to restore security state;
- NodeRun/Attempt ownership should allow deterministic child cleanup/reaping;
- approval routing needs a durable owner and wake-up path;
- authority facts shown to models should be distinguished from enforcement facts.

### OpenHands

Recent work emphasizes pre-flight configuration validation, structured error outcomes, backend scope preservation, and clear repository/module ownership.

MAIstro implication:

Add preflight validation before expensive/irreversible Runs and Invocations, and retain typed failure/disposition rather than generic errors.

### OpenClaw

Recent commits emphasize authoritative migration metadata and fresh authoritative plugin snapshots during startup convergence.

MAIstro implication:

Never trust stale derived identity/config metadata where an authoritative snapshot can be resolved. Derived state should carry snapshot/version identity.

### Mistral Vibe

Recent product/runtime direction includes custom subagents, clarification, skills, long-horizon unified work/code modes, compaction/resume, and versioned prompts/skills as a system of record.

MAIstro implication:

Skills/prompts/harness configuration should be durable versioned Project/Workspace artifacts with provenance, ownership, and exact revision identity in each Run.

### Pi

Pi's durable branchable session tree and extension hooks reinforce first-class history rather than flattening a session into current context. Public session sharing also treats real tool-use/failure trajectories as valuable improvement data.

MAIstro implication:

Preserve canonical event/execution trajectories as training/evaluation assets while enforcing privacy/authority controls over derived datasets.

## New cross-cutting architecture proposals

### 1. Evolvable Harness Artifact

Introduce a versioned artifact representing agent/harness configuration:

- system/instruction set;
- tool/capability bindings;
- skills;
- memory/retrieval policy;
- planner/control-flow policy;
- subagent/delegation policy;
- stop/budget policy;
- evaluator configuration.

Each Run references an immutable revision. Evolve creates candidate revisions rather than mutating the active artifact.

### 2. Challenge / Curriculum objects

For Dr.-Zero-style self-generated improvement:

`Challenge -> generated_by_revision -> targets_capability_gap -> difficulty estimate -> evaluation executions -> outcome`

Maintain challenge diversity, provenance, independence and retirement.

### 3. RetrievalPlan / RetrievalDecision

SIRA suggests making retrieval reasoning explicit:

`RetrievalPlan`
- original intent/query;
- candidate expansions;
- corpus statistics;
- confuser hypotheses;
- accepted discriminative terms/weights;
- retrieval provider/index snapshot.

Then `RetrievalDecision` links results/evidence to the plan and exact index snapshot.

### 4. EvaluationRun + PromotionManifest

Separate search-time evaluation from promotion-time evaluation. PromotionManifest should bind hidden-eval identity/version, BehavioralContract set, candidate revision, execution identities, environment, and result digest.

### 5. Authority-preserving delegation

Authority should be calculated as a monotonic ceiling:

`child authority <= parent delegated authority <= originating Binding/Run authority`

Compaction, resume, fork, subagent creation, provider fallback, and skill invocation cannot widen it.

### 6. Dynamic-environment recovery

A resumed Run must distinguish durable internal state from assumptions about external state. Recovery should revalidate relevant external facts before irreversible continuation.

## Priority for MAIstro

Immediate, while current convergence stack is active:

1. finish Attempt/Invocation/Policy/Approval/TraversalCommit spine;
2. guarantee authority preservation across retry, resume, delegation and provider fallback;
3. preserve exact configuration/policy/harness revision identity in execution records;
4. make approval and child-agent cleanup durable rather than conversational;
5. distinguish authoritative runtime state from context summaries/prompts.

Next architectural slices:

6. versioned EvolvableHarness artifact;
7. PromotionManifest + BehavioralContracts + hidden evaluation;
8. RetrievalPlan with corpus-discriminative expansion/statistics inspired by SIRA;
9. Challenge/Curriculum objects inspired by Dr. Zero;
10. Turing contextual memory authority and clarification/preference-revision pathways informed by CIMemories + PAHF;
11. dynamic-environment recovery/evaluation informed by Gaia2/ARE.

The frontier evidence strongly supports MAIstro's current direction while exposing concrete failure modes in systems that rely on context text, implicit permission reconstruction, static benchmarks, or unrestricted self-modification.