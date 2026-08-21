# MAIstro Coordinated Backlog

**Operational branch:** `develop` is the newest active integration branch. Topic backlog changes follow ADR-095 and land through a PR into `develop`.

This file is the human-readable execution ledger during convergence. It replaces the old four-repo milestone ordering with one coordinated dependency plan. Legacy `engine-*`, `maistro-*`, `turing-*`, and `sh-*` IDs remain stable as source references; they do **not** define execution order.

The architecture source of truth remains the Accepted ADR/spec corpus and `docs/CONVERGENCE-PLAN.md`. This backlog coordinates implementation; it does not override an ADR.

## Scheduling law

1. **Convergence is highest priority.**
2. **Replacement-before-connection exception:** if an approved/planned item will replace a surface that the next convergence step would otherwise connect, build the minimum viable replacement immediately before that connection. Do not wire a disposable implementation and remove it one PR later.
3. After that replacement seam is established, return immediately to convergence.
4. Do not create new universal execution, authorization, event, capability, memory, or persistence lifecycles. Extend the canonical ones.
5. Optional product/frontier work may preserve hooks during convergence but does not preempt the convergence trunk.
6. Turing is an optional MAIstro extension. Convergence removes accidental parallel platform ownership; it does not activate or replace Turing.
7. Status is evidence-derived. “Done” means the declared acceptance criteria are tested and reachable through a real product path, not merely implemented in an isolated module.

Canonical execution:
```text
Workspace / Project
    ↓
Persona
    ↓
Graph / Node
    ↓
Run
    ↓
NodeRun
    ↓
Attempt
    ↓
ExecutionRuntime
```

Canonical fulfillment:
```text
Capability → Provider → Binding → Invocation
```

Canonical improvement:
```text
Run evidence
  → evaluation
  → improvement proposal
  → candidate version
  → sandbox / trials
  → evaluation
  → policy / HITL promotion
  → promoted Template / Skill / Policy / Code version
```

## Priority classes

| Class | Meaning |
|---|---|
| **C0** | Active convergence work. Nothing unrelated jumps ahead. |
| **C1–C6** | Remaining convergence dependency chain. |
| **R** | Replacement-before-connection item. May jump immediately ahead of the exact C-step that would otherwise wire its predecessor. |
| **V** | v1 stabilization/release work after convergence, except safety/CI required to land C-work. |
| **F** | Post-convergence frontier/continual-improvement work. |
| **P** | Product/UX/platform expansion after the canonical substrate is converged. |
| **H** | Historical, implemented, abandoned, superseded, or revalidation-only source item. |

---

# Canonical execution queue

## C0 — Land the reachability wiring already in flight — COMPLETE

PR #480 merged into `develop` on 2026-08-21.

What it closed:
- static reachability for graph node registration;
- real `graph.compaction` wiring;
- stage-aware retry policy and coordinated 429 handling;
- Hive streaming DAG signature bug;
- live `maistro_design.nodes` registration and bundled design-system loading;
- reachability baseline reduction from 234 to 205.

Still intentionally not invented:
- graph steering has no real producer/consumer yet;
- context probing has no real prober yet;
- credential pooling waits for the governed Provider/Invocation seam in C4.

**Rule:** those omissions remain honest gaps until their owning canonical seam exists. Do not wire them as stand-alone islands.

## C1 — Make Workspace / Project / Persona / Template ownership ordinary

**Goal:** every durable definition and mutable object has one canonical owner before more execution paths are connected.

Work:
1. Wire `Workspace` and `WorkspaceMembership` into core composition/container and Hive.
2. Create exactly one persisted Root Project with each Workspace.
3. Put every persisted Graph in exactly one Project with immutable `workspace_id` + `project_id` captured in Run snapshots.
4. Enforce Project tree rules, scoped resource visibility, grant/deny semantics, move validation, and child-Run same-Workspace rules.
5. Extend the existing Persona surface. Do not create a second Persona or treat Persona as an actor/ACL.
6. Finish `NodeTemplate → Node` and `GraphTemplate → Graph` copy-plus-provenance semantics; immutable Template versions; explicit save-as-template.
7. Add architecture-fitness enforcement forbidding a new universal run-lifecycle definition or outward dependency that competes with core ownership.
8. Reconcile older AgentRecipe/AgentSpec/AgentIdentity/PM-fleet definition formats into Template/Node/Graph projections without deleting useful domain semantics.

