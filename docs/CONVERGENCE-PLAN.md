# Convergence Plan

**Historical measurement baseline:** `develop` @ 9f8e6e8d (PR #476 merged) · **Date:** 2026-08-20
**Governing migration-order decision:** `ADR-082126-c9f4` / `SPEC-082126-c9f4`
**Current operational queue:** [`BACKLOG.md`](../BACKLOG.md)
**Rendered version:** https://claude.ai/code/artifact/8eef8a01-a9de-4536-bb43-bc4dc9ccf3b8

The execution spine is built and Accepted. Almost nothing uses it. This plan converges every
producer, island, and boundary onto it, measured per acceptance criterion, then deletes the
scaffolding and ships v1.

The stage descriptions below describe migration dependencies and required outcomes. Operational
priority is convergence-first under ADR-082126-c9f4. A replacement may move immediately ahead of
a convergence connection only when that exact connection would otherwise wire a disposable
predecessor; only the minimum replacement seam jumps, then convergence resumes.

## Ground truth

Facts from the tree at the baseline, from two full-tree sweeps (work-producers x Run,
governed-invocation coverage):

| Fact | Count |
|---|---|
| production call sites of the spine, repo-wide | 3 (`run_durable_graph` x1, `run_graph` x2) |
| competing run-record models in production | 4 (`tasks.Task`, builders `RunState`, hive `DagRun`, rsi `RunState`) |
| DAG/wave executors | 3 (`GraphRun`, builders `GraphPipelineExecutor`, `waves/ensemble`) |
| production callers of the governed invocation boundary | 0 — built, tested, unwired |
| clusters of direct LLM/tool calls bypassing governance | 24 |
| modules in the reachability baseline | 234 (agents 26, graph 21, security 18, builders 15, hive services 15) |
| spine ADRs Accepted, each with an AC-Defined spec | 11 |

Two structural causes. **Execution:** every maistro-server HTTP producer funnels into
`TaskQueue.submit` (off-spine), and a chat turn through `conduit.route_request` produces no Run.
**Governance:** the boundary is composed at the call site rather than enforced at the registry
seam, and `HarnessSessionManager` exposes an ungoverned `send()` next to the governed
`send_invocation()` nobody calls.

## Operating principle

**Status is derived, never asserted.** Every stage exits by moving criteria up the ladder
(`declared -> covered -> passing -> reachable`), so progress self-reports on every run of
`python scripts/check-ac-state.py --run-tests`.

**Convergence is the default priority.** Optional product/frontier work does not displace the next
dependency-valid convergence slice. The only queue-jump is ADR-082126-c9f4's
replacement-before-connection exception, and it ends as soon as the minimum replacement seam is
available.

Three numbers to watch: criteria at `reachable` (up), the reachability baseline (down from 234),
untagged scenarios (down from 64).

## Phase 0 — close the measurement loop

Small, parallelizable with everything else.

1. Tag and bind the last 64 scenarios (ADR-065 x26, SPEC-062326-e9c6 x12, ADR-061 x7,
   ADR-062326-702b x7, ADR-100 x6, SPEC-175/179 x3 each).
2. Settle the two contract contradictions: `redact(None)` -> `None` vs the scenario's `""`;
   `PoolStats.per_key` `available` vs the scenario's `is_available`.
3. Close ADR-064's pattern gaps: Telegram tokens, Sentry DSNs, JSON-field secrets, OpenSSH key
   blocks; benchmark the 1ms / no-backtracking bounds.
4. Wire `tools/lint_lifecycle.py` into CI with its 84 violations baselined; add transitions for
   the orphaned `Blocked`/`Abandoned` states and a spec-level `Deprecated`.
5. Fix the 3 order-dependent failures and the 26 turing-backend collection errors.

**Exit:** untagged scenarios = 0, lifecycle lint enforced, suite green under any ordering.

## Stage 2 — definition and ownership becomes the ordinary representation

Workspace -> Persona / Templates / Root Project (ADR-081226-9944, -bb3a, -e626, -6e34;
ADR-081426-b1d3).

Current state: the Workspace model is built and entirely unreachable
(`maistro.workspaces.model/store`); `projects.authorization`, `projects.sqlite_scope_store` and
`routes.projects` are in the baseline.

1. **Retrofit the 11 spine specs to tagged Gherkin + `ac-modules`.** (DONE — this commit.)
2. Wire Workspace/WorkspaceMembership into `container.py` and hive-conductor, with Root-Project
   provisioning on workspace creation.
3. `workspace_id`/`project_id` on Graph, captured immutably in the Run snapshot; child-Run
   workspace-boundary rule.
4. Template instantiation = copy + provenance into a destination Project; save-as-template
   explicit; template versions immutable.
5. Architecture-fitness rule: a new universal run-lifecycle definition is a violation. This is the
   fence that keeps stage 3 from regressing.

**Exit:** SPEC-9944/bb3a/b1d3/e626 criteria >= `passing`; workspace and project modules out of the
reachability baseline.

## Stage 3 — every work producer creates a Run

`ExecutionRuntime` has zero consumers outside `runs/` and `graph/durable_runs/`.

1. **Tasks -> Run.** `TaskQueue.submit` mints a Run; retire `tasks/lanes.py LaneGate`. Every
   maistro-server producer converges for free. Highest-traffic single change in the plan.
2. **Chat turn -> Run.** `conduit.route_request` produces a single-node Run; outcome rows become a
   derived view. Hive's `EngineService.route_request` follows.
3. **Events/reactor -> Run per firing**, keeping the Invocation row as delivery receipt (or an
   explicit ADR carve-out).
4. **Builders -> the graph executor.** Replaces `GraphPipelineExecutor` and builders `RunState`.
5. **Orchestrator waves -> nodes.** `waves/ensemble.py:441` already says this is possible.
6. Stragglers: a2a broker, `pm_runner`/`pm_llm_call`, repertoire cascade.
7. Hive `graph_runner`: lift `run_graph` -> `run_durable_graph`; drop its private httpx LLM callable.
8. `dag_run_store` -> adapter -> delete.

**Exit:** one run-record model in production; SPEC-a66b and SPEC-1f7c criteria `reachable`.

## Stage 4 — product islands onto the spine

Order: Builders, then RSI/Evolve, then Canvas/Design. Turing stays optional (out of v1 scope).

1. Builders (done in 3.4; the island template the others copy).
2. **Immediately before RSI consumes backlog state, execute R1 from `BACKLOG.md`:** establish the
   minimum Workspace-owned structured backlog repository/service seam plus Markdown import/export.
   Do not wire RSI to a disposable Markdown runtime contract, and do not build the full backlog UI
   before returning to convergence.
3. RSI — coordinator/autorun/RsiRunner mint Runs; `local_loop` subprocess work becomes Attempts
   under ExecutionRuntime with lease/fencing.
4. Evolve — `cycle.run_cycle` becomes a graph; each tournament battle a NodeRun.
5. Canvas/Design — pipeline stages become nodes; import `maistro_design.nodes` in the hive
   node-registration path; converge hive `canvas_dag`.
6. Wire the P1 resilience layer: `depth` into subgraph spawn, `compaction`+`steering` into the
   durable run loop, `retry_policy`+`rate_coordination`+`context_probe` into ExecutionRuntime.
7. Hive `chat_completion.py` — the 2,396-line bespoke agent loop, largest item in the plan.
   Decompose onto the conduit path and the tool boundary, behind parity tests, last.

**Exit:** builders/rsi/evolve/canvas reachability clusters ~ 0; every island's work visible as
canonical Runs in one store.

## Stage 5 — universal Binding/Invocation enforcement

1. Construct the governed service in `container.py`; make the registry return governed handles.
   Fix `capabilities_wiring.py`'s direct `resolve("self_repair")`.
2. Close the twin door: `HarnessSessionManager.send()` delegates to `send_invocation()`; fix hive
   `routes/harness.py` (Warden only, no policy today) and `graph/harness_executor.py`.
3. One LLM egress. Hive's `adapters/llm_http.py` becomes the single client inside the governed
   path; burn down the direct-call clusters. **Credential pool/rotation wires in here.**
4. Tools through capability providers; hive `tool_executor`'s private SSRF guard folds in; MCP
   routes get Warden + policy.
5. Delete `tools/approval/gate.py` — one approval mechanism, not two.
6. Flip on SPEC-070226-2b70/AC-8: the ci.yml rule failing direct provider calls in engine code.

**Exit:** AC-8 gate green, bypass list = 0, every effect has an Invocation record.

## Stage 6 — shared services and observation on canonical correlation

1. Wire the recording proxies at the single egress from 5.3.
2. Close SPEC-228 AC-5..10: the 6 `maistro_*` metrics, ~14 ADR-037 spans, 6 event topics,
   `trace_id`/`agent_id` in log context, retention policy.
3. Correlate run_id <-> trace_id <-> event topics <-> invocation ids.

**Exit:** SPEC-228 and SPEC-070226-2b70 fully `reachable`; one trace spans a chat turn end to end.

## Stage 7 — burn to zero, flip the gate, ship v1

1. Deletions: `GraphPipelineExecutor`, builders `RunState`, `LaneGate`, `dag_run_store`,
   `tools/approval/gate.py`.
2. Reachability burn-down; intentional library-only surfaces documented, not assumed.
3. Flip `check-ac-state.py` from report to gate — a completion claim below `reachable` fails CI.
4. Spec corpus complete: the 141 prose-only specs retrofitted layer-by-layer as their code is
   touched in stages 2-6.
5. v1 release: lockstep tags per ADR-073126-c4e1, `ghcr.io/agent-stronghold`, cosign.

**Definition of done:** islands at zero, one run model, one LLM egress, every completion claim
machine-verified, v1 tagged and signed.

## Sequencing

Operational sequencing is convergence-first under ADR-082126-c9f4. The current fine-grained
queue lives in `BACKLOG.md`; this table records the dependency order of the stages in this plan.

| Order | Work | Depends on |
|---|---|---|
| complete | Phase 0 measurement loop | — |
| next | Stage 2.2-2.5 Workspace/Project/Persona/Template wiring + architecture fence | Stage 2.1 |
| then | Stage 3 producers -> canonical Run | Stage 2 ownership/scope |
| then | Stage 4 product islands -> spine | Stage 3; R1 runs only immediately before RSI backlog consumption |
| then | Stage 5 universal governed Binding/Invocation enforcement | migrated execution paths from Stages 3-4 |
| then | Stage 6 event/recovery/observability correlation | single governed egress from Stage 5 |
| last | Stage 7 duplicate-owner deletion, gate flip, v1 | Stages 2-6 |

Two threads run continuously alongside without displacing the convergence trunk: the per-layer
spec retrofit (write criteria when touching a layer's code), and the ratchets staying monotone
(CI already enforces those).
