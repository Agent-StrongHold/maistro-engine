# Anthropic Agent Framework — Research & Architecture Alignment

Source: [How Anthropic Thinks About Agents, Workflows, and Tasks](https://shellypalmer.com/2026/04/how-anthropic-thinks-about-agents-workflows-and-tasks/)

---

## Anthropic's Three-Tier Taxonomy

| Tier | Definition | Cost Profile | Failure Mode |
|------|-----------|--------------|--------------|
| **Task** | Single model call (summarization, classification, extraction) | Predictable, bounded | Contained to one call |
| **Workflow** | Multiple sequential model calls within a predetermined control flow | Linear with call count | Bounded by design |
| **Agent** | Model operating autonomously in a loop; uses tools to decide its own trajectory at runtime | Potentially unbounded | Errors compound through iterations |

The critical distinction: in a **workflow** the developer controls the flow; in an **agent** the model controls the flow.

---

## When to Build an Agent (Barry Zhang's Criteria)

1. **Task Ambiguity** — if the steps can be fully mapped in advance, build a workflow for better accuracy, lower cost, and tighter failure bounds.
2. **Token Economics** — a $0.10 budget covers roughly 30K–50K tokens (workflow territory). Choosing an agent pattern for a high-volume, low-ambiguity workload wastes proportionally; at 1M support tickets/month with 5× agent overhead that is ~$1.5M/year in avoidable spend.
3. **Capability Reliability** — the model's core competency for each subtask must be solid before looping; errors inside an agent loop compound on every iteration.
4. **Error Cost** — high-stakes actions (deploys, financial writes, infra changes) require human oversight and an audit trail, which caps how much autonomy an agent should have.

### Why Coding Is the Canonical Agent Use Case

Coding satisfies all four criteria:
- Ambiguous by nature — requirements rarely specify every file and function to touch.
- Strong model performance on code generation.
- Outputs are self-verifiable — unit tests provide a deterministic pass/fail signal.
- Error cost is moderate — a bad diff is visible and reversible.

---

## Essential Agent Components

1. **Operational environment** — the sandbox/workspace the agent can act on.
2. **Available tools** — what the model can call (file I/O, shell, search).
3. **System prompt** — objectives, constraints, and safety rails.

Caching and other optimizations are secondary; get these three right first.

---

## Maistro Architecture Mapping

| Anthropic Concept | Maistro Implementation | Status |
|---|---|---|
| Task | Direct LLM call returning `ConductorOutput` | ✅ supported via `ExecutionMode.TASK` |
| Workflow | PLANNING → CODING → REVIEWING → TESTING pipeline | ✅ encoded in `TaskStatus` enum; default `ExecutionMode.WORKFLOW` |
| Agent | Autonomous tool-loop (Phase 2 sub-agents) | 🔄 planned (`conductor.py` comment: "Phase 2 will split into sub-agents") |
| Operational environment | `/workspace` sandbox (Docker, `SandboxSettings`) | ✅ |
| Available tools | `tools/` — browser, git, media, sandbox | ✅ |
| System prompt with constraints | `CONDUCTOR_SYSTEM` with explicit `SAFETY CONSTRAINTS` section | ✅ |
| Token budget | `max_tokens_per_task` in `Settings` | ✅ |
| Token cost monitoring (p50/p95) | `llm_tokens_used_total` histogram in metrics | ✅ added |
| Trajectory logging | `conductor_trajectory` structured log event | ✅ added |
| Capability reliability gate | Circuit breaker (`circuit_breaker.py`) + retry with backoff | ✅ |

---

## Gaps and Recommendations

### 1. Enforce `ExecutionMode` at the Runner Layer

`TaskCreate.execution_mode` is now surfaced to callers but the runner and
conductor currently treat every task identically. A future improvement is to
short-circuit the plan/code/review pipeline for `TASK` mode (single call,
return immediately) and reserve the autonomous sub-agent loop for `AGENT` mode.

### 2. Expose Token p50/p95 in `/metrics`

`llm_tokens_used_total` now records per-call token counts in the histogram.
The `/metrics` endpoint already emits all histogram data. Operators should
alert when p95 token usage exceeds the `max_tokens_per_task` ceiling — a
sustained breach signals a runaway agent loop or an unexpectedly complex task
class that should be downgraded to a workflow.

### 3. Add a Pre-Deployment Trajectory Review Step

The `conductor_trajectory` log event (added in this change) emits subtask
count, files changed, review score, and execution mode for every completed
task. Before promoting the agent-mode path to production, review a sample of
trajectory logs to verify the model's decision path is sensible and does not
expand scope unexpectedly.

### 4. Audit Projects Mislabelled as Agents

Using `ExecutionMode.WORKFLOW` as the default (rather than `AGENT`) ensures
new tasks are conservatively routed. Callers that explicitly opt in to
`ExecutionMode.AGENT` surface themselves in logs, making periodic audits
straightforward.

---

## Token Economics Quick Reference

| Tier | Model size | Approx. tokens / $0.10 | Recommended mode |
|------|-----------|------------------------|-----------------|
| QUICK (1) | 7B | 150K–300K | TASK or WORKFLOW |
| STANDARD (2) | 32B | 30K–80K | WORKFLOW |
| THOROUGH (3) | 70B+ | 15K–40K | WORKFLOW or AGENT |
| ULTRA (4) | 70B+ (parallel) | 8K–20K per generation | AGENT (verified outputs only) |

At ULTRA tier with an agent loop the per-task cost can easily be 5–10× a
workflow. Reserve it for tasks with strong verifiability signals (unit tests,
linters, type checkers).