**Exit:**
- Workspace/Project/Persona/Template spine criteria at least `passing` and product-reachable where applicable;
- Workspace/Project modules removed from the reachability debt;
- no new mutable definition can exist without a canonical Workspace/Project owner.

**Primary decisions:** ADR-081226-9944, ADR-081426-b1d3, ADR-081226-e626, ADR-081226-bb3a, ADR-081226-6e34, ADR-081226-034b.

## C2 — Every work producer creates a canonical Run

**Goal:** one logical execution history everywhere.

Order:
1. **Task ingress → Run.** `TaskQueue.submit` remains ingress/admission but mints/links a canonical Run. Queue state may exist before admission; it does not own post-admission execution lifecycle.
2. **Chat turn → single-node Graph/Run.** `conduit.route_request` is the generic front door; Hive follows the same service.
3. **Events/reactor/schedules → Run per firing.** Trigger/schedule records remain definitions/receipts, not competing execution histories.
4. **Builders → canonical graph executor.** Retire Builders `RunState` and `GraphPipelineExecutor` after parity.
5. **Orchestrator waves → Graph nodes/subgraphs.** Preserve useful fan-out/fan-in policy, not a second runtime.
6. **A2A/delegation → child Runs.** Preserve transport/delegation records as projections/receipts.
7. **PM runner / repertoire / other stragglers → Run.**
8. **Hive graph execution → durable canonical Graph/Run path.** Remove private LLM callable from graph execution.
9. **Hive `DagRun` store → adapter/projection → delete.**
10. Preserve lane/priority policy semantics as admission/scheduling policy while retiring duplicate universal lifecycle ownership.

**Exit:**
- one production Run/NodeRun/Attempt model;
- no `GraphRun`, `DagRun`, Builders `RunState`, task status, or A2A lifecycle can claim universal execution ownership;
- ADR-081226-a66b, ADR-081226-69ee, ADR-081426-1f7c are product-reachable.

**Dedup decision:** legacy `engine-097` and `maistro-200` are satisfied/superseded by this canonical graph/runtime convergence. Do not build another “Hyperagent graph runtime.”

## R1 — Workspace backlog repository seam before RSI is connected

**Trigger:** execute immediately before C3 reaches the RSI work-source connection. This is the explicit replacement-before-connection exception.

Why it jumps:
- wiring RSI directly to a Markdown parser would create a disposable execution dependency;
- the intended replacement is Workspace-owned structured backlog state.

Minimum replacement needed before RSI connection:
1. Define a Workspace-scoped Backlog repository/service contract with stable item IDs.
2. Model status, priority, dependencies, acceptance/evidence refs, allowed/protected scope, risk, parent/child relationships, provenance, version, claim/lease, partial progress, blockers, candidate/PR/eval links, cost, and resulting Learnings.
3. Atomic eligible-work claim/lease semantics so concurrent Runs cannot silently duplicate work.
4. Evidence-driven completion/reopen semantics.
5. Provide a Markdown import/export adapter so this file remains usable during migration.
6. Do **not** require the full Conductor backlog UI before returning to convergence.

Source items: `engine-113` (minimum service portion), prepares `engine-112` and later `engine-114/115`.

**Exit:** RSI can consume a repository interface whose durable implementation is the target architecture; Markdown is compatibility/import-export, not the runtime contract.

## C3 — Converge product islands onto the spine

**Goal:** Builders, RSI, Evolve, Canvas/Design, Hive, and any currently reachable Turing surface use the same execution spine.

