---
id: ADR-051
title: Tool approval gates — plan preview, impact-weighted escalation, learned trust
repo: maistro-engine
kind: adr
status: Proposed
created: 2026-05-13
substrate:
  - maistro-engine#ADR-050
  - maistro-engine#ADR-037
implements: []
related:
  - maistro-engine#ADR-028
  - maistro-engine#ADR-054
  - maistro-engine#ADR-056
supersedes: []
blocks: []
blocked-by: []
contracts:
  - boundary
  - behavioral
tests: []
layer: Governance
owners:
  - '@BlakeMatthews-dev'
---

# ADR-051: Tool approval gates — plan preview, impact-weighted escalation, learned trust

## Context

Sentinel enforces tool-call policy at the call site (`allow`/`deny`); it does not surface for human approval. Per ADR-050, `irreversible` tool calls need human approval before execution. Per-call synchronous prompts disrupt long tasks; plain per-task batch approval doesn't surface high-stakes calls. ADR-028 is process-level privilege separation, not task-level human-in-the-loop.

Mature production agent systems converge on a layered model: a single plan-level approval up front, automatic escalation for calls whose impact exceeds a threshold, and learned trust rules that promote frequently-approved patterns. This ADR specifies that layered model as a substrate primitive that Sentinel calls into.

## Problem

No substrate model for human approval of irreversible tool calls. Without one, products either gate every call (kills autonomy) or gate none (unsafe).

## Decision

Three layers, all active by default:

**1. Plan-level preview.** At task start, the agent declares its plan including every irreversible call it expects. Substrate raises one prompt covering the whole bundle. Approval allows execution without further prompts unless a *new* irreversible call appears mid-task (not declared in the plan).

**2. Per-call escalation.** An irreversible call whose `impact_estimator` (ADR-050) output exceeds a recipe-declared threshold raises an inline gate regardless of plan-level approval. Thresholds are per-resource (dollars, recipient count, audience, tokens, etc.) — collapsed into one prompt if multiple thresholds trip in the same window.

**3. Learned trust.** Substrate maintains a per-`(tenant, agent, tool, context-hash)` trust store. After N approvals over M days without a single denial, a pattern auto-promotes to `no further prompt`. Tenant opt-in; revocable; per-tool always-deny override always wins.

While waiting for any approval, the agent continues on non-dependent steps from its plan DAG. Blocks only on steps that consume the pending call's output.

## Interface (sketch)

```python
class ApprovalGate(Protocol):
    async def request_plan_approval(self, task_id: UUID, plan: TaskPlan) -> ApprovalDecision: ...
    async def request_escalation(self, task_id: UUID, call: ToolCall, impact: Impact) -> ApprovalDecision: ...
    async def record_decision(self, decision: ApprovalDecision) -> None: ...  # feeds learned-trust store

class ApprovalDecision(BaseModel):
    task_id: UUID
    target: Literal["plan", "call"]
    outcome: Literal["approved", "denied", "timeout"]
    latency_ms: int
    decided_by: str
    promoted_to_trust: bool = False
```

Recipe declares thresholds (merge: deep per ADR-053):

```yaml
approval:
  escalation_thresholds:
    dollars: { gt: 100 }
    recipients: { gt: 50 }
    tokens: { gt: 50_000 }
  learned_trust:
    enabled: true
    promote_after: { approvals: 5, days: 30, denials_max: 0 }
```

## Acceptance criteria

- [ ] Task with zero irreversible calls runs without an approval prompt.
- [ ] Task with N irreversible calls in plan-preview produces one prompt at start.
- [ ] An irreversible call appearing mid-execution not in the plan triggers a fresh gate.
- [ ] Per-resource thresholds independently checked against `impact_estimator` output.
- [ ] Multiple thresholds tripping in the same wall-clock window collapse to one prompt.
- [ ] Learned-trust store keyed strictly per `(tenant, agent, tool, context-hash)`; never global.
- [ ] Per-tool always-deny override always overrides a learned-trust promotion.
- [ ] Event `approval.gate.{raised,answered}` per ADR-037 with latency.
- [ ] Span `approval.wait` parents the agent's non-blocking parallel work.

## Open questions

1. **Notification surface.** Inline chat / push / dedicated queue. Recommend substrate exposes a `notify(target, prompt)` protocol; product picks the channel. Multiple channels can be wired simultaneously.
2. **Plan-DAG awareness.** Substrate needs to know which steps depend on a gated call to allow non-blocking parallel work. Recipe declares the DAG at task start, or substrate infers from data-flow analysis. Recommend explicit recipe declaration for v0.
3. **Trust promotion latency.** Recommend N=5 approvals over M=30 days with zero denials; configurable per recipe within substrate-wide bounds.
4. **Cross-tenant trust sharing.** Out of scope here. Stronghold concern.
5. **Bubble-up reuse for ADR-056 crash recovery.** The same approval-gate UI serves the "this tool was mid-flight on crash — retry / skip / mark-done" prompt. Recommend a single substrate surface.

## Source references

- `maistro-engine:src/maistro/security/sentinel/`
- ADR-050 reversibility taxonomy (provides `impact_estimator`).
- ADR-028 privilege separation (orthogonal; process-level, not task-level).

## Out of scope

- Specific notification channel implementations (Slack / email / push — product-level).
- The on-disk schema of the learned-trust store.
- Cross-tenant trust sharing (stronghold concern).
- Recipe-level approval policy DSL beyond the threshold map.