Order:
1. Builders parity/deletion tail from C2.
2. **R1**, then RSI:
   - coordinator/autorun/RsiRunner create canonical Runs;
   - backlog/scenario/regression/security/operator sources normalize into one authorized objective/work-request type;
   - local-loop subprocess work becomes fenced Attempts under `ExecutionRuntime`;
   - bounded campaign controls remain policy, not lifecycle.
3. Evolve:
   - one evolution cycle becomes a Graph/Run;
   - tournament/evaluation battles become Nodes/NodeRuns;
   - domain population/fitness state remains Evolve-owned;
   - candidate promotion records provenance rather than mutating execution history.
4. Canvas/Design:
   - pipeline stages are Nodes;
   - domain assets remain domain-owned;
   - Hive canvas/design DAGs converge on canonical Graph execution.
5. Attempt lease/fencing:
   - all production physical execution that can recover/retry carries the current execution fence;
   - recovery cannot let stale workers mutate newer Attempts.
6. Finish resilience integration only at owning seams: depth/compaction/steering where real producers exist, retry/rate/context mechanics in Runtime/provider paths.
7. Hive `chat_completion.py` last:
   - parity tests first;
   - decompose the bespoke loop onto Conduit + canonical Run + governed tool/model fulfillment.
8. Existing Turing package entry points that are product-reachable must use canonical Runs/Bindings, but no optional cognitive/autonomous feature is activated.

**Exit:**
- Builders/RSI/Evolve/Canvas/Design execution islands reduced to adapters/domain state, not separate runtimes;
- all product work visible in the same Run store;
- physical recovery paths fenced;
- Turing remains optional and off unless explicitly invoked/configured.

## C4 — Universal governed fulfillment

**Goal:** every external/model/tool/harness/agent effect passes through one auditable authorization and fulfillment seam.

Work:
1. Compose the governed capability service in the core container.
2. Registry returns governed Binding/Invocation handles, not raw provider escape hatches.
3. Close the harness twin door: ungoverned `send()` delegates to governed invocation.
4. Establish one LLM egress; migrate all direct provider clusters.
5. Wire credential pool/rotation at Provider selection/Invocation, where failures and selected credentials are actually known.
6. Tools execute as capability providers/bindings; fold in existing SSRF/sandbox/reversibility controls.
7. MCP gets the same Warden/policy/binding enforcement.
8. Agent delegation is an ordinary provider/binding case plus child Run correlation.
9. Converge human approval flows (tool, prompt, learning, self-repair) on one approval Capability while preserving domain-specific state machines.
10. Delete duplicate approval/gate implementations after parity.
11. Turn the direct-provider-call rule into a blocking CI invariant.

**Exit:**
- bypass list = 0;
- one model egress;
- every effect has an Invocation record;
- credentials are resolved only at Invocation;
- security policy cannot be bypassed by choosing a different transport surface.

## C5 — One event/checkpoint/recovery/observability/knowledge correlation plane

**Goal:** canonical correlation makes live UI, recovery, audit, evaluation, memory, and later self-improvement consume the same evidence.

Work:
1. Converge Graph events, Builders stage events, task progress, collaboration/runtime callbacks, and package-specific progress onto the canonical Event envelope.
2. One durable Workspace sequence authority; package-local sequence values only as domain payload metadata.
3. Converge checkpoints/recovery under Run/NodeRun/Attempt; queue/schedule records remain ingress/trigger state.
4. Correlate `workspace_id`, `project_id`, `run_id`, `node_run_id`, `attempt_id`, `invocation_id`, `session_id`, and `trace_id`.
5. Wire recording proxies at the single C4 egress.
6. Close required metrics/spans/event topics/log context/retention gaps from ADR-037/SPEC-228.
7. Keep Memory types/stores but align scope IDs and evidence provenance to canonical Run/Outcome/Event IDs.
8. Keep Artifact/Session distinct from Run but correlate them canonically.
9. Preserve the data needed for future validated-learning promotion: source Runs, evaluations, candidate versions, confidence, provenance, and applicability scope.
10. Recovery/backup work must restore authoritative domain records, not revive deleted duplicate lifecycles.

**Exit:**
- one trace can follow a user request through Run → Attempt → Invocation → Event/Outcome;
- recovery reconstructs from canonical records;
- memory/evaluation evidence is attributable to the exact execution that produced it.

## C6 — Burn duplicate architecture to zero and make it impossible to regrow

Work:
1. Delete retired `GraphPipelineExecutor`, Builders `RunState`, legacy `GraphRun`/`DagRun` lifecycle stores, `LaneGate` if no unique policy remains, duplicate approval gates, and other parity-proven compatibility owners.
2. Drive reachability baseline monotonically downward; document intentional library-only surfaces explicitly.
3. Turn acceptance-state completion claims into CI gates: no “implemented/done” claim below `reachable`.
4. Finish prose-only criteria retrofit when a layer is touched; do not stop convergence for unrelated documentation churn.
5. Add architecture-fitness invariants:
   - no new universal execution lifecycle;
   - no direct effect/provider bypass;
   - core dependency direction points inward;
   - no duplicate durable event sequence authority;
   - no unscoped Workspace/Project durable object;
   - no stale compatibility owner presented as canonical.
6. Reconcile old backlog/ADR drift created by monorepo consolidation; mark superseded/abandoned source items rather than silently carrying them forward.
7. Keep mutation, property, conformance, reachability, complexity, dead-code, secret, and lifecycle ratchets monotone.

**Exit / full convergence:**
- one Run model;
- one governed effect path;
- one canonical durable event/correlation plane;
- every product island connected or deliberately removed;
- replacement targets, not predecessors, are what production paths use;
- no known duplicate owner can become canonical by accident.

## V1 — Stabilize, verify, promote, release

This starts after C6 except for security/CI repairs required to land convergence.

Re-audit `docs/product/V1-RELEASE-PLAN.md` against the current tree before executing stale checklist text.

Remaining ship classes:
1. Enforce ADR-095 branch protections/status checks on `develop`, `integration`, and `main`.
2. Resolve only deployability/security gaps that block a truthful v1; keep intentionally deferred limitations in `KNOWN-GAPS.md`.
3. Verify version single-source/tag guards and run the actual release pipeline rather than assuming the workflow is valid.
4. Clean-machine Conductor install/wizard/auth/Graph/real-model execution.
5. RSI + Evolve through the Conductor UI end-to-end on the converged runtime.
6. Verify degraded modes are explicit, never fake success.
7. RC promotion to `integration`, signed/tagged release candidate, soak, repeat if required.
8. Promote byte-equivalent soaked commit to `main`; signed `v1.0.0`; external install and cosign verification.
9. Publish known limitations and immediately seed v1.1 from deliberate deferrals.

**Important current evidence:** ADR-095 requires protected PR-gated branches; GitHub currently reports `develop` unprotected. Treat this as a V1 gate, not a reason to stop C1–C6.

---

# Post-convergence frontier program

These items are coordinated now so convergence preserves the right seams, but implementation follows C6 unless a narrowly defined replacement hook is triggered.

## F1 — Canonical continual-improvement / promotion loop

Deduplicates:
- `engine-051`;
- `sh-101`, `sh-200`;
- RSI recursive improvement;
- Evolve candidate promotion;
- graph optimizer proposals;
- prompt/skill/code/policy improvement workflows.

One mechanism:
```text
evidence
→ evaluation
→ proposal
→ immutable candidate version
→ sandbox trials
→ evaluation
→ policy / HITL
→ promotion
→ new production version
```

Rules:
- never mutate historical Runs or source execution snapshots;
- candidate creation is not promotion;
- promotion is scoped, versioned, reversible where possible, and provenance-complete;
- RSI/Evolve/GraphOptimizer become producers/consumers of this substrate, not owners of parallel promotion systems.

## F2 — Validated collective learning / cultural evolution

Generalize CoinSwarm’s strongest mechanism without importing a new top-level `Wisdom` noun.

```text
local execution experience
→ Memory / Outcome / Learning
→ repeated evidence
→ eval / Gauntlet
→ distillation
→ confidence + provenance + scope
→ reusable Workspace knowledge / repertoire
→ future Runs
```

Deduplicates:
- memory v2/drift/backup work where it concerns learned knowledge;
- Repertoire learning;
- CoinSwarm Tier-7 Wisdom concept;
- prompt/skill improvement evidence;
- Turing memory inheritance ideas where they apply generically.

Requirements:
- keep agent/local memory distinct from promoted collective knowledge;
- future unrelated agents may reuse validated learning;
- retrieve by relevance/applicability, not global broadcast;
- preserve diversity and negative evidence;
- no learned rule can broaden permissions or bypass policy.

## F3 — Candidate sandbox / evaluation worlds

Deduplicates chaos, shadow-workspace, phantom execution, code-registry isolation, and agentic-sandbox research.

Target capabilities:
- persistent but isolated candidate environments;
- branch/snapshot/restore;
- deterministic fixture/eval worlds;
- network/credential/budget policy;
- stale-write fencing;
- reproducible evaluation artifact;
- rollback/cleanup.

This is the trial substrate for F1, not another execution hierarchy. Trials are still Runs/Attempts.

## F4 — Optional Turing continual/autonomous cognition

Turing remains an extension that may later:
- maintain self-model/drives/mood/persistent cognition;
- originate authorized work;
- call F1/F2/Evolve/RSI;
- reason across historical Runs;
- run self-talk/dream/phantom processes;
- propose changes.

Guardrails:
- no Turing-owned Run/Graph/authorization/capability/event universe;
- explicit activation gate;
- delegated scope and budgets;
- canonical Events/Invocations;
- improvement candidates pass F1 promotion;
- no automatic activation merely because convergence makes the substrate available.

All `turing-*` cognitive features remain here unless the task is purely migration of an already-reachable Turing path onto C1–C5.

## F5 — Population evolution, diversity, and tournament evidence

Deduplicates:
- `engine-073`, `engine-096`;
- `sh-102`;
- `turing-062`;
- Evolve tournaments;
- CoinSwarm population/convergence techniques.

Use only where population search adds measurable lift over ordinary candidate evaluation.

Requirements:
- out-of-sample/held-out evaluation;
- minimum sample/fitness gates;
- diversity/convergence monitoring;
- lineage/provenance;
- no production promotion outside F1 policy gate;
- collective learning feeds F2 only after validation.

---

# Product/platform expansion after convergence

These remain legitimate backlog, but do not interleave with C1–C6 unless a specific item is the replacement for something C-work would otherwise wire.

## P1 — Backlog UI and authority cutover

- `engine-114`: Conductor backlog UI over the R1 Workspace backlog service.
- `engine-115`: E2E migration/cutover. DB becomes canonical only after persistence, UI edit, agent read/write, claim/lease, provenance, and restart durability are proven.
- After cutover this Markdown file becomes generated/exported. Until then it remains an editable human-readable authority, backed by the repository contract rather than a special RSI parser.

## P2 — Product UX, catalogs, channels, portability, deployment extensions

Includes:
- A2UI/chat UI, low-code graph designer, Canvas UI/backend expansion;
- MCP/default/CLI-Anything catalogs and skills;
- voice/email/Alexa and cross-deployment A2A experiences;
- Copier/distribution templates that remain relevant after monorepo/convergence revalidation;
- hardware/DID/networking/crypto integrations not needed for the v1 convergence substrate;
- Stronghold multi-tenant/compliance product expansion.

Each must enter through C1–C5 contracts. None may introduce a private runtime, provider bypass, event bus, memory owner, or permission model.

---

# Replacement-before-connection gates

| When convergence reaches… | Do this first only if predecessor would otherwise be wired | Then resume |
|---|---|---|
| RSI work-source integration | R1 minimal DB-backed Workspace backlog repository/service (`engine-113`) | C3 RSI (`engine-112`) |
| Builders/Hive/Hyperagent execution | canonical Graph/Run executor, not `engine-097`/`maistro-200` | C2/C3 |
| new tool/MCP/model/harness wiring | governed Binding/Invocation handle | C4 |
| approval wiring | common human Approval Capability, not another gate | C4 |
| new execution recovery | Attempt lease/fence + canonical checkpoint state | C3/C5 |
| new learning shared across agents | F2 validation/promotion contract; do not globally broadcast raw memory | F2 when post-convergence work begins |

No replacement jumps the queue merely because it is newer. It jumps only when the immediate convergence step would otherwise connect code that the replacement will remove.

---

# Accepted-decision coverage ledger

This is a coordination ledger, not a substitute for front-matter status. `develop` is authoritative.

| Accepted decision family | Canonical owner |
|---|---|
| ADR-002..009: porting, agent/schema/recipe/variant/parser/spawner contracts | C1/C2; preserve useful definitions as Templates/Nodes and execution adapters |
| ADR-010: lane scheduling | C2 admission/scheduling policy; do not preserve a duplicate lifecycle merely to preserve `LaneGate` |
| ADR-011..017 + ADR-034: memory engine/types/protocols/learnings/episodes/outcomes/ownership | C5 now, F2 for validated collective promotion |
| ADR-018: task-record persistence | C2 ingress durability only; post-admission truth is Run/NodeRun/Attempt |
| ADR-019: canonical source/package ownership | C1/C6, interpreted with ADR-081226-034b and monorepo reality |
| ADR-031/032: registry + acceptance contracts | C6 continuous quality/coverage enforcement |
| ADR-033: templates/Copier | C1 for runtime Template semantics; P2 for repository/product scaffolding |
| ADR-035: catalog ownership | C4/P2; catalogs expose authorized Bindings/skills, not raw bypasses |
| ADR-036: semantic object layer | C1/P2; keep domain semantics, no new execution owner |
| ADR-037: observability taxonomy | C5 |
| ADR-038: reliability taxonomy | C3/C4/C5 |
| ADR-039: external-library adoption policy | invariant for all P/F external adoption |
| ADR-062: graph execution protocol | C2/C3, reconciled into canonical Graph/Run |
| ADR-063: credential pool/rotation | C4 at real Provider/Invocation egress |
| ADR-064: secret redaction | already reachable; continuous security invariant |
| ADR-076: HTTP API content negotiation | deliberate v1.1 limitation unless convergence makes it unavoidable; do not preempt C1–C6 |
| ADR-095: four-tier branch model | V1 enforcement; branch flow is already the working rule |
| ADR-100: bundled design systems | C0/#480 made the live loader reachable; domain catalog continues under P2 |
| ADR-081226-034b: package ownership/dependency direction | C1/C6 |
| ADR-081226-9944: canonical product hierarchy/ownership | C1 |
| ADR-081426-b1d3: Project scope tree | C1 |
| ADR-081226-e626: Persona/surface model | C1 |
| ADR-081226-bb3a: Template/object/provenance | C1/F1 promotion semantics |
| ADR-081226-6e34: scoped grants/deny-wins | C1/C4 |
| ADR-081226-a66b: Run/NodeRun/Attempt | C2/C3 |
| ADR-081226-69ee: Graph/Node execution model | C2/C3 |
| ADR-081426-1f7c: ExecutionRuntime | C2/C3 |
| ADR-081226-6b46: Capability/Provider/Binding/Invocation | C4 |
| ADR-081226-7248: Event/checkpoint model | C5 |
| ADR-081626-f383: Attempt execution leases/fencing | C3/C5 |

**Coverage rule for any Accepted ADR not explicitly listed above:** it is not automatically a new backlog project. Its unmet acceptance criteria are assigned to the canonical C/V/F/P owner whose substrate they modify. `scripts/check-ac-state.py --run-tests` is the authoritative criterion-level inventory, so a later Accepted ADR cannot silently fall out of this plan.

**Proposed Turing gate:** ADR-081426-fb9f is intentionally not in the Accepted table. It preserves future Turing capability and explicitly does not activate it; owner F4.

---

# Legacy backlog disposition ledger

The old IDs remain stable so links and history resolve. This ledger says where each item belongs now. The original detailed wording remains in git history and the linked ADR/specs.

## `engine-*`

| IDs | Disposition |
|---|---|
| `engine-001..004` | C6 governance/registry/doc hygiene; re-evaluate already-landed portions before work |
| `engine-010..013` | P2/V; repository/product scaffolding and release packaging, not execution convergence |
| `engine-020..022` | H/C6; monorepo drift/dedup cleanup, execute only where current tree still proves debt |
| `engine-030` | C1/P2 semantic-object work, only if required by reachable products |
| `engine-031` | C5 |
| `engine-032` | C3/C4/C5 |
| `engine-040..043` | C6 quality contracts/ratchets |
| `engine-050` | P2 portability |
| `engine-051` | F1 |
| `engine-052` | C6/V compliance audit |
| `engine-060` | F2 |
| `engine-061` | P2 research/eval, evidence-gated |
| `engine-062` | C4/P2 routing improvement |
| `engine-070..072` | P2 ontology expansion |
| `engine-073` | F5 |
| `engine-080..081` | C6 tooling choices only if current gaps remain |
| `engine-082` | F2/V backup/export semantics |
| `engine-083` | C5/V disaster recovery |
| `engine-084` | F3 |
| `engine-085` | C5/P2 long-term trace export |
| `engine-090..091` | P2 A2UI/chat surface |
| `engine-092..095` | P2 catalogs/skills; must use C4 Binding/Invocation |
| `engine-096` | F5 |
| `engine-097` | C2, **deduped/superseded by canonical Graph/Run runtime; do not build separately** |
| `engine-098` | F2 |
| `engine-099` | F2/P2 context/retrieval tooling |
| `engine-100..102` | V/P2 distribution + Conductor product completion; only v1-critical deployability enters V |
| `engine-103` | C4/P2: wrap existing tools as governed MCP providers before building duplicates |
| `engine-104` | P2: feature-port candidates after convergence/revalidation |
| `engine-105` | C2/C4: orchestration/security dispatch only through canonical Graph + policy seams |
| `engine-110..111` | H, Implemented |
| `engine-112` | C3 after R1 |
| `engine-113` | R1 minimum first; P1 for remaining service depth |
| `engine-114..115` | P1 |

## `maistro-*`

| IDs | Disposition |
|---|---|
| `maistro-001..007` | V/P2; revalidate against current Conductor/auth/workspace implementation before doing old product-split work |
| `maistro-090..092` | C6 doc/registry migration only where still live |
| `maistro-095` | P2 scaffolding |
| `maistro-100` | P2 channels via C4 |
| `maistro-101..103` | P2 identity/crypto/trust integrations via C1/C4 |
| `maistro-150..151` | P2 cross-deployment A2A |
| `maistro-200` | C2, **deduped with `engine-097`; canonical Graph/Run runtime is the implementation** |
| `maistro-201` | P2 low-code designer over canonical Graph APIs |
| `maistro-202` | C3 if HITL parity remains; Human is a canonical Node/Approval provider, not a new lifecycle |
| `maistro-300` | P2 portability |
| `maistro-400..401` | P2 Canvas expansion over canonical Nodes/Bindings |

## `turing-*`

| IDs | Disposition |
|---|---|
| `turing-001..004` | F4 |
| `turing-010..013` | F4/F2; generic validated-learning pieces belong to F2, self-specific semantics stay F4 |
| `turing-020..023` | F4; preserve Accepted product specs but do not activate during core convergence |
| `turing-030..035` | F4 evaluation/activation gates |
| `turing-040..043` | C6/P2 migration/docs/scaffolding as needed; no activation |
| `turing-050..053` | F4/F3 |
| `turing-060..062` | F4/F5 |
| `turing-070..072` | F4/F1 |
| `turing-080..083` | F4/F2/P2 portability/routing |
| `turing-090..092`, `turing-095` | C6/F4 documentation/contract hygiene |
| `turing-100..102` | F4 research/calibration |
| `turing-200..201` | H, Abandoned |

## `sh-*`

| IDs | Disposition |
|---|---|
| `sh-001..003` | P2 multi-tenant catalog over C4 |
| `sh-010..012` | P2/C4 policy providers; do not create a second permission model |
| `sh-020..021` | H/C6 monorepo/content migration revalidation |
| `sh-030..032` | P2/V compliance documentation as release scope requires |
| `sh-040` | V/P2 red-team/eval |
| `sh-050` | P2 deployment parity |
| `sh-060` | C5/P2 audit chain correlated to canonical Events |
| `sh-070` | P2 product acceptance |
| `sh-080` | P2 scaffolding |
| `sh-090`, `sh-095` | C6/P2 contract hygiene |
| `sh-100` | F1/P2 trust promotion, bounded by C1/C4 permissions |
| `sh-101`, `sh-200` | F1, deduped continual-improvement loop |
| `sh-102` | F5 |
| `sh-201` | F2 |
| `sh-300..301` | P2 marketplace/failover |
| `sh-400..402` | P2 compliance certifications |
| `sh-500..503` | P2 validation of policy/catalog/compliance |
| `sh-600..605` | P2/F3 external tool/catalog/sandbox integrations; all gated by ADR-039 and C4 |

---

# Source-plan coverage

The earlier 0–51 convergence work breakdown is fully represented here:

| Earlier work | Now |
|---|---|
| inventory/vocabulary/ADRs/specs/architecture maps | C6 continuous governance; definition decisions already landed |
| Workspace, Persona, Template, Project, Agent-definition convergence | C1 |
| Graph, Run, NodeRun, Attempt, durable Graph, Runtime, cancellation | C2/C3 |
| task lifecycle, schedules, child delegation | C2/C5 |
| Capability/Provider/Binding/Invocation, tools, protocols, harness, HITL, permissions, credentials | C4 |
| Sessions, Events, checkpoints/recovery, resilience, memory, artifacts, observability | C5 |
| Builders, RSI, Evolve, Turing mapping, Canvas, Design, Bootstrap, server/Hive | C2/C3/C4 |
| Workspace/run inspection/UI surfaces | P1/P2 after service convergence, except UI needed for V1 verification |
| unreachable audits, reachability baseline, architecture fitness, migration tests, cleanup | C6 |

No separate “Phase 6” is reintroduced.

---

# Completion rules

A canonical item closes only when:
1. behavior exists at the owning layer;
2. tests bind to declared acceptance criteria;
3. the code is reachable from the real product path where the criterion claims it is used;
4. no predecessor implementation remains authoritative by accident;
5. no new bypass/duplicate lifecycle was introduced;
6. reachability/quality/security ratchets are banked in the same change;
7. docs/ADRs are corrected if implementation changed the actual decision boundary.

## Operational maintenance until P1 cutover

- `develop` is the active integration branch; topic backlog changes PR into `develop`.
- Stable legacy IDs are never renumbered. Their detailed old descriptions remain recoverable in git history.
- During convergence, humans and authorized agents may edit this file through normal topic-branch/PR flow.
- R1 introduces the durable Workspace backlog substrate before RSI consumes it.
- After `engine-114/115` prove UI + DB + agent read/write + restart durability, the DB becomes canonical and this file becomes a generated/exported view.
- Until that cutover, this file remains the coordinating human-readable authority.
- External-library decisions follow ADR-039.
